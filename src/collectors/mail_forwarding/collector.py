from collectors.base import BaseCollector
from core.logging.logger import logger


class MailForwardingCollector(BaseCollector):
    """
    Coleta encaminhamentos de e-mail de todos os usuários.
    Permissão necessária: MailboxSettings.Read, User.Read.All
    """

    def collect(self) -> list[dict]:
        users = self._client.get(
            "users",
            params={"$select": "id,displayName,userPrincipalName"}
        )

        results = []
        for user in users.get("value", []):
            try:
                settings = self._client.get(
                    f"users/{user['id']}/mailboxSettings"
                )
                results.append({
                    "userPrincipalName": user["userPrincipalName"],
                    "forwardingSmtpAddress": settings.get("forwardingSmtpAddress")
                })
            except Exception:
                # usuário sem caixa postal (guest, conta de serviço, etc.)
                logger.warning(f"Sem caixa postal: {user['userPrincipalName']}")
                continue

        return results