"""
Cliente do SharePoint Online com autenticação app-only via certificado.

Espelha a estrutura do GraphClient (integrations/graph/client.py), mas o
SharePoint exige certificado em vez de client_secret para tokens app-only.
A credencial de certificado (chave PEM + thumbprint) é extraída do .pfx
guardado no cliente.
"""
import time
from datetime import datetime, timezone

import httpx

from core import cert_manager
from core.config.constants import SHAREPOINT_AUTHORITY, SHAREPOINT_SCOPE
from core.exceptions.sharepoint import (
    SharePointAPIException,
    SharePointAuthenticationException,
)
from core.logging.logger import logger

_MAX_RETRIES = 5
_DEFAULT_BACKOFF = 2  # segundos


def montar_dominio(sharepoint_name: str) -> str:
    """
    'duco' → 'duco.sharepoint.com'. Idempotente e tolerante a
    sufixos digitados por engano (.onmicrosoft.com / .sharepoint.com).
    """
    nome = (sharepoint_name or "").strip().lower()
    if not nome:
        raise SharePointAPIException(
            "Cliente sem 'sharepoint_name' — não é possível montar o domínio."
        )
    if nome.endswith(".sharepoint.com"):
        return nome
    nome = nome.replace(".onmicrosoft.com", "")
    return f"{nome}.sharepoint.com"


def montar_dominio_admin(sharepoint_name: str) -> str:
    """'duco' → 'duco-admin.sharepoint.com' (site de administração)."""
    base = montar_dominio(sharepoint_name).replace(".sharepoint.com", "")
    return f"{base}-admin.sharepoint.com"


class SharePointClient:
    """
    Cliente app-only do SharePoint para um cliente (tenant) específico.
    Use como context manager para fechar a conexão HTTP ao final.
    """

    def __init__(self, customer):
        self._customer = customer
        self._access_token: str | None = None
        self._http = httpx.Client(timeout=30)

    # ── Ciclo de vida ────────────────────────────────────────────────────

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SharePointClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ── Autenticação (MSAL + certificado) ────────────────────────────────

    def _acquire_token(self) -> None:
        try:
            import msal
        except ImportError as e:
            raise SharePointAPIException(
                "Biblioteca 'msal' não instalada. Adicione 'msal' ao requirements."
            ) from e

        cred = self._customer.credentials

        if not getattr(self._customer, "cert_pfx", None):
            raise SharePointAuthenticationException(
                cred.tenant_id,
                detalhe=f"cliente '{self._customer.name}' sem certificado gerado",
            )

        dominio = montar_dominio(self._customer.sharepoint_name)
        scope = [SHAREPOINT_SCOPE.format(dominio=dominio)]
        authority = SHAREPOINT_AUTHORITY.format(tenant_id=cred.tenant_id)

        private_key_pem = cert_manager.obter_chave_privada_pem(self._customer.cert_pfx)
        client_credential = {
            "private_key": private_key_pem,
            "thumbprint": self._customer.cert_thumbprint,
        }

        app = msal.ConfidentialClientApplication(
            client_id=cred.client_id,
            authority=authority,
            client_credential=client_credential,
        )

        result = app.acquire_token_silent(scope, account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=scope)

        if "access_token" not in result:
            erro = result.get("error_description") or result.get("error") or "erro desconhecido"
            raise SharePointAuthenticationException(cred.tenant_id, detalhe=erro)

        self._access_token = result["access_token"]
        logger.info(f"Token SharePoint obtido para {self._customer.name} ({dominio})")

    def _ensure_token(self) -> str:
        # A MSAL mantém cache interno e renova sozinha; só adquirimos se ainda nulo.
        if self._access_token is None:
            self._acquire_token()
        return self._access_token  # type: ignore[return-value]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._ensure_token()}",
            "Accept": "application/json;odata=nometadata",
        }

    # ── Requisições ──────────────────────────────────────────────────────

    def _request_with_retry(self, url: str, params: dict | None) -> httpx.Response:
        for attempt in range(_MAX_RETRIES):
            response = self._http.get(url, headers=self._headers(), params=params)
            if response.status_code not in (429, 503):
                return response
            if attempt == _MAX_RETRIES - 1:
                return response
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() \
                else _DEFAULT_BACKOFF * (2 ** attempt)
            logger.warning(
                f"SharePoint respondeu {response.status_code}; aguardando {wait}s "
                f"(tentativa {attempt + 1}/{_MAX_RETRIES})"
            )
            time.sleep(wait)
        return response  # type: ignore[return-value]

    def get(self, url: str, params: dict | None = None) -> dict:
        """GET em uma URL absoluta do SharePoint (REST _api)."""
        response = self._request_with_retry(url, params)
        if response.status_code != 200:
            raise SharePointAPIException(
                f"Erro {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        return response.json()