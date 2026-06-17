from collectors.base import BaseCollector


class MFACollector(BaseCollector):
    """
    Coleta status de MFA de todos os usuários.
    Permissão necessária: Reports.Read.All
    """

    def collect(self) -> list[dict]:
        data = self._client.get("reports/authenticationMethods/userRegistrationDetails")
        return data.get("value", [])