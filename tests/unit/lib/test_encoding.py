import pytest
import tiktoken

from lib.encoding import EMBEDDING_ENCODING, chunk_string


def test_chunk_string():
    chunks = chunk_string("", 10, EMBEDDING_ENCODING)
    assert chunks == []

    test_string = "Hello world! " * 50
    chunks = chunk_string(test_string, 10, EMBEDDING_ENCODING)
    assert isinstance(chunks, list)
    assert len(chunks) > 1
    assert all(isinstance(chunk, str) for chunk in chunks)

    tokenizer = tiktoken.get_encoding(EMBEDDING_ENCODING)
    for chunk in chunks:
        tokens = tokenizer.encode(chunk)
        assert len(tokens) <= 10


def test_chunk_string_special_tokens():
    # By default, treats all special tokens as allowed
    chunks = chunk_string("foo <|endoftext|>", 10, EMBEDDING_ENCODING)
    assert len(chunks) == 1

    # Can specify disallowed special tokens
    with pytest.raises(ValueError):
        chunk_string("foo <|endoftext|>", 10, EMBEDDING_ENCODING, disallowed_special="all")
    with pytest.raises(ValueError):
        chunk_string("foo <|endoftext|>", 10, EMBEDDING_ENCODING, disallowed_special={"<|endoftext|>"})

    # Can specify allowed special tokens
    chunks = chunk_string("foo <|im_start|>", 10, EMBEDDING_ENCODING, allowed_special={"<|im_start|>"})
    assert len(chunks) == 1
