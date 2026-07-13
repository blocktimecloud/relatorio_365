import time

import httpx
from datetime import datetime, timedelta, timezone

from customer.models import CustomerCredentials
from core.config.constants import GRAPH_BASE_URL, GRAPH_TOKEN_URL, GRAPH_SCOPE
from core.exceptions.graph import GraphAPIException, GraphAuthenticationException
from core.logging.logger import logger

# Tentativas em respostas com throttling (429) ou indisponibilidade (503)
_MAX_RETRIES = 5
_DEFAULT_BACKOFF = 2  # segundos, usado quando não há header Retry-After

# Tentativas em falha de REDE (conexão recusada/inalcançável, timeout) --
# diferente do throttling acima: aqui a requisição nem chega a completar,
# então não existe status_code para checar.
_MAX_NETWORK_RETRIES = 3
_NETWORK_BACKOFF = 2  # segundos, backoff exponencial


class GraphClient:
    def __init__(self, credentials: CustomerCredentials):
        self._credentials = credentials
        self._access_token: str | None = None
        self._token_expires_at: datetime = datetime.now(timezone.utc)  # já "expirado"
        # Reusa a mesma conexão TCP/TLS em todas as chamadas (pooling).
        self._http = httpx.Client(timeout=30)

    # ── Ciclo de vida ────────────────────────────────────────────────────

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "GraphClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ── Requisição com retry de rede ─────────────────────────────────────

    def _send_with_network_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Executa uma requisição HTTP, retentando em caso de falha de REDE
        (httpx.TransportError -- cobre ConnectError, ReadTimeout,
        ConnectTimeout, PoolTimeout, etc.), com backoff exponencial.

        Diferente do retry de status HTTP (429/503) feito em
        _request_with_retry: aqui o problema é a requisição nem completar
        (sem resposta, sem status_code para checar) -- por isso é uma
        camada separada, usada tanto por _acquire_token (POST) quanto
        por _request_with_retry (GET).
        """
        for attempt in range(_MAX_NETWORK_RETRIES):
            try:
                return self._http.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt == _MAX_NETWORK_RETRIES - 1:
                    raise
                wait = _NETWORK_BACKOFF * (2 ** attempt)
                logger.warning(
                    f"Falha de rede em {method} {url} "
                    f"({exc.__class__.__name__}: {exc}); tentando de novo "
                    f"em {wait}s (tentativa {attempt + 1}/{_MAX_NETWORK_RETRIES})"
                )
                time.sleep(wait)

        raise AssertionError("inatingível -- o loop sempre retorna ou levanta antes")  # pragma: no cover

    # ── Autenticação ─────────────────────────────────────────────────────

    def _is_token_expired(self) -> bool:
        # considera expirado 60 segundos antes para ter margem de segurança
        return datetime.now(timezone.utc) >= (self._token_expires_at - timedelta(seconds=60))

    def _acquire_token(self) -> None:
        url = GRAPH_TOKEN_URL.format(tenant_id=self._credentials.tenant_id)
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
            "scope": GRAPH_SCOPE,
        }
        response = self._send_with_network_retry("POST", url, data=payload)

        if response.status_code != 200:
            raise GraphAuthenticationException(self._credentials.tenant_id)

        token_data = response.json()
        self._access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)  # padrão 1 hora
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        logger.info(f"Token adquirido para o tenant {self._credentials.tenant_id}")

    def _ensure_token(self) -> str:
        if self._access_token is None or self._is_token_expired():
            self._acquire_token()
        return self._access_token  # type: ignore[return-value]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._ensure_token()}",
            "Content-Type": "application/json",
        }

    # ── Requisições ──────────────────────────────────────────────────────

    def _request_with_retry(self, url: str, params: dict | None) -> httpx.Response:
        """
        Faz um GET respeitando o throttling do Graph.
        Em 429/503 aguarda o tempo indicado em Retry-After (ou backoff
        exponencial) e tenta novamente, até _MAX_RETRIES vezes.

        Falhas de rede (conexão recusada/inalcançável, timeout) são
        tratadas à parte por _send_with_network_retry, antes mesmo de
        chegar a existir uma resposta com status_code para checar aqui.
        """
        for attempt in range(_MAX_RETRIES):
            response = self._send_with_network_retry(
                "GET", url, headers=self._headers(), params=params
            )

            if response.status_code not in (429, 503):
                return response

            if attempt == _MAX_RETRIES - 1:
                return response  # estourou as tentativas — devolve para tratar como erro

            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() \
                else _DEFAULT_BACKOFF * (2 ** attempt)
            logger.warning(
                f"Graph respondeu {response.status_code}; aguardando {wait}s "
                f"(tentativa {attempt + 1}/{_MAX_RETRIES})"
            )
            time.sleep(wait)

        return response  # type: ignore[return-value]

    def get(self, endpoint: str, params: dict | None = None, base_url: str | None = None) -> dict:
        url = f"{base_url or GRAPH_BASE_URL}/{endpoint.lstrip('/')}"
        results = []

        while url:
            response = self._request_with_retry(url, params)

            if response.status_code != 200:
                raise GraphAPIException(
                    f"Erro {response.status_code}: {response.text}",
                    status_code=response.status_code,
                )

            data = response.json()

            if "value" in data:
                results.extend(data["value"])
                url = data.get("@odata.nextLink")
                params = None
            else:
                return data

        return {"value": results}