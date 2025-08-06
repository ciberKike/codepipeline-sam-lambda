FROM public.ecr.aws/docker/library/python:3.13

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    pip install boto3 pytest && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

CMD ["python", "worker.py"]
