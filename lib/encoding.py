from collections.abc import Callable, Iterable
from typing import Literal

import tiktoken

# Using the gpt-4o encoder because that's what we've been using for chunking so far
LLM_ENCODING = "o200k_base"

# This is the right encoding for working with the OpenAI text-embedding-3-small model
EMBEDDING_ENCODING = "cl100k_base"


def chunk_string(
    string: str,
    max_tokens: int,
    encoding: str,
    allowed_special: set[str] | Literal["all"] = set(),
    disallowed_special: set[str] | Literal["all"] = set(),
) -> list[str]:
    tokenizer = tiktoken.get_encoding(encoding)
    tokens = tokenizer.encode(string, allowed_special=allowed_special, disallowed_special=disallowed_special)
    chunks: list[str] = []
    current_chunk: list[int] = []
    current_size = 0

    for token in tokens:
        if current_size + 1 > max_tokens:
            chunks.append(tokenizer.decode(current_chunk))
            current_chunk = []
            current_size = 0

        current_chunk.append(token)
        current_size += 1

    if current_chunk:
        chunks.append(tokenizer.decode(current_chunk))

    return chunks


def chunk_objects[Chunkable](
    chunkables: Iterable[Chunkable],
    line_getter: Callable[[Chunkable], str],
    target_tokens_per_chunk: int,
    encoding: str,
) -> Iterable[list[Chunkable]]:
    """
    Groups a series of objects into chunks, ensuring that each chunk is no longer than `target_tokens_per_chunk`
    """
    tokenizer = tiktoken.get_encoding(encoding)

    chunk: list[Chunkable] = []
    tokens_in_chunk = 0
    for chunkable in chunkables:
        tokens = tokenizer.encode(line_getter(chunkable))
        if tokens_in_chunk + len(tokens) > target_tokens_per_chunk:
            yield chunk
            chunk = []
            tokens_in_chunk = 0
        chunk.append(chunkable)
        tokens_in_chunk += len(tokens)

    if chunk:
        yield chunk
