import asyncio
import datetime
import hashlib
import io
import mimetypes
import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlencode
from uuid import uuid4 as generate_uuid

import google.auth
import httpx
import magic
from fastapi import APIRouter, File, Form, Query, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from google.auth import impersonated_credentials
from google.auth.transport import requests
from google.cloud import storage  # type: ignore
from pydantic import BaseModel
from tortoise import BaseDBAsyncClient, fields
from tortoise.models import Model

from config import logger, settings
from config.settings import StorageService
from lib.filenames import DEFAULT_FILENAME, sanitize_filename
from lib.mime_types import is_inline_content_type

#
# Trusted Content Types
#
#


class TrustedBytesIO(io.BytesIO):
    """Marks file content as pre-validated and trusted.

    Use only for internal/system-generated content.
    Never use for user uploads or external sources.
    """

    pass


class TrustedStr(str):
    """Marks string content as pre-validated and trusted for file storage.

    Use only for internal/system-generated content.
    Never use for user-provided strings or external data.
    """

    pass


#
# File Validation
#
#


class FileValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


ALLOWED_MIME_PREFIXES = [
    "audio/",
    "image/",
    "text/",
    "video/",
    "application/gzip",
    "application/ics",
    "application/json",
    "application/msword",
    "application/pdf",
    "application/rtf",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument",
    "application/vnd.rar",
    "application/x-7z-compressed",
    "application/x-ole-storage",
    "application/x-tar",
    "application/x-zip-compressed",
    "application/xml",
    "application/zip",
]

FILE_VALIDATION_PEEK_SIZE = 2048  # 2KB


def validate_file(file: BinaryIO, content_type: str | None = None):
    if isinstance(file, TrustedBytesIO):
        return

    # Use provided content_type if available, otherwise detect via magic bytes
    if content_type:
        mime_type = content_type
    else:
        mime_type = magic.from_buffer(file.read(FILE_VALIDATION_PEEK_SIZE), mime=True)
        file.seek(0)

        if not mime_type:
            raise FileValidationError("File type could not be detected")

    if not any(mime_type.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES):
        raise FileValidationError(f"File type '{mime_type}' is not allowed")


#
# API for local storage
#
#

router = APIRouter()


@router.get("/{key}/filename/{filename}")
async def storage_download(
    key: str,
    filename: str,
    content_type: str = Query("application/octet-stream"),
) -> FileResponse:
    # Mirror GCS: derive disposition server-side from the content type so the
    # client URL can't flip a stored SVG to inline and bypass is_inline_content_type.
    disposition = "inline" if is_inline_content_type(content_type) else "attachment"
    return FileResponse(
        path=settings.local_storage_path / key,
        media_type=content_type,
        content_disposition_type=disposition,
        filename=filename,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/{key}/upload/")
async def storage_upload(
    key: str,
    file: bytes = File(...),
    next: str | None = Form(None),
):
    with open(LocalStorage._build_path(key), "wb") as f:
        f.write(file)

    # The legacy HTML form flow passes `next` and expects a redirect back to its
    # completion route. The React direct-upload flow (FileReference.from_key)
    # omits `next` and just needs a 201, mirroring a GCS signed-POST response.
    if next is None:
        return Response(status_code=status.HTTP_201_CREATED)

    query = urlencode({"key": key})
    return RedirectResponse(url=next + "?" + query, status_code=status.HTTP_302_FOUND)


#
# Storage services
#
#


class FileUploadForm(BaseModel):
    action: str
    fields: dict[str, str]

    @classmethod
    async def new(cls, next_url: str):
        service = STORAGE_SERVICES[settings.storage_service]()
        form = await service.upload_form(next_url)
        return cls(action=form.action, fields=form.fields)


# Direct (browser → storage) upload target for the fetch-based React flow.
# Unlike FileUploadForm, the client POSTs via fetch and reads the status code
# rather than following a redirect, and needs the object `key` back so it can
# hand it to the backend (FileReference.from_key) once the upload completes.
class UploadTarget(BaseModel):
    action: str
    fields: dict[str, str]
    key: str


class ServiceBase(ABC):
    @abstractmethod
    async def save(self, file: BinaryIO, filename: str, content_type: str) -> str:
        pass

    @abstractmethod
    async def save_streaming(
        self, stream: AsyncGenerator[bytes], filename: str, content_type: str
    ) -> tuple[str, int, str]:
        pass

    @abstractmethod
    async def retrieve(self, key: str) -> bytes:
        pass

    @abstractmethod
    async def url(self, key: str, filename: str, content_type: str | None = None) -> str:
        pass

    @abstractmethod
    async def upload_form(self, next_url: str) -> FileUploadForm:
        pass

    @abstractmethod
    async def upload_target(self, *, content_type: str, max_bytes: int) -> UploadTarget:
        pass

    @abstractmethod
    async def content_type(self, key: str) -> str:
        pass

    @abstractmethod
    async def size(self, key: str) -> int:
        pass

    @abstractmethod
    async def checksum(self, key: str) -> str:
        pass


class LocalStorage(ServiceBase):
    prefix: str | None = None

    async def save(self, file: BinaryIO, filename: str, content_type: str) -> str:
        unique_key = str(generate_uuid())

        def _write() -> None:
            with open(self._build_path(unique_key), "wb") as buffer:
                shutil.copyfileobj(file, buffer)

        await asyncio.to_thread(_write)
        file.seek(0)
        return unique_key

    async def save_streaming(
        self, stream: AsyncGenerator[bytes], filename: str, content_type: str
    ) -> tuple[str, int, str]:
        unique_key = str(generate_uuid())
        md5_hash = hashlib.md5()
        byte_size = 0
        with open(self._build_path(unique_key), "wb") as buffer:
            async for chunk in stream:
                md5_hash.update(chunk)
                byte_size += len(chunk)
                buffer.write(chunk)

        return unique_key, byte_size, md5_hash.hexdigest()

    async def retrieve(self, key: str) -> bytes:
        def _read() -> bytes:
            with open(self._build_path(key), "rb") as f:
                return f.read()

        return await asyncio.to_thread(_read)

    async def url(self, key: str, filename: str, content_type: str | None = None) -> str:
        result = ""
        if LocalStorage.prefix:
            result += LocalStorage.prefix
        result += router.url_path_for("storage_download", key=key, filename=filename)
        if content_type:
            result += "?" + urlencode({"content_type": content_type})
        return result

    async def upload_form(self, next_url: str) -> FileUploadForm:
        unique_key = str(generate_uuid())
        upload_url = ""
        if LocalStorage.prefix:
            upload_url += LocalStorage.prefix
        upload_url += router.url_path_for("storage_upload", key=unique_key)
        return FileUploadForm(
            action=upload_url,
            fields={
                "next": next_url,
            },
        )

    async def upload_target(self, *, content_type: str, max_bytes: int) -> UploadTarget:
        # No content-type/size enforcement locally — the upload endpoint trusts
        # the dev client. GCS enforces both via signed-POST policy conditions.
        unique_key = str(generate_uuid())
        upload_url = ""
        if LocalStorage.prefix:
            upload_url += LocalStorage.prefix
        upload_url += router.url_path_for("storage_upload", key=unique_key)
        return UploadTarget(action=upload_url, fields={}, key=unique_key)

    async def content_type(self, key: str) -> str:
        return "application/octet-stream"

    async def size(self, key: str) -> int:
        return await asyncio.to_thread(lambda: self._build_path(key).stat().st_size)

    async def checksum(self, key: str) -> str:
        def _read_and_hash() -> str:
            with open(self._build_path(key), "rb") as f:
                return hashlib.md5(f.read()).hexdigest()

        return await asyncio.to_thread(_read_and_hash)

    @staticmethod
    def _build_path(key: str) -> Path:
        storage_path = settings.local_storage_path
        storage_path.mkdir(parents=True, exist_ok=True)
        return storage_path / key


class GCSStorage(ServiceBase):
    bucket_name: str | None = None
    _bucket: storage.Bucket | None = None
    # Serializes credential refresh and first-touch bucket fetch across coroutines.
    # google.auth.default() returns process-cached credentials, and concurrent
    # credentials.refresh() calls would race on the shared token state.
    _refresh_lock: asyncio.Lock | None = None

    def __init__(self, bucket_name: str = settings.gcs_bucket):
        self.client = storage.Client()
        self.bucket_name = bucket_name

    @classmethod
    def _get_refresh_lock(cls) -> asyncio.Lock:
        if cls._refresh_lock is None:
            cls._refresh_lock = asyncio.Lock()
        return cls._refresh_lock

    async def get_bucket(self) -> storage.Bucket:
        if GCSStorage._bucket is not None:
            return GCSStorage._bucket
        async with self._get_refresh_lock():
            if GCSStorage._bucket is None:
                GCSStorage._bucket = await asyncio.to_thread(self.client.get_bucket, self.bucket_name)
        return GCSStorage._bucket

    def _prefixed_key(self, key: str) -> str:
        if settings.gcs_key_prefix:
            return f"{settings.gcs_key_prefix}/{key}"
        return key

    async def save(self, file: BinaryIO, filename: str, content_type: str) -> str:
        unique_key = self._prefixed_key(str(generate_uuid()))
        bucket = await self.get_bucket()
        blob = bucket.blob(unique_key)
        await asyncio.to_thread(blob.upload_from_file, file, content_type=content_type)
        file.seek(0)
        return unique_key

    async def save_streaming(
        self, stream: AsyncGenerator[bytes], filename: str, content_type: str
    ) -> tuple[str, int, str]:
        unique_key = self._prefixed_key(str(generate_uuid()))
        bucket = await self.get_bucket()
        blob = bucket.blob(unique_key)

        # Set chunk size to 10MB for efficient uploads of large files
        blob.chunk_size = 10 * 1024 * 1024

        md5_hash = hashlib.md5()
        byte_size = 0
        upload = await asyncio.to_thread(blob.open, mode="wb")

        try:
            async for chunk in stream:
                md5_hash.update(chunk)
                byte_size += len(chunk)
                await asyncio.to_thread(upload.write, chunk)
        except Exception:
            await asyncio.to_thread(upload.close)
            await asyncio.to_thread(blob.delete)
            raise

        await asyncio.to_thread(upload.close)

        return unique_key, byte_size, md5_hash.hexdigest()

    async def retrieve(self, key: str) -> bytes:
        bucket = await self.get_bucket()
        blob = bucket.blob(key)
        return await asyncio.to_thread(blob.download_as_bytes)

    async def url(self, key: str, filename: str, content_type: str | None = None) -> str:
        bucket = await self.get_bucket()
        blob = bucket.blob(key)
        credentials = await self._signing_credentials()
        disposition = "inline" if is_inline_content_type(content_type) else "attachment"

        def _generate() -> str:
            return blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=24),
                method="GET",
                response_disposition=f'{disposition}; filename="{filename}"',
                response_type=content_type,
                credentials=credentials,
            )

        return await asyncio.to_thread(_generate)

    async def upload_form(self, next_url: str) -> FileUploadForm:
        unique_key = self._prefixed_key(str(generate_uuid()))
        credentials = await self._signing_credentials()

        def _generate_policy() -> dict:
            return self.client.generate_signed_post_policy_v4(
                bucket_name=self.bucket_name,
                blob_name=unique_key,
                expiration=datetime.timedelta(minutes=15),
                credentials=credentials,
                fields={
                    "success_action_redirect": next_url,
                },
            )

        policy = await asyncio.to_thread(_generate_policy)

        return FileUploadForm(
            action=policy["url"],
            fields=policy["fields"],
        )

    async def upload_target(self, *, content_type: str, max_bytes: int) -> UploadTarget:
        unique_key = self._prefixed_key(str(generate_uuid()))
        credentials = await self._signing_credentials()

        def _generate_policy() -> dict:
            # `success_action_status` makes GCS return 201 (instead of redirecting)
            # so a cross-origin fetch can read response.ok. Content-Type is pinned
            # to an exact-match condition; content-length-range rejects empty or
            # oversized uploads at the bucket before they reach the backend.
            return self.client.generate_signed_post_policy_v4(
                bucket_name=self.bucket_name,
                blob_name=unique_key,
                expiration=datetime.timedelta(minutes=15),
                credentials=credentials,
                fields={
                    "Content-Type": content_type,
                    "success_action_status": "201",
                },
                conditions=[["content-length-range", 1, max_bytes]],
            )

        policy = await asyncio.to_thread(_generate_policy)

        return UploadTarget(action=policy["url"], fields=policy["fields"], key=unique_key)

    async def content_type(self, key: str) -> str:
        bucket = await self.get_bucket()
        blob = bucket.blob(key)
        await asyncio.to_thread(blob.reload)
        return blob.content_type

    async def size(self, key: str) -> int:
        bucket = await self.get_bucket()
        blob = bucket.blob(key)
        await asyncio.to_thread(blob.reload)
        if not blob.size:
            return 0

        return blob.size

    async def checksum(self, key: str) -> str:
        bucket = await self.get_bucket()
        blob = bucket.blob(key)
        await asyncio.to_thread(blob.reload)
        return blob.md5_hash

    async def _signing_credentials(self):
        def _build():
            # We have to impersonate ourselves to get credentials capable of signing
            # Application default credentials can't be used to sign
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/devstorage.read_only"],
            )

            if isinstance(credentials, impersonated_credentials.Credentials):
                return credentials

            credentials.refresh(requests.Request())

            # google.auth.default() returns base Credentials which lacks this in type stubs
            principal = getattr(credentials, "service_account_email", None)
            if principal is None:
                raise TypeError("Credentials do not support service account impersonation")

            return impersonated_credentials.Credentials(
                source_credentials=credentials,
                target_principal=principal,
                target_scopes=["https://www.googleapis.com/auth/devstorage.read_only"],
                lifetime=datetime.timedelta(minutes=1),
            )

        async with self._get_refresh_lock():
            return await asyncio.to_thread(_build)


ServiceClass = type[ServiceBase]
STORAGE_SERVICES: dict[StorageService, ServiceClass] = {
    StorageService.LOCAL: LocalStorage,
    StorageService.GCS: GCSStorage,
}

#
# File management
#
#

DEFAULT_CONTENT_TYPE = "application/octet-stream"


class FileReference(Model):
    id = fields.UUIDField(primary_key=True)
    key = fields.CharField(max_length=500)
    filename = fields.CharField(max_length=500)
    content_type = fields.CharField(max_length=100)
    metadata = fields.JSONField[dict](null=True)
    byte_size = fields.BigIntField(default=0)
    checksum = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    @classmethod
    async def from_key(cls, key: str):
        service = STORAGE_SERVICES[settings.storage_service]()
        content_type = await service.content_type(key)
        file_extension = mimetypes.guess_extension(content_type) or ""
        return cls(
            key=key,
            content_type=content_type,
            filename=f"{key}{file_extension}",
            byte_size=await service.size(key),
            checksum=await service.checksum(key),
        )

    @classmethod
    async def upload_target(cls, *, content_type: str, max_bytes: int) -> UploadTarget:
        service = STORAGE_SERVICES[settings.storage_service]()
        return await service.upload_target(content_type=content_type, max_bytes=max_bytes)

    async def url(self) -> str:
        service = STORAGE_SERVICES[settings.storage_service]()
        return await service.url(self.key, self.filename, self.content_type)

    async def attach(self, file: BinaryIO, filename: str, content_type: str):
        validate_file(file, content_type)

        contents = file.read()
        file.seek(0)

        filename = sanitize_filename(filename)
        self.filename = filename
        self.content_type = content_type
        self.checksum = hashlib.md5(contents).hexdigest()
        self.byte_size = len(contents)

        service = STORAGE_SERVICES[settings.storage_service]()
        key = await service.save(file, filename, content_type)
        self.key = key

    async def attach_stream(self, stream: AsyncGenerator[bytes], filename: str, content_type: str):
        filename = sanitize_filename(filename)
        self.filename = filename
        self.content_type = content_type

        # Peek the first chunk to validate the file type
        first_chunk = await stream.__anext__()
        validate_file(io.BytesIO(first_chunk), content_type)

        async def patched_stream():
            yield first_chunk
            async for chunk in stream:
                yield chunk

        service = STORAGE_SERVICES[settings.storage_service]()
        key, byte_size, checksum = await service.save_streaming(patched_stream(), filename, content_type)

        self.key = key
        self.byte_size = byte_size
        self.checksum = checksum

    async def download(self) -> bytes:
        service = STORAGE_SERVICES[settings.storage_service]()
        return await service.retrieve(self.key)

    async def copy(self, using_db: BaseDBAsyncClient | None = None):
        result = self.clone()
        result.id = generate_uuid()
        result.created_at = None  # type: ignore
        result.updated_at = None  # type: ignore
        content = await self.download()
        await result.attach(TrustedBytesIO(content), self.filename, self.content_type)

        await result.save(using_db=using_db)
        return result

    @asynccontextmanager
    async def download_to_tempfile(self, **kwargs) -> AsyncIterator[tempfile._TemporaryFileWrapper]:
        content = await self.download()
        with tempfile.NamedTemporaryFile(mode="w+", **kwargs) as temp_file:
            temp_file.write(content.decode())
            temp_file.flush()
            temp_file.seek(0)
            yield temp_file


async def store_file(content: BinaryIO, filename: str | None, content_type: str | None) -> FileReference:
    if not filename:
        filename = DEFAULT_FILENAME
    if not content_type:
        content_type = DEFAULT_CONTENT_TYPE

    file_reference = FileReference()
    await file_reference.attach(content, filename, content_type)
    await file_reference.save()
    return file_reference


async def store_file_from_stream(
    streaming_response: httpx.Response,
    filename: str | None = None,
    content_type: str | None = None,
    chunk_size: int = 10 * 1024 * 1024,  # 10MB chunks by default
) -> FileReference:
    if not filename:
        filename = DEFAULT_FILENAME
    if not content_type:
        content_type = DEFAULT_CONTENT_TYPE

    async def stream_chunks() -> AsyncGenerator[bytes]:
        async for chunk in streaming_response.aiter_bytes(chunk_size=chunk_size):
            yield chunk

    file_reference = FileReference()
    try:
        await file_reference.attach_stream(stream_chunks(), filename, content_type)
        await file_reference.save()
    except Exception as e:
        logger.error(f"Failed to store file from streaming: {e}")
        if file_reference._saved_in_db:
            await file_reference.delete()
        raise e

    logger.info(f"Stored file {file_reference.key} with filename {filename} after streaming")

    return file_reference


async def store_file_from_string(
    content: str, filename: str | None = None, content_type: str | None = None
) -> FileReference:
    bytes_io: BinaryIO
    if isinstance(content, TrustedStr):
        bytes_io = TrustedBytesIO(content.encode())
    else:
        bytes_io = io.BytesIO(content.encode())
    return await store_file(bytes_io, filename, content_type)
