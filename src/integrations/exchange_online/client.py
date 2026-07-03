"""
Cliente do Exchange Online, para dados que só o Exchange PowerShell expõe
(forwarding nativo de caixa, transport rules) -- o Graph API não tem esses
dados, ver discussão no client de MailForwardingCollector.

Espelha a estrutura do SharePointClient (integrations/sharepoint/client.py):
mesmo padrão de context manager, mesma separação de exceção de
autenticação vs. exceção de API. A diferença de implementação é que aqui
não há uma chamada HTTP direta -- o único jeito suportado de acessar esses
dados é via módulo ExchangeOnlineManagement (PowerShell), então o "cliente"
é um wrapper de subprocess que chama um script .ps1 e parseia JSON.

Reaproveita a MESMA credencial (client_id/tenant_id) e o MESMO certificado
(cert_pfx) já usados para o SharePoint -- não é preciso um App Registration
separado, só adicionar no App Registration existente:
  - a permissão de aplicativo "Exchange.ManageAsApp" (API Office 365
    Exchange Online), com consentimento de admin
  - o papel Microsoft Entra "Exchange Administrator" atribuído ao service
    principal do app
"""
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from core import cert_manager
from core.exceptions.exchange import ExchangeAPIException, ExchangeAuthenticationException
from core.exceptions.graph import GraphAPIException
from core.logging.logger import logger
from integrations.graph.client import GraphClient

_SCRIPT_PATH = Path(__file__).parent / "get_native_forwarding.ps1"
_TIMEOUT_SECONDS = 180


class ExchangeOnlineClient:
    """
    Cliente app-only do Exchange Online para um cliente (tenant) específico.
    Use como context manager, no mesmo padrão do SharePointClient -- aqui
    não há uma conexão HTTP persistente pra fechar, mas mantemos a mesma
    forma de uso por consistência com o resto do projeto.
    """

    def __init__(self, customer):
        self._customer = customer
        self._org_cache: dict | None = None

    def __enter__(self) -> "ExchangeOnlineClient":
        return self

    def __exit__(self, *_exc) -> None:
        pass

    def list_verified_domains(self) -> set[str]:
        """
        Todos os domínios verificados do tenant (não só o .onmicrosoft.com),
        em minúsculas -- usado pra classificar um destino de encaminhamento
        como interno (mesmo domínio do tenant) ou externo.
        """
        org = self._fetch_organization()
        domains: set[str] = set()
        for entry in org.get("value", []):
            for domain in entry.get("verifiedDomains", []):
                name = domain.get("name")
                if name:
                    domains.add(name.lower())
        return domains

    def get_native_forwarding(self) -> list[dict]:
        """
        Retorna o encaminhamento nativo (ForwardingSmtpAddress/ForwardingAddress/
        DeliverToMailboxAndForward) de todas as caixas que têm algo configurado.
        """
        organization = self._resolve_onmicrosoft_domain()

        with self._temp_pfx() as cert_path:
            try:
                result = subprocess.run(
                    [
                        "pwsh", "-NoProfile", "-NonInteractive",
                        "-File", str(_SCRIPT_PATH),
                        "-AppId", self._customer.credentials.client_id,
                        "-Organization", organization,
                        "-CertPath", cert_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as e:
                logger.error(
                    f"Timeout ({_TIMEOUT_SECONDS}s) ao coletar forwarding nativo "
                    f"para {self._customer.name}"
                )
                raise ExchangeAPIException(
                    f"pwsh excedeu o timeout de {_TIMEOUT_SECONDS}s"
                ) from e
            except FileNotFoundError as e:
                raise ExchangeAPIException(
                    "Comando 'pwsh' não encontrado -- PowerShell não está "
                    "instalado nesse ambiente."
                ) from e

        if result.returncode != 0:
            self._raise_for_failure(result)

        stdout = result.stdout.strip()
        if not stdout:
            return []

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.error(
                f"Saída do pwsh não é JSON válido para {self._customer.name}: {e}. "
                f"Saída crua: {stdout[:500]!r}"
            )
            raise ExchangeAPIException(
                f"Saída do script PowerShell não é JSON válido: {e}",
                exit_code=result.returncode,
            ) from e

    # ── Auxiliares ───────────────────────────────────────────────────────

    def _raise_for_failure(self, result: subprocess.CompletedProcess) -> None:
        """
        Distingue falha de autenticação (Connect-ExchangeOnline) do resto,
        igual o SharePointClient distingue pelo status_code HTTP -- aqui
        não há status HTTP, então a distinção é pelo cmdlet que apareceu
        no stderr.
        """
        stderr = result.stderr.strip()
        logger.error(
            f"Falha ao coletar forwarding nativo para {self._customer.name} "
            f"(exit code {result.returncode}): {stderr}"
        )

        if "Connect-ExchangeOnline" in stderr:
            raise ExchangeAuthenticationException(
                self._customer.credentials.tenant_id,
                detalhe=stderr[:300],
            )

        raise ExchangeAPIException(
            f"pwsh retornou código {result.returncode}: {stderr}",
            exit_code=result.returncode,
        )

    def _fetch_organization(self) -> dict:
        """Busca (e cacheia por instância) a resposta de GET /organization."""
        if self._org_cache is None:
            graph = GraphClient(self._customer.credentials)
            try:
                self._org_cache = graph.get("organization")
            except GraphAPIException as e:
                raise ExchangeAPIException(
                    f"Falha ao consultar domínios via Graph: {e}"
                ) from e
        return self._org_cache

    def _resolve_onmicrosoft_domain(self) -> str:
        """
        O Customer não guarda o domínio .onmicrosoft.com -- em vez de exigir
        um campo novo no model, buscamos via Graph (mesma credencial já
        usada em todos os outros collectors). O domínio inicial (isInitial)
        é sempre o .onmicrosoft.com, mesmo que o tenant tenha domínios
        customizados verificados depois.
        """
        org = self._fetch_organization()

        for entry in org.get("value", []):
            for domain in entry.get("verifiedDomains", []):
                if domain.get("isInitial") and domain.get("name", "").endswith(".onmicrosoft.com"):
                    return domain["name"]

        raise ExchangeAPIException(
            f"Não foi possível localizar o domínio .onmicrosoft.com de "
            f"{self._customer.name} via Graph (/organization)."
        )

    def _temp_pfx(self) -> "_TempPfxFile":
        """
        Context manager que grava o .pfx decifrado num arquivo temporário
        com permissão restrita (0600), removido ao final -- mesmo em caso
        de exceção. O arquivo nunca fica em disco além do tempo da chamada
        ao pwsh.
        """
        if not self._customer.cert_pfx:
            raise ExchangeAPIException(
                f"Cliente '{self._customer.name}' sem certificado (cert_pfx) configurado."
            )
        return _TempPfxFile(self._customer.cert_pfx)


class _TempPfxFile:
    def __init__(self, pfx_cifrado: str):
        self._pfx_cifrado = pfx_cifrado
        self._path: str | None = None

    def __enter__(self) -> str:
        pfx_bytes = cert_manager.obter_pfx_bytes(self._pfx_cifrado)

        fd, path = tempfile.mkstemp(suffix=".pfx")
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600 -- só o dono lê/escreve
            with os.fdopen(fd, "wb") as f:
                f.write(pfx_bytes)
        except Exception:
            os.close(fd)
            raise

        self._path = path
        return path

    def __exit__(self, *_exc) -> None:
        if self._path and os.path.exists(self._path):
            os.remove(self._path)