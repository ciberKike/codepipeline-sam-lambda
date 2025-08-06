# Transcoder Service

Python/FFmpeg microservice that consumes SQS messages, downloads source videos from a single S3 bucket, decides whether to transcode or just copy, uploads results, and posts a completion message to a “done” queue. Designed to run locally (Docker + LocalStack) and in production (AWS Lambda container or ECS/EC2).

> All code comments and docs are in English.

---

## 1. Features

* **SQS → Worker loop** with long polling, retries and DLQ support.
* **Single S3 bucket** with hierarchical paths: `tenant/sport/competition/event/videos/{originals|transcoded}`.
* **Conditional transcode**: if height/FPS already match, it only copies the file.
* **Robust FFmpeg wrapper** with error capture (`FFmpegError`) and fallback behavior (`ERROR_TRANSCODE`).
* **Modular codebase**: `config`, `ffutils`, `processor`, `worker`.
* **Unit tests** (pytest + mocks) included.

---

## 2. Repository Layout

```
transcoder/
├─ docker/
│  ├─ development/
│  │  ├─ Dockerfile           # Dev build (service)
│  │  └─ Dockerfile.tests     # Dev test runner
│  └─ Dockerfile              # (optional) prod image
├─ tests/
│  ├─ test_ffutils.py
│  ├─ test_processor.py
│  └─ test_worker_handle_event.py
├─ __init__.py
├─ config.py                  # Settings loader (env vars)
├─ ffutils.py                 # ffprobe/ffmpeg helpers
├─ processor.py               # Core logic (copy vs transcode)
├─ worker.py                  # SQS loop (refactored)
├─ main.py                    # CLI helper for local one-shot runs
├─ requirements.txt
├─ requirements-dev.txt
└─ README.md (this file)
```

---

## 3. Requirements

* Python 3.10+
* FFmpeg (ffmpeg/ffprobe binaries reachable in PATH)
* Docker & Docker Compose (for local dev)
* LocalStack (mock AWS) or real AWS account for prod

---

## 4. Environment Variables

| Var                     | Default                | Description                                               |
| ----------------------- | ---------------------- | --------------------------------------------------------- |
| `AWS_REGION`            | `eu-west-1`            | AWS region for clients                                    |
| `LOCALSTACK_URL`        | *(unset)*              | Endpoint for LocalStack (e.g., `http://localstack:4566`)  |
| `S3_BUCKET`             | `media`                | Single S3 bucket name                                     |
| `SQS_INPUT_QUEUE_NAME`  | `transcode-queue`      | Input queue name                                          |
| `SQS_OUTPUT_QUEUE_NAME` | `transcode-done-queue` | Output queue (DONE)                                       |
| `SQS_DLQ_QUEUE_NAME`    | `transcode-dlq`        | Dead-letter queue name                                    |
| `SQS_INPUT_QUEUE_URL`   | *(unset)*              | Explicit URL (skip lookup)                                |
| `SQS_OUTPUT_QUEUE_URL`  | *(unset)*              | Explicit URL (skip lookup)                                |
| `SQS_DLQ_QUEUE_URL`     | *(unset)*              | Explicit URL (skip lookup)                                |
| `MAX_RETRIES`           | `3`                    | Retries before sending to DLQ                             |
| `VISIBILITY_TIMEOUT`    | `120`                  | Seconds (SQS receive)                                     |
| `WAIT_TIME_SECONDS`     | `20`                   | Long polling wait                                         |
| `MAX_WIDTH`             | `3840`                 | (Optional) clamp width when scaling, to avoid huge widths |

---

## 5. Message Schema

### Input (to `transcode-queue`)

```json
{
  "tenant": "tenantA",
  "sport": "football",
  "competition": "laliga",
  "event": "2025-07-01-barca-madrid",
  "filename": "clip.mp4",          // used if s3_key is not provided
  "s3_key": "tenantA/football/laliga/2025-07-01-barca-madrid/videos/originals/clip.mp4", // optional
  "height": 100,
  "format": "50"
}
```

### Output (to `transcode-done-queue`)

```json
{
  "tenant": "tenantA",
  "sport": "football",
  "competition": "laliga",
  "event": "2025-07-01-barca-madrid",
  "bucket": "media",
  "original_key": "tenantA/.../videos/originals/clip.mp4",
  "transcoded": true,
  "file": "tenantA/.../videos/transcoded/uuid_clip_1280x720.mp4",
  "status": "DONE",
  "processed_at": 1721680000
}
```

If FFmpeg fails:

```json
{
  "status": "ERROR_TRANSCODE",
  "error": "ffmpeg failed (rc=1): ...",
  "transcoded": false,
  "file": "<original_key>"
}
```

---

## 6. Local Development

### 6.1 With docker-compose (recommended)

This service is usually run via the `amc-dev` monorepo. If you run it standalone:

```bash
docker compose up -d --build transcoder localstack
```

* `localstack-setup.sh` (from the monorepo) creates `media` bucket and the SQS queues.
* The worker will block/wait until queues exist; otherwise define `SQS_*_QUEUE_URL` env vars.

### 6.2 Manually send a test message

```bash
docker compose exec localstack awslocal s3 cp ./sample.mp4 s3://media/tenantA/football/laliga/match1/videos/originals/sample.mp4

docker compose exec localstack awslocal sqs send-message \
  --queue-url http://localhost:4566/000000000000/transcode-queue \
  --message-body '{
    "tenant":"tenantA","sport":"football","competition":"laliga","event":"match1",
    "filename":"sample.mp4","height":100,"format":"50"
  }'
```

Tail logs:

```bash
docker compose logs -f transcoder
```

Peek done queue:

```bash
make sqs-peek QUEUE=transcode-done-queue
```

---

## 7. Running Tests

### 7.1 Inside Docker

```bash
# Build test image
docker build -f docker/development/Dockerfile.tests -t transcoder-tests .
# Run tests
docker run --rm -e PYTHONPATH=/app transcoder-tests
```

### 7.2 Locally (no docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q --disable-warnings --maxfail=1
```

### 7.3 Coverage

```bash
pytest --cov=. --cov-report=term-missing
```

---

## 8. Deployment Options

**Lambda (container image):**

* Build image with ffmpeg inside (static bin or layer copied to `/opt`).
* Add SQS trigger; max duration 15 min, <=10GB RAM. Perfect for <=10MB / 30s clips.

**ECS/Fargate:**

* Long-running worker service pulling from SQS; scalable by task count.
* Good for larger/longer videos or when you need custom scaling.

**AWS MediaConvert:**

* Managed service; pay-per-minute transcode, advanced presets, ABR, etc.
* Simpler ops, but higher cost vs self-hosted ffmpeg for very small clips.

---

## 9. Troubleshooting

| Symptom                               | Cause                                         | Action                                                                                  |
| ------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------- |
| `QueueDoesNotExist`                   | Queues not created yet                        | Ensure LocalStack init script or use `wait_for_queue_url` (built-in)                    |
| `FFmpegError: invalid width x height` | Extreme aspect ratio -> width > encoder limit | Clamp width (`MAX_WIDTH`), compute scale in Python or use `force_original_aspect_ratio` |
| Messages reappear                     | Not deleting or visibility too short          | We call `delete_message`; adjust `VISIBILITY_TIMEOUT`                                   |
| `ffmpeg: not found`                   | Missing ffmpeg in container                   | Install via apt/yum or copy static binary in Dockerfile                                 |
| Wrong S3 paths                        | Missing tenant/sport/... fields               | Validate input JSON before processing                                                   |

---

## 10. Contributing

* Keep test coverage for new modules.
* Follow the existing style: small functions, clear error paths, environment-driven config.
* PRs should include an update to this README if you add new features/env vars.

---

Happy transcoding! 🎬🚀
