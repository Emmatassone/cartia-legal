FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# El build context es la raiz del monorepo.
COPY shared /shared
COPY rag-loader/pyproject.toml ./pyproject.toml

RUN uv pip install --system -e /shared && uv pip install --system .

COPY rag-loader/ .

# Los documentos se montan aca (volumen local en Tilt, bucket/volumen en GCP).
ENV DOCUMENTS_DIR=/app/documents

EXPOSE 8003
# Por defecto levanta la API on-demand. Para correr una ingesta puntual:
#   docker run ... python -m app.cli ingest ./documents
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
