FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# El build context es la raiz del monorepo.
COPY shared /shared
COPY backend/pyproject.toml ./pyproject.toml

RUN uv pip install --system -e /shared && uv pip install --system .

COPY backend/ .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
