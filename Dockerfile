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
        wget \
        ca-certificates \
    && wget -q https://github.com/PowerShell/PowerShell/releases/download/v7.6.3/powershell_7.6.3-1.deb_amd64.deb \
        -O powershell.deb \
    && dpkg -i powershell.deb || true \
    && apt-get install -y -f \
    && rm powershell.deb \
    && rm -rf /var/lib/apt/lists/*

# Módulo do Exchange Online, usado pelo NativeForwardingCollector para ler
# o encaminhamento nativo de caixa (ForwardingSmtpAddress/ForwardingAddress),
# dado que a Graph API não expõe.
RUN pwsh -NoProfile -Command \
    "Install-Module -Name ExchangeOnlineManagement -Force -Scope AllUsers -Repository PSGallery"

# Falha o build cedo se o módulo não carregar, em vez de só descobrir isso
# em produção na primeira execução do collector.
RUN pwsh -NoProfile -Command \
    "Import-Module ExchangeOnlineManagement -ErrorAction Stop; Write-Host 'ExchangeOnlineManagement OK'"

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