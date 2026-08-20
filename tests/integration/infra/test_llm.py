import pytest

from infra.llm import LLM, LLMTruncationError

pytestmark = pytest.mark.real_embeddings


@pytest.mark.asyncio
async def test_string_completion_raises_on_truncation():
    # A tiny max_tokens forces the model to stop on max_tokens rather than finishing,
    # producing a mid-sentence cutoff. string_completion must refuse to return the
    # partial text so callers never persist or email a truncated report.
    llm = LLM()

    with pytest.raises(LLMTruncationError):
        await llm.string_completion(
            user_prompt="Write a detailed multi-paragraph essay about the history of computing.",
            system_prompt="Respond with a thorough, long-form answer.",
            max_tokens=16,
        )
