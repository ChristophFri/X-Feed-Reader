FROM python:3.11-slim
WORKDIR /app

# Copy project files
COPY . .

# Install package with web dependencies (no CLI Playwright needed in cloud)
RUN pip install --no-cache-dir ".[web]"

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
