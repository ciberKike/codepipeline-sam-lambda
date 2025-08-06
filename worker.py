"""
Worker SQS → FFmpeg Transcoder
--------------------------------
- Lee mensajes de una cola SQS de ENTRADA
- Descarga el vídeo de S3, ejecuta transcode.py y sube resultados
- Envía un mensaje a la cola SQS de SALIDA al terminar
- Manejo de errores con reintentos y DLQ

Variables de entorno esperadas
------------------------------
AWS_REGION                eu-west-1 (por defecto)
LOCALSTACK_URL            http://localstack:4566   (solo en dev)
SQS_INPUT_QUEUE_NAME      transcode-queue
SQS_OUTPUT_QUEUE_NAME     transcode-done-queue
SQS_DLQ_QUEUE_NAME        transcode-dlq            (opcional pero recomendado)
TARGET_HEIGHT             720
PROD_FORMAT               50
MAX_RETRIES               3                        (reintentos antes de enviar a DLQ)
VISIBILITY_TIMEOUT        120                      (segundos)
WAIT_TIME_SECONDS         20                       (long polling)

Dependencias: boto3, botocore
"""

"""Modular worker version using Settings. Keeps logic isolated and testable."""
import os, json, time, uuid, logging, tempfile
from typing import Dict, Any, List
import boto3, botocore.exceptions
from config import Settings
from processor import process_single_file

logger = logging.getLogger("transcoder-worker")
logger.setLevel(logging.INFO)


def build_paths(
    tenant: str, sport: str, competition: str, event: str
) -> Dict[str, str]:
    """Return S3 prefixes for originals and transcoded folders."""
    base = f"{tenant}/{sport}/{competition}/{event}/videos"
    return {"originals": f"{base}/originals", "transcoded": f"{base}/transcoded"}


def upload_file(s3, file: str, bucket: str, prefix: str) -> List[str]:
    """Upload local file to S3 and return their keys."""
    rel = os.path.basename(file)
    key = os.path.join(prefix, f"{uuid.uuid4()}_{rel}")
    s3.upload_file(file, bucket, key)
    return key


def upload_files(s3, files: List[str], bucket: str, prefix: str) -> List[str]:
    """Upload local files to S3 and return their keys."""
    uploaded = []
    for f in files:
        key = upload_file(s3, f, bucket, prefix)
        uploaded.append(key)
    return uploaded


def handle_event(s3, body: Dict[str, Any], settings: Settings) -> Dict[str, Any]:
    """Handle a single SQS message body: download, (maybe) transcode, upload, return payload."""
    paths = build_paths(body["tenant"], body["sport"], body["competition"], body["event"])
    s3_key = body.get("s3_key") or f"{paths['originals']}/{os.path.basename(body['filename'])}"
    target_height = body.get("height")
    prod_format = body.get("format", settings.prod_format)

    with tempfile.TemporaryDirectory() as tmpd:
        local_input = os.path.join(tmpd, os.path.basename(s3_key))
        s3.download_file(settings.bucket, s3_key, local_input)
        output_root = os.path.join(tmpd, "transcoded_files")
        os.makedirs(output_root, exist_ok=True)

        try:
            file = process_single_file(local_input, target_height, prod_format, output_root)
        except Exception as exc:
            # Fallback strategy: keep original and mark error so API can decide what to do
            return {
                **body,
                "bucket": settings.bucket,
                "original_key": s3_key,
                "transcoded": False,
                "file": s3_key,
                "status": "ERROR_TRANSCODE",
                "error": str(exc),
                "processed_at": int(time.time()),
            }

        if not file:
            # No transcode required
            return {
                **body,
                "bucket": settings.bucket,
                "original_key": s3_key,
                "transcoded": False,
                "file": s3_key,
                "status": "DONE",
                "processed_at": int(time.time()),
            }

        uploaded = upload_file(s3, file, settings.bucket, paths["transcoded"])
        return {
            **body,
            "bucket": settings.bucket,
            "original_key": s3_key,
            "transcoded": True,
            "file": uploaded,
            "status": "DONE",
            "processed_at": int(time.time()),
        }


def main_loop():
    """Infinite loop that polls SQS, processes messages, handles retries/DLQ."""
    st = Settings.from_env()
    client_kwargs = {"region_name": st.region}
    if st.localstack_url:
        client_kwargs["endpoint_url"] = st.localstack_url
    sqs = boto3.client("sqs", **client_kwargs)
    s3 = boto3.client("s3", **client_kwargs)

    def get_url(name: str, timeout: int = 60) -> str:
        """Return the QueueUrl by name, waiting until it exists (dev friendly)."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                return sqs.get_queue_url(QueueName=name)["QueueUrl"]
            except botocore.exceptions.ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in (
                    "AWS.SimpleQueueService.NonExistentQueue",
                    "QueueDoesNotExist",
                ):
                    time.sleep(2)
                    continue
                raise
        raise TimeoutError(f"Queue {name} not found after {timeout}s")

    # Prefer explicit URLs from env to avoid race conditions; fallback to lookup
    input_url = os.getenv("SQS_INPUT_QUEUE_URL") or get_url(st.input_queue_name)
    output_url = os.getenv("SQS_OUTPUT_QUEUE_URL") or get_url(st.output_queue_name)
    dlq_url_env = os.getenv("SQS_DLQ_QUEUE_URL")
    dlq_url = dlq_url_env or (get_url(st.dlq_queue_name) if st.dlq_queue_name else None)

    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=input_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=st.wait_time_seconds,
                VisibilityTimeout=st.visibility_timeout,
                AttributeNames=["ApproximateReceiveCount"],
            )
        except Exception:
            logger.exception("Error receiving from SQS. Retrying in 5s...")
            time.sleep(5)
            continue

        messages = resp.get("Messages", [])
        if not messages:
            continue

        for m in messages:
            receipt = m["ReceiptHandle"]
            rc = int(m.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            try:
                payload = handle_event(s3, json.loads(m["Body"]), st)
                sqs.send_message(QueueUrl=output_url, MessageBody=json.dumps(payload))
                sqs.delete_message(QueueUrl=input_url, ReceiptHandle=receipt)
            except Exception as e:  # noqa
                logger.exception("Processing error")
                if rc >= st.max_retries and dlq_url:
                    body = json.loads(m["Body"])
                    body["error"] = str(e)
                    body["failed_at"] = int(time.time())
                    sqs.send_message(QueueUrl=dlq_url, MessageBody=json.dumps(body))
                    sqs.delete_message(QueueUrl=input_url, ReceiptHandle=receipt)
                else:
                    # Let it reappear later, optionally reduce visibility timeout
                    try:
                        sqs.change_message_visibility(
                            QueueUrl=input_url,
                            ReceiptHandle=receipt,
                            VisibilityTimeout=min(st.visibility_timeout, 30 * rc),
                        )
                    except Exception:
                        logger.warning(
                            "Could not change visibility timeout; default will apply"
                        )


if __name__ == "__main__":
    main_loop()
