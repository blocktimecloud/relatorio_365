import httpx
from core.config.settings import settings
from core.logging.logger import logger


class MaestroException(Exception):
    pass


class MaestroClient:
    """
    Dispara aberturas de chamado no Desk Manager via Maestro (Invoke URL POST).
    Cada 'tipo' de achado tem sua própria pipeline (URL + token).
    O token vai na query string; o número do chamado volta em R.cod_chamado.
    """

    def __init__(self, routes: dict | None = None):
        self._routes = routes or settings.maestro_routes
        self._client = httpx.Client(timeout=30.0)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self) -> None:
        self._client.close()

    def _resolver_rota(self, tipo: str) -> tuple[str, str]:
        url, token = self._routes.get(tipo, ("", ""))
        if not url or not token:
            raise MaestroException(
                f"Nenhuma pipeline configurada para o tipo '{tipo}'. "
                f"Verifique MAESTRO_{tipo.upper()}_URL / _TOKEN no .env."
            )
        return url, token

    def abrir_chamado(self, payload: dict) -> str:
        """
        Dispara um achado para a pipeline correspondente ao seu 'tipo'
        e retorna o número do chamado.
        payload: {tipo, cliente, solicitante_email, alvo, titulo, descricao}
        """
        tipo = payload.get("tipo", "")
        url, token = self._resolver_rota(tipo)

        try:
            resp = self._client.post(url, params={"token": token}, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise MaestroException(f"Falha ao chamar o Maestro ({tipo}): {e}")

        try:
            data = resp.json()
        except Exception:
            raise MaestroException(f"Resposta do Maestro não é JSON: {resp.text[:200]}")

        r = data.get("R", {})
        cod  = r.get("cod_chamado", "")
        erro = r.get("e", "")

        if erro:
            raise MaestroException(f"Maestro retornou erro ({tipo}): {erro}")
        if not cod:
            raise MaestroException(f"Maestro não retornou cod_chamado ({tipo}): {str(data)[:200]}")

        logger.info(f"Chamado aberto no Desk: {cod} ({tipo} / {payload.get('alvo')})")
        return cod