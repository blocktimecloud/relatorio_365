"""
Serviço de disparo: recebe achados e abre chamados no Desk via Maestro.
Tolerante a falhas — registra o que abriu e o que falhou, sem abortar.
"""

from integrations.maestro.client import MaestroClient, MaestroException
from core.logging.logger import logger


def disparar_achados(achados: list[dict]) -> dict:
    """
    Abre um chamado por achado via Maestro.

    Retorna:
    {
      "abertos": [{tipo, alvo, cliente, cod_chamado}, ...],
      "falhas":  [{tipo, alvo, erro}, ...],
    }
    """
    abertos = []
    falhas  = []

    if not achados:
        return {"abertos": abertos, "falhas": falhas}

    with MaestroClient() as maestro:
        for achado in achados:
            try:
                cod = maestro.abrir_chamado(achado)
                abertos.append({
                    "tipo":        achado.get("tipo"),
                    "alvo":        achado.get("alvo"),
                    "cliente":     achado.get("cliente"),
                    "cod_chamado": cod,
                })
            except MaestroException as e:
                logger.warning(
                    f"Falha ao abrir chamado ({achado.get('tipo')} / "
                    f"{achado.get('alvo')}): {e}"
                )
                falhas.append({
                    "tipo": achado.get("tipo"),
                    "alvo": achado.get("alvo"),
                    "erro": str(e),
                })

    logger.info(
        f"Disparo concluído: {len(abertos)} chamado(s) aberto(s), "
        f"{len(falhas)} falha(s)."
    )
    return {"abertos": abertos, "falhas": falhas}