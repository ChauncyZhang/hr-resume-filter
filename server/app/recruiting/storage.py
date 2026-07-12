from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True)
class StoredDownload:
    chunks: Iterable[bytes]
    content_type: str
    filename: str


class PrivateResumeStorage(Protocol):
    def read_preview(self, storage_key: str) -> str: ...
    def stream_download(self, storage_key: str, content_type: str, filename: str) -> StoredDownload: ...


class MinioResumeStorage:
    def __init__(self, client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def read_preview(self, storage_key: str) -> str:
        response = self.client.get_object(self.bucket, storage_key)
        try:
            return response.read().decode("utf-8", errors="replace")
        finally:
            response.close()
            response.release_conn()

    def stream_download(self, storage_key: str, content_type: str, filename: str) -> StoredDownload:
        response = self.client.get_object(self.bucket, storage_key)

        def chunks():
            try:
                yield from response.stream(64 * 1024)
            finally:
                response.close()
                response.release_conn()

        return StoredDownload(chunks(), content_type, filename)
