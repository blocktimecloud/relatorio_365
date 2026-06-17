# ═══════════════════════════════════════════════════════════════
# Dockerfile — Blocktime Office 365 Reports
# Python 3.13 + Poetry + WeasyPrint (Pango/Cairo)
# ═══════════════════════════════════════════════════════════════

# ---------- Stage 1: builder (instala dependências) ----------
FROM python:3.13-slim AS builder

# Poetry exporta as deps para um requirements; instalamos num venv isolado
ENV POETRY_VERSION=2.0.1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install "poetry==${POETRY_VERSION}" poetry-plugin-export

WORKDIR /app

# Copia só os arquivos de dependência primeiro (melhora cache de build)
COPY pyproject.toml poetry.lock ./

# Exporta as dependências para requirements.txt (sem as dev) e instala num venv
RUN poetry export --without-hashes --format=requirements.txt --output=requirements.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ---------- Stage 2: runtime (imagem final, enxuta) ----------
FROM python:3.13-slim AS runtime

# Bibliotecas de sistema que o WeasyPrint precisa em runtime:
# - libpango / libcairo / libgdk-pixbuf: renderização de texto e gráficos
# - libffi: usada pela cryptography/cffi
# - fonts: para o PDF ter fontes disponíveis (DejaVu cobre acentuação PT-BR)
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

# Copia o venv já montado no builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copia o código da aplicação
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY assets/ ./assets/

# Usuário não-root (boa prática de segurança)
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/reports /app/logs \
    && chown -R appuser:appuser /app
USER appuser

# Comando padrão: gera os relatórios de todos os clientes ativos.
# O CronJob do Kubernetes sobrescreve isso quando precisa (command:).
CMD ["python", "src/main.py"]