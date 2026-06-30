"""
Coleta a cota de armazenamento REAL do tenant no SharePoint Online.

Diferente do SharePointCollector (collector.py), que usa a Graph API e
soma o storage por site/drive, este collector lê o número que só existe
no site de administração do SharePoint: a cota TOTAL contratada do
tenant (Tenant.StorageQuota), que a Graph API não expõe.

Endpoint confirmado (GET REST simples, sem CSOM):
    GET https://{tenant}-admin.sharepoint.com/_api/StorageQuotas()?api-version=1.3.2

Campos relevantes da resposta (agregados por geo, somamos todos):
    TenantStorageMB        — cota total contratada
    GeoUsedStorageMB       — usado
    GeoAvailableStorageMB  — disponível

Requer que o cliente tenha um certificado gerado (cert_pfx) e a
permissão Sites.FullControl.All consentida no Azure — ver
integrations/sharepoint/client.py.
"""
from core.exceptions.sharepoint import SharePointAPIException
from core.logging.logger import logger
from customer.models import Customer
from integrations.sharepoint.client import SharePointClient, montar_dominio_admin

_STORAGE_QUOTAS_ENDPOINT = "/_api/StorageQuotas()"
_API_VERSION = "1.3.2"


def _to_number(valor) -> float:
    """
    Converte um campo numérico do OData de forma defensiva: aceita int,
    float, string numérica ('123', '123.45'), ou None/ausente (-> 0).
    Os campos de StorageQuotas() já foram observados vindo como string
    em alguns tenants, então nunca confiamos no tipo declarado.
    """
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).strip())
    except (ValueError, TypeError):
        return 0.0


class SharePointQuotaCollector:
    """
    Coleta a cota global de armazenamento do tenant via SharePoint REST
    (site de administração), autenticando por certificado app-only.

    Diferente dos demais collectors, não estende BaseCollector porque
    não usa GraphClient — recebe o `Customer` diretamente e gerencia
    seu próprio SharePointClient.
    """

    def __init__(self, customer: Customer):
        self._customer = customer

    def collect(self) -> dict:
        """
        Retorna a cota do tenant em GB, ou um dict com 'disponivel': False
        se o cliente ainda não tiver certificado configurado — para o
        relatório poder omitir a seção sem quebrar.
        """
        if not self._customer.cert_pfx:
            logger.info(
                f"{self._customer.name}: sem certificado SharePoint configurado "
                f"— pulando cota real do tenant."
            )
            return {"disponivel": False}

        data = None
        try:
            with SharePointClient(self._customer) as client:
                dominio_admin = montar_dominio_admin(self._customer.sharepoint_name)
                url = f"https://{dominio_admin}{_STORAGE_QUOTAS_ENDPOINT}"

                data = client.get(url, params={"api-version": _API_VERSION})

            return self._parse_resposta(data)

        except SharePointAPIException:
            # Já é um erro tratado (auth, permissão, HTTP) — relança para
            # quem chama decidir (logar e seguir sem essa seção, etc).
            raise
        except Exception as exc:
            logger.exception(
                f"Erro inesperado ao coletar cota do tenant para {self._customer.name}. "
                f"Resposta crua recebida: {data!r}"
            )
            raise SharePointAPIException(
                f"Falha ao coletar cota do tenant: {exc}"
            ) from exc

    @staticmethod
    def _parse_resposta(data: dict) -> dict:
        """
        A resposta vem como uma lista de entradas por geo-localização
        (a maioria dos tenants tem só uma). Somamos tudo para obter o
        total do tenant.

        Os campos numéricos do OData às vezes vêm como string (depende
        da versão da API / tenant), então cada valor é convertido de
        forma defensiva antes de somar — em vez de assumir int.
        """
        entradas = data.get("value", data) if isinstance(data, dict) else data
        if isinstance(entradas, dict):
            entradas = [entradas]
        if not entradas:
            raise SharePointAPIException(
                "Resposta de StorageQuotas() veio vazia — verifique a permissão "
                "Sites.FullControl.All e o consentimento de admin no tenant."
            )

        total_mb = sum(_to_number(e.get("TenantStorageMB")) for e in entradas)
        usado_mb = sum(_to_number(e.get("GeoUsedStorageMB")) for e in entradas)
        disponivel_mb = sum(_to_number(e.get("GeoAvailableStorageMB")) for e in entradas)

        total_gb = round(total_mb / 1024, 2)
        usado_gb = round(usado_mb / 1024, 2)
        disponivel_gb = round(disponivel_mb / 1024, 2)
        percent_usado = round((usado_mb / total_mb) * 100, 2) if total_mb > 0 else 0

        return {
            "disponivel": True,
            "total_gb": total_gb,
            "used_gb": usado_gb,
            "remaining_gb": disponivel_gb,
            "percent_used": percent_usado,
        }