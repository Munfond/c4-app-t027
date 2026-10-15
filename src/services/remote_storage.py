"""Private S3-compatible artifact storage; only server-generated keys are accepted."""

import hashlib
from functools import lru_cache, wraps

from botocore.exceptions import BotoCoreError, ClientError

from src.config import get_settings


class StorageUnavailableError(RuntimeError):
    pass


def storage_operation(operation):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError("Remote storage is unavailable; check backend configuration") from exc
    return wrapped


@lru_cache(maxsize=4)
def client(endpoint, region, access, secret):
    import boto3
    from botocore.config import Config

    return boto3.client("s3", endpoint_url=endpoint or None, region_name=region,
                        aws_access_key_id=access or None, aws_secret_access_key=secret or None,
                        config=Config(signature_version="s3v4", retries={"max_attempts": 2},
                                      connect_timeout=10, read_timeout=30))


def storage():
    settings = get_settings()
    if not settings.remote_storage_bucket:
        raise StorageUnavailableError("REMOTE_STORAGE_BUCKET is required")
    return client(settings.remote_storage_endpoint, settings.remote_storage_region,
                  settings.remote_storage_access_key, settings.remote_storage_secret_key)


@storage_operation
def ticket(record):
    params = {"Bucket": get_settings().remote_storage_bucket, "Key": record["object_key"],
              "ContentLength": record["bytes"], "Metadata": {"sha256": record["sha256"]}}
    return {"path": record["path"], "url": storage().generate_presigned_url("put_object", Params=params, ExpiresIn=900),
            "headers": {"x-amz-meta-sha256": record["sha256"]}}


@storage_operation
def read(record):
    response = storage().get_object(Bucket=get_settings().remote_storage_bucket, Key=record["object_key"])
    stream = response["Body"]
    try:
        if response["ContentLength"] != record["bytes"]:
            raise ValueError("Artifact size mismatch")
        raw = stream.read(record["bytes"] + 1)
        if len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("Artifact integrity check failed")
        return raw
    finally:
        stream.close()


@storage_operation
def verify(record):
    response = storage().get_object(Bucket=get_settings().remote_storage_bucket, Key=record["object_key"])
    stream = response["Body"]
    try:
        if response["ContentLength"] != record["bytes"]:
            raise ValueError("Artifact size mismatch")
        digest, size = hashlib.sha256(), 0
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > record["bytes"]:
                raise ValueError("Artifact exceeds registered size")
            digest.update(chunk)
        if size != record["bytes"] or digest.hexdigest() != record["sha256"]:
            raise ValueError("Artifact integrity check failed")
    finally:
        stream.close()
