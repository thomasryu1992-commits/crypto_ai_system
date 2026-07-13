# Crypto AI System Agent Package runtime for Thomas Agent OS Local Launcher.
# This container is review-only by default and never enables live trading or real order execution.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CRYPTO_AI_SYSTEM_CONTAINER_MODE=local_launcher \
    PYTHONPATH=/app/crypto_ai_system/src:/app/crypto_ai_system

WORKDIR /app/crypto_ai_system

COPY requirements.txt pyproject.toml ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME ["/app/crypto_ai_system/data/reports", "/app/crypto_ai_system/storage"]

ENTRYPOINT ["python", "scripts/run_command.py"]
CMD ["--command", "daily", "--dry-run"]
