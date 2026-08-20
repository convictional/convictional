import asyncio
import base64
import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar
from uuid import UUID

import httpx
import instructor  # type: ignore[import-untyped]
import sentry_sdk
from anthropic import NOT_GIVEN, AsyncAnthropic, AsyncStream, NotGiven
from anthropic.types import (
    Message,
    MessageParam,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    RawMessageStreamEvent,
    ToolUnionParam,
)
from instructor.core.client import T  # type: ignore[import-untyped]
from instructor.dsl.partial import Partial  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError
from sentry_sdk.ai.monitoring import record_token_usage
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import logger, settings
from config.enums import LLMMessageRole
from infra.storage import FileReference

# Narrower than instructor's `T` (which also covers Iterable/Partial); restricts
# `streaming_partial_json_completion` to genuine pydantic models so we can call
# `model_json_schema()` and inspect fields.
PydanticT = TypeVar("PydanticT", bound=BaseModel)


DEFAULT_MODEL = "claude-sonnet-4-6"


class LLMTruncationError(Exception):
    """Raised when the model stopped because it hit max_tokens rather than finishing.

    The response text is incomplete (cut off mid-sentence). Callers should treat this
    as a failure — never persist or send the partial output — and either raise a larger
    max_tokens or retry.
    """


def _resolve_temperature(temperature: float | None) -> float | NotGiven:
    return temperature if temperature is not None else NOT_GIVEN


def _unwrap_self_nested_list_fields(partial: BaseModel, list_field_names: Iterable[str]) -> None:
    # Repairs Sonnet hallucination: list field wrapped as `{"sections": {"sections": [...]}}`.
    # NOTE: the hoisted `inner` elements are the raw parsed dicts — they are NOT re-validated into
    # the field's item model here. Callers iterating the repaired list must coerce/validate each
    # element themselves (see `_as_llm_section` in app/routers/api/mailbox_views.py for the pattern).
    for field_name in list_field_names:
        value = getattr(partial, field_name, None)
        if not isinstance(value, dict) or len(value) != 1:
            continue
        inner = value.get(field_name)
        if isinstance(inner, list):
            setattr(partial, field_name, inner)


# Retry policy for `streaming_partial_json_completion`. Wait is driven by
# `settings.mailbox_retry_wait_seconds` so tests can zero it out via env without
# patching tenacity internals.
_retry_wait_seconds = settings.mailbox_retry_wait_seconds
_STREAMING_RETRY_POLICY: dict[str, Any] = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(
        multiplier=_retry_wait_seconds,
        min=_retry_wait_seconds,
        max=_retry_wait_seconds * 2,
    ),
    "retry": retry_if_exception_type(ValidationError),
    "reraise": True,
}


async def _iter_json_text_deltas(stream: AsyncStream[RawMessageStreamEvent]) -> AsyncGenerator[str]:
    # Yields text deltas from an Anthropic stream, stripping any preface before the
    # first `{` so the partial JSON parser only sees valid JSON.
    seen_open_brace = False
    async for event in stream:
        if event.type != "content_block_delta":
            continue
        delta = event.delta
        if getattr(delta, "type", None) != "text_delta":
            continue
        text = getattr(delta, "text", "")
        if not text:
            continue
        if not seen_open_brace:
            idx = text.find("{")
            if idx == -1:
                continue
            text = text[idx:]
            seen_open_brace = True
        yield text


def _try_repair_validation[T: BaseModel](
    last_partial: BaseModel | None,
    response_model: type[T],
) -> T | None:
    # Re-validate the last successfully-constructed partial against the strict model.
    # The unwrap helper already mutated `last_partial` in place during streaming; this
    # is the second chance for those repairs to surface a valid object. Returns None
    # if validation still fails, signalling the caller to propagate the original error.
    if last_partial is None:
        return None
    try:
        # `last_partial` is a streamed `Partial`, so nested fields may still hold raw dicts
        # rather than validated submodels; dumping it would emit pydantic serializer warnings.
        # We immediately re-validate the dump against the strict model, so the intermediate
        # shape mismatch is expected and the warnings are noise.
        return response_model.model_validate(last_partial.model_dump(warnings=False))
    except ValidationError:
        return None


#
# Clients
#
#


@asynccontextmanager
async def get_anthropic_client(api_key: str = settings.anthropic_api_key.get_secret_value()):
    async with httpx.AsyncClient() as http_client:
        yield AsyncAnthropic(api_key=api_key, http_client=http_client)


#
# Completion
#
#


@dataclass
class LLMMessage:
    id: str
    role: LLMMessageRole
    content: str | list[dict[str, str]]


@dataclass
class LLM:
    api_key: str | None = None
    organization_id: UUID | None = None

    async def instructor_completion(
        self,
        user_prompt: str,
        system_prompt: str,
        response_model: type[T],
        max_tokens: int = 4096,
        model: str = DEFAULT_MODEL,
        temperature: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Generic completion function for simple instructor completions.
        This function covers the basics of getting an LLM completion using instructor and should be used in most cases.
        If you need to re-use a response_model in multiple places, subclass it, or have more complex completions,
        consider creating a new completion function.

        Args:
            user_prompt (str): The user prompt for the completion.
            system_prompt (str): The system prompt for the completion.
            response_model (type[T]): The response model for the completion.

        Returns:
            T: An instance of the response model with the completion results from the LLM.
        """

        messages: list[MessageParam] = [{"role": "user", "content": user_prompt}]

        with sentry_sdk.start_span(op="infra.llm.instructor_completion", name="Instructor completion"):
            async with get_anthropic_client(*self._get_anthropic_credentials()) as client:
                instructor_client = instructor.from_anthropic(client)
                return await instructor_client.chat.completions.create(
                    messages=messages,
                    max_tokens=max_tokens,
                    model=model,
                    temperature=_resolve_temperature(temperature),
                    response_model=response_model,
                    context=context,
                    system=system_prompt,
                )

    async def instructor_streaming_completion(
        self,
        user_prompt: str,
        system_prompt: str,
        response_model: type[T],
        max_tokens: int = 4096,
        model: str = DEFAULT_MODEL,
        temperature: float | None = None,
    ) -> AsyncGenerator[T]:
        """Stream partial structured responses as they're generated.

        Uses instructor's create_partial to yield incremental snapshots of the response
        model as the LLM generates JSON. Each yield contains a progressively more
        complete version of the response.

        Note: Pydantic validators are not supported with partial streaming due to
        incomplete data during generation.

        Note: Anthropic's tool_use streaming is buffered server-side and arrives as a
        single burst at the end. If progressive token-level streaming matters for the UX,
        use `streaming_partial_json_completion` instead.
        """
        messages: list[MessageParam] = [{"role": "user", "content": user_prompt}]

        with sentry_sdk.start_span(
            op="infra.llm.instructor_streaming_completion", name="Instructor streaming completion"
        ):
            async with get_anthropic_client(*self._get_anthropic_credentials()) as client:
                instructor_client = instructor.from_anthropic(client, mode=instructor.Mode.ANTHROPIC_TOOLS)
                stream = instructor_client.chat.completions.create_partial(
                    messages=messages,
                    max_tokens=max_tokens,
                    model=model,
                    temperature=_resolve_temperature(temperature),
                    response_model=response_model,
                    system=system_prompt,
                )
                async for partial in stream:
                    yield partial

    async def streaming_partial_json_completion(
        self,
        user_prompt: str,
        system_prompt: str,
        response_model: type[PydanticT],
        max_tokens: int = 4096,
        model: str = DEFAULT_MODEL,
        temperature: float | None = None,
        on_retry: Callable[[int], Awaitable[None]] | None = None,
    ) -> AsyncGenerator[PydanticT]:
        """Stream partial structured responses with genuine token-level progressiveness.

        Unlike `instructor_streaming_completion`, which uses Anthropic's tool_use mode
        and buffers the JSON server-side, this injects the schema into the system prompt,
        streams raw text deltas, and feeds them into `Partial[Model].model_from_chunks_async`
        so each chunk yields a progressively more complete pydantic model.

        If the final pydantic validation fails (and the dict-unwrap repair can't recover),
        the entire attempt is retried per `_STREAMING_RETRY_POLICY`. `on_retry`, when
        provided, fires just before each retry with the upcoming 1-indexed attempt number
        — callers use it to discard already-streamed partials. Only `ValidationError`
        triggers a retry; everything else propagates.
        """
        schema_dict = response_model.model_json_schema()
        schema_json = json.dumps(schema_dict, indent=2, ensure_ascii=False)
        list_field_names = tuple(
            name
            for name, prop in schema_dict.get("properties", {}).items()
            if prop.get("type") == "array" or any(sub.get("type") == "array" for sub in prop.get("anyOf", []))
        )
        full_system = (
            f"{system_prompt}\n\n"
            f"Respond with a JSON object matching this schema:\n{schema_json}\n\n"
            "Output ONLY the JSON object itself. No preface, no markdown code fences, no "
            "trailing commentary."
        )
        # Anthropic Sonnet 4.6+ rejects requests that don't end on a user message, so we
        # can't use the historical assistant `{` prefill. `_iter_json_text_deltas` strips
        # any prose preface before the first `{` to keep the partial parser fed valid JSON.
        messages: list[MessageParam] = [{"role": "user", "content": user_prompt}]
        partial_model = Partial[response_model]  # type: ignore[valid-type]

        async def _signal_retry(state: RetryCallState) -> None:
            if on_retry is None:
                return
            try:
                # attempt_number is the just-failed attempt; the next one is +1.
                await on_retry(state.attempt_number + 1)
            except Exception:
                logger.exception("on_retry callback raised between streaming_partial_json_completion attempts")

        async def _run_attempt() -> AsyncGenerator[PydanticT]:
            async with get_anthropic_client(*self._get_anthropic_credentials()) as client:
                stream: AsyncStream[RawMessageStreamEvent] = await client.messages.create(
                    messages=messages,
                    system=full_system,
                    max_tokens=max_tokens,
                    model=model,
                    temperature=_resolve_temperature(temperature),
                    stream=True,
                )
                # The partial parser re-parses the full accumulated buffer on every delta
                # (O(N²) in buffer length), bounded by max_tokens — if a caller raises
                # max_tokens substantially, consider throttling.
                last_partial: PydanticT | None = None
                try:
                    async for obj in partial_model.model_from_chunks_async(_iter_json_text_deltas(stream)):  # type: ignore[attr-defined]
                        _unwrap_self_nested_list_fields(obj, list_field_names)
                        last_partial = obj
                        yield obj
                except ValidationError:
                    recovered = _try_repair_validation(last_partial, response_model)
                    if recovered is None:
                        raise
                    yield recovered
                finally:
                    await stream.close()

        with sentry_sdk.start_span(
            op="infra.llm.streaming_partial_json_completion", name="Streaming partial JSON completion"
        ):
            async for attempt in AsyncRetrying(**_STREAMING_RETRY_POLICY, before_sleep=_signal_retry):
                with attempt:
                    sentry_sdk.set_tag("attempt", attempt.retry_state.attempt_number)
                    async for obj in _run_attempt():
                        yield obj

    async def string_completion(
        self,
        user_prompt: str,
        system_prompt: str,
        model: str = DEFAULT_MODEL,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ):
        messages: list[MessageParam] = [
            {"role": "user", "content": user_prompt},
        ]

        with sentry_sdk.start_span(op="infra.llm.string_completion", name="String completion"):
            async with get_anthropic_client(*self._get_anthropic_credentials()) as client:
                results: Message = await client.messages.create(
                    messages=messages,
                    system=system_prompt,
                    max_tokens=max_tokens,
                    model=model,
                    temperature=_resolve_temperature(temperature),
                )
                if results.stop_reason == "max_tokens":
                    raise LLMTruncationError(
                        f"Completion truncated at max_tokens={max_tokens} "
                        f"(model={model}, output_tokens={results.usage.output_tokens})"
                    )
                if results.content[0].type == "text":
                    return results.content[0].text

                raise ValueError("String completion returned a non-text result")

    async def instructor_multimodal_completion(
        self,
        user_prompt: str,
        system_prompt: str,
        file: FileReference,
        response_model: type[T],
        model: str = DEFAULT_MODEL,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> T | None:
        # Claude only accepts these media types
        accepted_media_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in accepted_media_types:
            logger.warning(f"Invalid media type for image completion: {file.content_type}")
            return None

        file_content = base64.b64encode(await file.download()).decode("utf-8")
        instructor_image = instructor.Image(source="", media_type=file.content_type, data=file_content)

        messages = [{"role": "user", "content": [user_prompt, instructor_image]}]

        with sentry_sdk.start_span(
            op="infra.llm.instructor_completion_with_image", name="Instructor completion with image"
        ):
            async with get_anthropic_client(*self._get_anthropic_credentials()) as client:
                instructor_client = instructor.from_anthropic(client)
                return await instructor_client.chat.completions.create(
                    messages=messages,
                    max_tokens=max_tokens,
                    model=model,
                    temperature=_resolve_temperature(temperature),
                    response_model=response_model,
                    system=system_prompt,
                )

    async def chat_completion(
        self,
        system_prompt: str,
        prior_messages: list[LLMMessage],
        model: str = DEFAULT_MODEL,
        stream: bool = True,
        temperature: float | None = None,
        max_tokens: int = 4096,
        tools: Iterable[ToolUnionParam] | None = None,
    ):
        messages: list[MessageParam] = []

        for message in prior_messages:
            messages.append({"role": message.role.value, "content": message.content})  # type: ignore

        with sentry_sdk.start_span(op="infra.llm.chat_completion", name="Chat completion") as span:
            async with get_anthropic_client(*self._get_anthropic_credentials()) as client:
                result_stream: AsyncStream[RawMessageStreamEvent] = await client.messages.create(
                    messages=messages,
                    system=system_prompt,
                    model=model,
                    max_tokens=max_tokens,
                    stream=stream,
                    temperature=_resolve_temperature(temperature),
                    tools=tools or NOT_GIVEN,
                )

                try:
                    chunks: list[RawMessageStreamEvent] = []
                    async for chunk in result_stream:
                        chunks.append(chunk)
                        yield chunk

                    start_message: RawMessageStartEvent = [chunk for chunk in chunks if chunk.type == "message_start"][
                        0
                    ]
                    last_message_delta: RawMessageDeltaEvent = [
                        chunk for chunk in chunks if chunk.type == "message_delta"
                    ][-1]

                    if last_message_delta and last_message_delta.usage:
                        input_tokens = start_message.message.usage.input_tokens
                        output_tokens = last_message_delta.usage.output_tokens
                        record_token_usage(span, input_tokens=input_tokens, output_tokens=output_tokens)
                except asyncio.CancelledError:
                    logger.warning("Chat completion stream was cancelled")
                    raise
                finally:
                    await result_stream.close()

    def _get_anthropic_credentials(self):
        api_key = self.api_key or settings.anthropic_api_key.get_secret_value()
        return (api_key,)
