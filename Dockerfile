FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y \
        ffmpeg \
        cmake \
        build-essential \
        libgl1 \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend /app

ENV LOG_LEVEL=INFO PORT=10000 HOST=0.0.0.0

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
