FROM public.ecr.aws/lambda/python:3.13

RUN dnf install -y tar xz wget && \
    mkdir -p /ffmpeg && \
    cd /ffmpeg && \
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz && \
    tar -xvf ffmpeg-release-amd64-static.tar.xz && \
    mv ffmpeg-*-amd64-static/ffmpeg ffmpeg-*-amd64-static/ffprobe . && \
    chmod +x ffmpeg ffprobe

ENV PATH="/ffmpeg:${PATH}"

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY transcoder.py lambda_function.py ./

CMD ["lambda_function.lambda_handler"]
