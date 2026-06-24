#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# run-monthly.sh — Atualiza o container e executa o relatório.
#
# Fluxo (chamado pelo agendamento do dia 26):
#   1. Baixa a imagem mais recente (pull)  — build vem do GitHub Action
#   2. Recria o container com a nova imagem (up -d)
#   3. Executa o relatório dentro do container (docker exec)
#
# Uso:  ./run-monthly.sh
# ═══════════════════════════════════════════════════════════════

set -uo pipefail

# ── Configuração ──────────────────────────────────────────────
PROJECT_DIR="/home/blocktime/relatorio_365"

# container_name definido no docker-compose.yaml
# (ajuste se o nome no seu compose for diferente)
CONTAINER_NAME="relatorio_office365"

# Comando que gera o relatório dentro do container
APP_COMMAND="python src/main.py"

# ── Acessa a pasta do projeto ─────────────────────────────────
cd "${PROJECT_DIR}" || {
    echo "ERRO: não foi possível acessar ${PROJECT_DIR}"
    exit 1
}

# Detecta o nome do arquivo compose (.yaml ou .yml)
if [ -f "docker-compose.yaml" ]; then
    COMPOSE_FILE="docker-compose.yaml"
elif [ -f "docker-compose.yml" ]; then
    COMPOSE_FILE="docker-compose.yml"
else
    echo "ERRO: docker-compose.yaml/.yml não encontrado em ${PROJECT_DIR}"
    exit 1
fi

# ── 1. Baixa a imagem mais recente ────────────────────────────
echo "======================================="
echo "1/3  Baixando a imagem mais recente"
echo "======================================="
if ! docker compose -f "${COMPOSE_FILE}" pull; then
    echo "ERRO: falha ao baixar a imagem (docker login? nome/tag corretos?)"
    exit 1
fi

# ── 2. Recria o container com a nova imagem ───────────────────
echo "======================================="
echo "2/3  Recriando o container com a nova imagem"
echo "======================================="
if ! docker compose -f "${COMPOSE_FILE}" up -d; then
    echo "ERRO: falha ao recriar o container."
    exit 1
fi

# Aguarda o container ficar de pé antes do exec
echo "Aguardando o container ficar pronto..."
for i in $(seq 1 15); do
    if [ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null)" = "true" ]; then
        echo "Container '${CONTAINER_NAME}' está rodando."
        break
    fi
    sleep 2
    if [ "$i" -eq 15 ]; then
        echo "ERRO: container '${CONTAINER_NAME}' não ficou pronto a tempo."
        echo "      Verifique o container_name no compose e o estado com: docker ps"
        exit 1
    fi
done

# ── 3. Executa o relatório dentro do container ────────────────
echo "======================================="
echo "3/3  Executando o relatório"
echo "======================================="
docker exec "${CONTAINER_NAME}" ${APP_COMMAND}
EXIT_CODE=$?

echo
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Relatório executado com sucesso."
else
    echo "❌ O relatório finalizou com erro (código: ${EXIT_CODE})."
fi
exit $EXIT_CODE