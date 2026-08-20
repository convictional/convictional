import asyncio
import io
import json
import os
from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx
import pytest
from fastapi import status

from config import settings
from infra.storage import (
    STORAGE_SERVICES,
    FileReference,
    FileValidationError,
    TrustedBytesIO,
    TrustedStr,
    store_file,
    store_file_from_stream,
    store_file_from_string,
)
from tests.helpers.app import AppClient


@pytest.mark.asyncio
async def test_storage(client: AppClient):
    file = await store_file(filename="test.txt", content=io.BytesIO(b"Test content"), content_type="text/plain")

    assert len(file.key) > 0
    assert file.content_type == "text/plain"
    assert file.byte_size == 12
    assert file.filename == "test.txt"
    file_url = await file.url()
    assert len(file_url) > 0

    response = await client.get(file_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.content == b"Test content"
    assert response.headers["content-disposition"] == 'attachment; filename="test.txt"'


@pytest.mark.asyncio
async def test_storage_validation(client: AppClient):
    with pytest.raises(FileValidationError):
        with open("tests/fixtures/binary_file.bin", "rb") as f:
            # Attempt to store a binary file that should be detected as octet-stream
            # Note: mime type is ignored - only binary content is checked
            await store_file(filename="binary_file.bin", content=f, content_type="application/octet-stream")


@pytest.mark.asyncio
async def test_storage_validation_uses_provided_content_type(client: AppClient):
    """Test that provided content_type is used instead of magic detection."""
    # Use binary content that magic detects as octet-stream (not in allowlist).
    # Without a provided content_type, this would fail validation.
    # With a provided XLSX content_type, it should pass.
    with open("tests/fixtures/binary_file.bin", "rb") as f:
        binary_content = f.read()

    file = await store_file(
        filename="test.xlsx",
        content=io.BytesIO(binary_content),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert file.content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert file.filename == "test.xlsx"


@pytest.mark.asyncio
async def test_storage_download_to_tmpfile(client: AppClient):
    file = await store_file(filename="test.txt", content=io.BytesIO(b"Test content"), content_type="text/plain")

    async with file.download_to_tempfile() as temp_file:
        assert temp_file.read() == "Test content"
        temp_file.seek(0)

    assert temp_file.closed

    async with file.download_to_tempfile(prefix="TEST") as temp_file:
        assert temp_file.name.split("/")[-1].startswith("TEST")
        assert temp_file.read() == "Test content"

    csv_file = await store_file(
        filename="test.csv", content=io.BytesIO(b"Test,content\nfoo,bar"), content_type="text/csv"
    )
    async with csv_file.download_to_tempfile(suffix=".csv") as temp_file:
        assert temp_file.name.endswith(".csv")
        assert temp_file.read() == "Test,content\nfoo,bar"


class MockStreamingResponse(httpx.Response):
    """Mock httpx.Response for testing streaming"""

    def __init__(self, content: bytes, chunk_size: int = 5):
        self.test_content = content
        self.chunk_size = chunk_size

    async def aiter_bytes(self, chunk_size: int | None = None) -> AsyncIterator[bytes]:
        """Simulate streaming by yielding content in chunks"""
        for i in range(0, len(self.test_content), self.chunk_size):
            yield self.test_content[i : i + self.chunk_size]
            # Small delay to simulate network latency
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_storage_streaming(client: AppClient):
    # Test content that's larger than our chunk size
    test_content = b"This is a longer test content that will be streamed in chunks"
    mock_response = MockStreamingResponse(test_content)

    file = await store_file_from_stream(
        streaming_response=mock_response, filename="stream_test.txt", content_type="text/plain"
    )

    # Verify file metadata
    assert len(file.key) > 0
    assert file.content_type == "text/plain"
    assert file.byte_size == len(test_content)
    assert file.filename == "stream_test.txt"
    file_url = await file.url()
    assert len(file_url) > 0

    # Verify content was stored correctly
    response = await client.get(file_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.content == test_content
    assert response.headers["content-disposition"] == 'attachment; filename="stream_test.txt"'

    # Verify tempfile functionality works with streamed content
    async with file.download_to_tempfile() as temp_file:
        assert temp_file.read() == test_content.decode()
        temp_file.seek(0)


@pytest.mark.asyncio
async def test_storage_upload(client: AppClient):
    test_content = b"Test content"
    test_filename = "test.txt"

    # Upload file
    response = await client.post(
        "/storage/test-key/upload",
        data={"next": "/"},
        files={"file": (test_filename, io.BytesIO(test_content), "text/plain")},
    )
    assert response.status_code == status.HTTP_200_OK

    # File exists
    assert os.path.exists(settings.local_storage_path / "test-key")


@pytest.mark.asyncio
async def test_upload_target_round_trip(client: AppClient):
    # Mirrors the React direct-upload flow: mint a target, POST the file to it
    # without `next` (so the endpoint returns 201, as GCS would), then
    # materialize the FileReference from the returned key.
    service = STORAGE_SERVICES[settings.storage_service]()
    target = await service.upload_target(content_type="video/mp4", max_bytes=10_000_000)

    assert target.action
    assert target.key

    content = b"fake video bytes"
    response = await client.post(
        target.action,
        data=dict(target.fields),
        files={"file": ("rec.mp4", io.BytesIO(content), "video/mp4")},
    )
    assert response.status_code == status.HTTP_201_CREATED

    file_ref = await FileReference.from_key(target.key)
    assert file_ref.byte_size == len(content)


@pytest.mark.asyncio
async def test_upload_target_classmethod_delegates_to_current_service(client: AppClient):
    # FileReference.upload_target keeps storage-service selection inside the
    # model so callers (e.g. the meetings API) don't reach into STORAGE_SERVICES.
    target = await FileReference.upload_target(content_type="video/mp4", max_bytes=10_000_000)
    assert target.action
    assert target.key


@pytest.mark.asyncio
async def test_trusted_storage(client: AppClient):
    """Test that TrustedStr and TrustedBytesIO bypass validation."""
    # Test 1: TrustedStr with JSON content that might be misdetected as JavaScript
    raw_data = {
        "id": "test_message_123",
        "from": "test@example.com",
        "body": "function test() { return true; }",
    }

    file = await store_file_from_string(
        content=TrustedStr(json.dumps(raw_data)),
        filename="test_raw_data.json",
        content_type="application/json",
    )

    assert len(file.key) > 0
    assert file.content_type == "application/json"
    assert file.filename == "test_raw_data.json"

    # Verify content was stored correctly
    downloaded_content = (await file.download()).decode()
    assert json.loads(downloaded_content) == raw_data

    # Test 2: TrustedBytesIO bypasses validation
    file2 = await store_file(
        content=TrustedBytesIO(b"test content"),
        filename="test_trusted.txt",
        content_type="text/plain",
    )

    assert len(file2.key) > 0
    assert file2.content_type == "text/plain"

    # Test 3: Regular string still goes through validation
    simple_data = {"test": "data"}
    file3 = await store_file_from_string(
        content=json.dumps(simple_data),
        filename="test_regular.json",
        content_type="application/json",
    )

    assert len(file3.key) > 0
    assert file3.content_type == "application/json"


@pytest.mark.asyncio
async def test_storage_special_characters_in_filename(client: AppClient):
    """Test that filenames with special characters are handled correctly.

    RFC 5987 specifies that filenames with special characters should be encoded
    using the filename*=utf-8'' format with percent-encoding.
    """
    filename = "Convictional Commerce, Inc._Engagement Letter (to be signed).pdf"

    file = await store_file(
        filename=filename,
        content=io.BytesIO(b"Test PDF content"),
        content_type="application/pdf",
    )

    assert file.filename == filename

    response = await client.get(await file.url())
    assert response.status_code == status.HTTP_200_OK
    assert response.content == b"Test PDF content"
    # RFC 5987 encoding for filenames with special characters
    content_disposition = response.headers["content-disposition"]
    assert content_disposition.startswith("inline; filename")
    # Verify the complete filename is present (URL-encoded for special chars)
    encoded_filename = quote(filename)
    assert encoded_filename in content_disposition


@pytest.mark.asyncio
async def test_storage_sanitizes_filenames(client: AppClient):
    # Path traversal collapses to basename and dangerous characters are stripped
    # before the filename is persisted or rendered into a download URL.
    file = await store_file(
        filename="../../../etc/passwd\x00.txt",
        content=io.BytesIO(b"Test content"),
        content_type="text/plain",
    )
    assert file.filename == "passwd.txt"

    stream_file = await store_file_from_stream(
        streaming_response=MockStreamingResponse(b"streamed"),
        filename='evil"name\r\n.txt',
        content_type="text/plain",
    )
    assert stream_file.filename == "evilname.txt"


@pytest.mark.asyncio
async def test_storage_content_disposition_by_mime_type(client: AppClient):
    # Inline-eligible types: PDFs, videos, images, audio render in-browser
    # so iOS PWA users can preview them instead of getting a blank page.
    # Asserting the real Content-Type matters: with octet-stream, browsers
    # download regardless of disposition, so we'd preview-test a lie.
    inline_cases: list[tuple[str, io.BytesIO, str]] = [
        ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf"),
        ("test.mp4", TrustedBytesIO(b"\x00\x00\x00\x00"), "video/mp4"),
        ("test.png", TrustedBytesIO(b"\x00\x00\x00\x00"), "image/png"),
        ("test.mp3", TrustedBytesIO(b"\x00\x00\x00\x00"), "audio/mpeg"),
    ]
    for filename, content, content_type in inline_cases:
        file = await store_file(filename=filename, content=content, content_type=content_type)
        response = await client.get(await file.url())
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-disposition"].startswith("inline"), (
            f"expected inline for {content_type}, got {response.headers['content-disposition']}"
        )
        assert response.headers["content-type"].startswith(content_type), (
            f"expected content-type {content_type}, got {response.headers['content-type']}"
        )

    # Attachment types: text/plain, octet-stream, and SVG (security: SVG can embed JS).
    attachment_cases = [
        ("test.txt", io.BytesIO(b"plain text"), "text/plain"),
        ("test.svg", io.BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"), "image/svg+xml"),
        ("test.bin", TrustedBytesIO(b"\x00\x00\x00\x00"), "application/octet-stream"),
    ]
    for filename, content, content_type in attachment_cases:
        file = await store_file(filename=filename, content=content, content_type=content_type)
        response = await client.get(await file.url())
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-disposition"].startswith("attachment"), (
            f"expected attachment for {content_type}, got {response.headers['content-disposition']}"
        )
        assert response.headers["content-type"].startswith(content_type), (
            f"expected content-type {content_type}, got {response.headers['content-type']}"
        )
