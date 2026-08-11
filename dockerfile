FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt-get/lists/*

# Install UV package manager
RUN pip install uv

# Copy dependencies definitions
COPY pyproject.toml uv.lock* ./

# Install python dependencies
RUN uv venv && . .venv/bin/activate && uv pip install fastapi uvicorn sqlmodel psycopg2-binary alembic python-dotenv httpx aiofiles slowapi "passlib[bcrypt]" "python-jose[cryptography]" psutil

# Copy application code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Run Uvicorn server
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
