from collectors.base import BaseCollector
from core.logging.logger import logger


class SharePointCollector(BaseCollector):
    """
    Coleta permissões e armazenamento dos sites SharePoint.
    Permissão necessária: Sites.Read.All, Reports.Read.All
    """

    def collect(self) -> list[dict]:
        """Parte 1 — membros por site."""
        sites = self._client.get(
            "sites",
            params={"search": "*"}
        )

        results = []
        for site in sites.get("value", []):
            try:
                members = self._client.get(
                    f"sites/{site['id']}/members",
                    params={"$select": "displayName,mail"}
                )
                results.append({
                    "site": site.get("displayName", ""),
                    "url": site.get("webUrl", ""),
                    "members": members.get("value", [])
                })
            except Exception:
                logger.warning(f"Erro ao buscar membros do site: {site.get('displayName')}")
                continue

        return results

    def collect_storage(self) -> list[dict]:
        """Parte 2 — armazenamento por site via drive."""
        sites = self._client.get(
            "sites",
            params={"search": "*"}
        )

        results = []
        for site in sites.get("value", []):
            try:
                drive = self._client.get(f"sites/{site['id']}/drive")
                quota = drive.get("quota", {})
                results.append({
                    "site":      site.get("displayName", ""),
                    "url":       site.get("webUrl", ""),
                    "used_gb":   round(quota.get("used", 0) / 1024 ** 3, 2),
                    "total_gb":  round(quota.get("total", 0) / 1024 ** 3, 2),
                    "remaining_gb": round(quota.get("remaining", 0) / 1024 ** 3, 2),
                })
            except Exception:
                logger.warning(f"Erro ao buscar storage do site: {site.get('displayName')}")
                continue

        return results