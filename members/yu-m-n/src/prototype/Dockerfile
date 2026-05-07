FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 시스템 의존성 (PyMuPDF 빌드에 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmupdf-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

# api/index.py 의 FastAPI app 객체 서빙
CMD ["sh", "-c", "uvicorn api.index:app --host 0.0.0.0 --port ${PORT} --workers 1"]