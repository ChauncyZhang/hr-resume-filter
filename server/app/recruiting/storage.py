from typing import Protocol


MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_PREVIEW_BYTES = 1024 * 1024


class StorageReadFailed(Exception):
    pass


class StorageObjectTooLarge(Exception):
    pass


class PrivateResumeStorage(Protocol):
    def read_download(self, storage_key: str, max_bytes: int = MAX_DOWNLOAD_BYTES) -> bytes: ...


class MinioResumeStorage:
    def __init__(self, client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def read_download(self, storage_key: str, max_bytes: int = MAX_DOWNLOAD_BYTES) -> bytes:
        response = None
        try:
            response = self.client.get_object(self.bucket, storage_key)
            chunks: list[bytes] = []
            total = 0
            for chunk in response.stream(64 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise StorageObjectTooLarge
                chunks.append(chunk)
            return b"".join(chunks)
        except StorageObjectTooLarge:
            raise
        except Exception as error:
            raise StorageReadFailed from error
        finally:
            if response is not None:
                response.close()
                response.release_conn()
