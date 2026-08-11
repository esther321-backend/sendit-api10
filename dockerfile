FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt-get/lists/*

RUN pip install uv

COPY . .

RUN uv venv && . .venv/bin/activate && uv pip install fastapi uvicorn sqlmodel psycopg2-binary alembic python-dotenv httpx aiofiles slowapi "passlib[bcrypt]" "python-jose[cryptography]" psutil pytest python-multipart

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
