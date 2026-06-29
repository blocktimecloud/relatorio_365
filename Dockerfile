# ═══════════════════════════════════════════════════════════════
# Dockerfile — Blocktime Office 365 Reports
# Python 3.13 + WeasyPrint (Pango/Cairo)
# ═══════════════════════════════════════════════════════════════

# ---------- Stage 1: builder ----------
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copia apenas o requirements para aproveitar cache
COPY requirements.txt ./

# Instala as dependências em um ambiente virtual
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ---------- Stage 2: runtime ----------
FROM python:3.13-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copia o ambiente virtual
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copia a aplicação
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY assets/ ./assets/

# Copia o arquivo de variáveis de ambiente
COPY .env ./

# Usuário não-root
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/reports /app/logs \
    && chown -R appuser:appuser /app

USER appuser

CMD ["sleep", "infinity"]