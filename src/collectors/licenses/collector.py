from collectors.base import BaseCollector


# ── Mapeamento skuPartNumber → nome amigável ──────────────────────────────
SKU_NAMES = {
    "AAD_PREMIUM":                     "Microsoft Entra ID P1",
    "AAD_PREMIUM_P2":                  "Microsoft Entra ID P2",
    "ATP_ENTERPRISE":                  "Microsoft Defender para Office 365 P1",
    "BUSINESS_PREMIUM":                "Microsoft 365 Business Premium",
    "BUSINESS_ESSENTIALS":             "Microsoft 365 Business Basic",
    "BUSINESS_BASIC":                  "Microsoft 365 Business Basic",
    "BUSINESS_STANDARD":               "Microsoft 365 Business Standard",
    "DESKLESSPACK":                    "Microsoft 365 F1",
    "ENTERPRISEPACK":                  "Microsoft 365 E3",
    "ENTERPRISEPREMIUM":               "Microsoft 365 E5",
    "ENTERPRISEPREMIUM_NOPSTNCONF":    "Microsoft 365 E5 sem Audioconferência",
    "ENTERPRISEWITHSCAL":              "Microsoft 365 E4",
    "EMS":                             "Enterprise Mobility + Security E3",
    "EMSPREMIUM":                      "Enterprise Mobility + Security E5",
    "EXCHANGEENTERPRISE":              "Exchange Online P2",
    "EXCHANGESTANDARD":                "Exchange Online P1",
    "EXCHANGEARCHIVE":                 "Arquivamento do Exchange Online P1",
    "EXCHANGEDESKLESS":                "Exchange Online Kiosk",
    "INTUNE_A":                        "Microsoft Intune",
    "INTUNE_A_D":                      "Microsoft Intune Device",
    "MCOEV":                           "Telefonia Microsoft 365",
    "MCOIMP":                          "Skype for Business Online P1",
    "MCOSTANDARD":                     "Skype for Business Online P2",
    "MCOPSTN1":                        "Plano de Chamadas Domésticas",
    "MCOPSTN2":                        "Plano de Chamadas Domésticas e Internacionais",
    "MCOMEETADV":                      "Audioconferência Microsoft 365",
    "MFA_STANDALONE":                  "Microsoft Entra MFA",
    "O365_BUSINESS":                   "Microsoft 365 Apps for Business",
    "O365_BUSINESS_ESSENTIALS":        "Microsoft 365 Business Basic",
    "O365_BUSINESS_PREMIUM":           "Microsoft 365 Business Premium",
    "OFFICESUBSCRIPTION":              "Microsoft 365 Apps for Enterprise",
    "PLANNERSTANDALONE":               "Microsoft Planner P1",
    "POWER_BI_ADDON":                  "Power BI para Office 365",
    "POWER_BI_PRO":                    "Power BI Pro",
    "PROJECTESSENTIALS":               "Project Online Essentials",
    "PROJECTPREMIUM":                  "Project Online Premium",
    "PROJECTPROFESSIONAL":             "Project Online Professional",
    "RIGHTSMANAGEMENT":                "Azure Information Protection P1",
    "SMB_BUSINESS":                    "Microsoft 365 Apps for Business",
    "SMB_BUSINESS_ESSENTIALS":         "Microsoft 365 Business Basic",
    "SMB_BUSINESS_PREMIUM":            "Microsoft 365 Business Premium",
    "SPB":                             "Microsoft 365 Business Premium",
    "STANDARDPACK":                    "Office 365 E1",
    "STANDARDWOFFPACK":                "Office 365 E2",
    "TEAMS_ESSENTIALS":                "Microsoft Teams Essentials",
    "VISIOCLIENT":                     "Visio Online P2",
    "VISIOONLINE_PLAN1":               "Visio Online P1",
    "WIN_DEF_ATP":                     "Microsoft Defender para Endpoint",
    "YAMMER_ENTERPRISE":               "Yammer Enterprise",
}

# Fallback por skuId (GUID) — para licenças que não aparecem em subscribedSkus
SKU_NAMES_BY_ID = {
    "f30db892-07e9-47e9-837c-80727f46fd3d": "Microsoft Power Automate Free",
    "a403ebcc-fae0-4ca2-8c8c-7a907fd6c235": "Power BI (free)",
}

# SKUs gratuitos e trials — excluídos do relatório (por skuPartNumber)
FREE_SKUS = {
    "FLOW_FREE",
    "POWER_BI_STANDARD",
    "TEAMS_EXPLORATORY",
    "TEAMS_FREE",
    "POWERAPPS_VIRAL",
    "POWERAPPS_DEV",
    "DEVELOPERPACK",
    "DEVELOPERPACK_E5",
    "RIGHTSMANAGEMENT_ADHOC",
    "SPZA_IW",
    "IT_ACADEMY_AD",
    "WINDOWS_STORE",
    "INTUNE_FREE",
    "VIVA_LEARNING_SEEDED",
    # Identificados em produção (Total absurdamente alto: 10.000 a 1.000.000
    # unidades — característica de SKU gratuita/seeded pelo tenant, não
    # licença comprada). Sem isso, inflavam o "Total contratado" do
    # dashboard para a casa do milhão.
    "FORMS_PRO",                  # Microsoft Forms (Pro) — gratuita, seeded
    "DYN365_ENTERPRISE_P1_IW",    # Dynamics 365 P1 (Information Worker) — gratuita, seeded
    "POWERAPPS_PER_APP_IW",       # variações "_IW" (Information Worker) são sempre seeded/gratuitas
    "POWER_PAGES_VTRIAL_FOR_MAKERS",  # trial — não é licença contratada
    "RMSBASIC",                   # Rights Management Basic — vem grátis com qualquer assinatura
}

# Free conhecidos por skuId (GUID) — para os que não vêm em subscribedSkus
FREE_SKU_IDS = {
    "f30db892-07e9-47e9-837c-80727f46fd3d",  # FLOW_FREE (Power Automate Free)
    "a403ebcc-fae0-4ca2-8c8c-7a907fd6c235",  # POWER_BI_STANDARD (Power BI free)
}

# Acima deste número de unidades contratadas, tratamos como SKU
# seeded/gratuita mesmo que o skuPartNumber não esteja em FREE_SKUS — a
# Microsoft cria/renomeia esses SKUs com frequência, e nenhum tenant real
# compra 1.000+ licenças de um produto enquanto usa só um punhado.
# Funciona como rede de segurança complementar à blocklist por nome.
LIMITE_VOLUME_SEEDED = 1000

GRAPH_BETA_URL = "https://graph.microsoft.com/beta"


class LicensesCollector(BaseCollector):
    """
    Coleta licenças do tenant.
    Permissões necessárias: Organization.Read.All, User.Read.All
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sku_index_cache = None  # cache do índice de SKUs do tenant

    @staticmethod
    def _is_free_or_seeded(part_number: str, enabled: int) -> bool:
        """
        True se o SKU deve ser excluído do relatório por ser gratuito,
        trial, ou seeded pelo tenant (não uma licença efetivamente
        contratada/paga).
        """
        if part_number in FREE_SKUS:
            return True
        if enabled >= LIMITE_VOLUME_SEEDED:
            return True
        return False

    def collect(self) -> list[dict]:
        """Resumo de licenças por SKU — exclui free/trial, adiciona nome amigável e vencimento."""
        data = self._client.get("subscribedSkus")
        skus = data.get("value", [])

        expiry_map = self._collect_expiry_dates()

        results = []
        for sku in skus:
            part_number = sku.get("skuPartNumber", "")
            enabled = sku.get("prepaidUnits", {}).get("enabled", 0)

            # Exclui licenças gratuitas, trials ou seeded em volume
            if self._is_free_or_seeded(part_number, enabled):
                continue

            # Exclui licenças com 0 unidades contratadas
            if enabled == 0:
                continue

            # Exclui licenças deletadas
            if sku.get("capabilityStatus") == "Deleted":
                continue

            # Nome amigável — usa mapeamento ou skuPartNumber como fallback
            friendly_name = SKU_NAMES.get(part_number, part_number)

            # Data de vencimento via beta
            sku_id = sku.get("skuId", "")
            expiry = expiry_map.get(sku_id)

            results.append({
                **sku,
                "friendlyName": friendly_name,
                "expiryDate":   expiry,
            })

        return results

    def _build_sku_index(self) -> dict:
        """
        Mapa {skuId (GUID): {"part": skuPartNumber, "name": nome amigável,
        "enabled": prepaidUnits.enabled}} a partir dos SKUs do tenant.
        Cacheado para não chamar subscribedSkus mais de uma vez por execução.
        """
        if self._sku_index_cache is not None:
            return self._sku_index_cache

        data = self._client.get("subscribedSkus")
        index = {}
        for sku in data.get("value", []):
            sku_id = sku.get("skuId", "")
            part = sku.get("skuPartNumber", "")
            enabled = sku.get("prepaidUnits", {}).get("enabled", 0)
            if sku_id:
                index[sku_id] = {"part": part, "name": SKU_NAMES.get(part, part), "enabled": enabled}

        self._sku_index_cache = index
        return index

    def _collect_expiry_dates(self) -> dict:
        """
        Busca datas de vencimento via /beta/directory/subscriptions.
        Retorna dict {skuId: nextLifecycleDateTime}.
        Falha silenciosamente — nem todos os tenants têm esse endpoint disponível.
        """
        try:
            data = self._client.get(
                "directory/subscriptions",
                base_url=GRAPH_BETA_URL,
            )
            result = {}
            for sub in data.get("value", []):
                sku_id = sub.get("skuId", "")
                expiry = sub.get("nextLifecycleDateTime")
                if sku_id and expiry:
                    # formata de 2026-06-08T00:00:00Z para DD/MM/YYYY
                    result[sku_id] = "/".join(expiry[:10].split("-")[::-1])
            return result
        except Exception:
            return {}

    def collect_user_licenses(self) -> list[dict]:
        """
        Licenças atribuídas por usuário, EXCLUINDO licenças gratuitas/trial.
        Resolve o skuPartNumber via subscribedSkus e descarta o que está em
        FREE_SKUS (ou cujo skuId está em FREE_SKU_IDS, para os free que não
        aparecem em subscribedSkus).
        """
        sku_index = self._build_sku_index()

        data = self._client.get(
            "users",
            params={"$select": "displayName,userPrincipalName,assignedLicenses"}
        )
        users = data.get("value", [])

        for user in users:
            kept = []
            for lic in user.get("assignedLicenses", []):
                sku_id = lic.get("skuId", "")

                # free conhecido por GUID (não aparece em subscribedSkus)
                if sku_id in FREE_SKU_IDS:
                    continue

                # free/seeded identificado pelo skuPartNumber ou volume do tenant
                info = sku_index.get(sku_id, {})
                if self._is_free_or_seeded(info.get("part", ""), info.get("enabled", 0)):
                    continue

                kept.append(lic)

            user["assignedLicenses"] = kept

        return users

    def collect_sku_names(self) -> dict:
        """
        Mapa {skuId (GUID): nome amigável}, partindo dos GUIDs conhecidos
        (SKU_NAMES_BY_ID) e sobrescrevendo com os SKUs do tenant.
        """
        mapping = dict(SKU_NAMES_BY_ID)
        for sku_id, info in self._build_sku_index().items():
            mapping[sku_id] = info["name"]
        return mapping
    def collect_expiring_licenses(self, dias_limite: int = 15) -> list[dict]:
        """
        Retorna licenças que vencem em até `dias_limite` dias.
        Cada item: {skuId, nome, data_vencimento (DD/MM/YYYY), dias_para_vencer}.
        Usa o mesmo endpoint beta do _collect_expiry_dates; falha silenciosa
        retorna lista vazia.
        """
        from datetime import datetime, timezone

        try:
            data = self._client.get(
                "directory/subscriptions",
                base_url=GRAPH_BETA_URL,
            )
        except Exception:
            return []

        sku_names = self.collect_sku_names()
        hoje = datetime.now(timezone.utc).date()
        resultado = []

        for sub in data.get("value", []):
            sku_id = sub.get("skuId", "")
            expiry = sub.get("nextLifecycleDateTime")
            if not (sku_id and expiry):
                continue

            try:
                venc = datetime.fromisoformat(expiry.replace("Z", "+00:00")).date()
            except Exception:
                continue

            dias = (venc - hoje).days
            if 0 <= dias <= dias_limite:
                resultado.append({
                    "skuId":            sku_id,
                    "nome":             sku_names.get(sku_id, sku_id),
                    "data_vencimento":  venc.strftime("%d/%m/%Y"),
                    "dias_para_vencer": dias,
                })

        return resultado