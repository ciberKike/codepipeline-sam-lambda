"""Load and validate configuration from environment variables.
Separates config parsing from business logic to make testing and local usage easier.
"""

from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    region: str = "eu-west-1"
    localstack_url: str | None = None

    # SQS
    input_queue_name: str = "transcode-queue"
    output_queue_name: str = "transcode-done-queue"
    dlq_queue_name: str = "transcode-dlq"

    # S3
    bucket: str = "media"

    # Transcoding
    target_height: int = 720
    prod_format: str = "50"  # "50" or "60"
    max_retries: int = 3
    visibility_timeout: int = 120
    wait_time_seconds: int = 20

    @staticmethod
    def from_env() -> "Settings":
        def _int(name: str, default: int) -> int:
            return int(os.getenv(name, default))

        return Settings(
            region=os.getenv("AWS_REGION", "eu-west-1"),
            localstack_url=os.getenv("LOCALSTACK_URL"),
            input_queue_name=os.getenv("SQS_INPUT_QUEUE_NAME", "transcode-queue"),
            output_queue_name=os.getenv(
                "SQS_OUTPUT_QUEUE_NAME", "transcode-done-queue"
            ),
            dlq_queue_name=os.getenv("SQS_DLQ_QUEUE_NAME", "transcode-dlq"),
            bucket=os.getenv("S3_BUCKET", "media"),
            prod_format=os.getenv("PROD_FORMAT", "50"),
            max_retries=_int("MAX_RETRIES", 3),
            visibility_timeout=_int("VISIBILITY_TIMEOUT", 120),
            wait_time_seconds=_int("WAIT_TIME_SECONDS", 20),
        )
