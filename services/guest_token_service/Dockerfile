FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/guest_token_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/guest_token_service/main.py .
COPY web /app/web

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
