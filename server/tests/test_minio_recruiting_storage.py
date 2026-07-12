import io
import os
from uuid import uuid4

import pytest
from minio import Minio
from minio.error import S3Error

from server.app.recruiting.storage import MinioResumeStorage
from server.app.screening.storage import QuarantineStorage


@pytest.mark.skipif(not os.getenv("MINIO_SMOKE_ENDPOINT"), reason="MinIO smoke endpoint not configured")
def test_live_minio_private_object_round_trip() -> None:
    client = Minio(
        os.environ["MINIO_SMOKE_ENDPOINT"],
        access_key=os.environ["MINIO_SMOKE_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SMOKE_SECRET_KEY"],
        secure=False,
    )
    bucket = f"ux09-{uuid4().hex}"
    key = f"private/{uuid4()}"
    body = b"first-chunk-second-chunk"
    client.make_bucket(bucket)
    try:
        client.put_object(bucket, key, io.BytesIO(body), len(body), content_type="application/pdf")
        spool = MinioResumeStorage(client, bucket).open_download(key)
        try:
            assert spool.read() == body
        finally:
            spool.close()
        with pytest.raises(S3Error) as error:
            client.get_bucket_policy(bucket)
        assert error.value.code == "NoSuchBucketPolicy"
    finally:
        client.remove_object(bucket, key)
        client.remove_bucket(bucket)

@pytest.mark.skipif(not os.getenv("MINIO_SMOKE_ENDPOINT"), reason="MinIO smoke endpoint not configured")
def test_live_minio_quarantine_streaming_write_delete() -> None:
    client=Minio(os.environ["MINIO_SMOKE_ENDPOINT"],access_key=os.environ["MINIO_SMOKE_ACCESS_KEY"],secret_key=os.environ["MINIO_SMOKE_SECRET_KEY"],secure=False); bucket=f"ux09-q-{uuid4().hex}"; client.make_bucket(bucket); key=f"quarantine/{uuid4()}/{uuid4()}/{uuid4()}"; storage=QuarantineStorage(client,bucket)
    try:
        storage.write(io.BytesIO(b"private-quarantine"),key,"text/plain",1024); response=client.get_object(bucket,key)
        try: assert response.read()==b"private-quarantine"
        finally: response.close(); response.release_conn()
        storage.delete(key)
        with pytest.raises(S3Error) as missing: client.stat_object(bucket,key)
        assert missing.value.code in {"NoSuchKey","NoSuchObject"}
    finally: client.remove_bucket(bucket)
