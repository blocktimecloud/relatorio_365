"""
Coleta o encaminhamento NATIVO da caixa postal (ForwardingSmtpAddress /
ForwardingAddress / DeliverToMailboxAndForward, configuração do Mailbox
no Exchange, fora do alcance do Graph API) de TODAS as caixas do tenant,
classificando cada uma como:
    - ativo=False                 -- sem encaminhamento configurado
    - ativo=True,  interno=True   -- encaminha para o próprio domínio
    - ativo=True,  interno=False  -- encaminha para fora (risco)

É a única fonte de encaminhamento usada no relatório -- o antigo
MailForwardingCollector (baseado em messageRules/inbox rules do Graph)
foi descontinuado, ver collectors/mail_forwarding (removido).

Requer certificado configurado (cert_pfx) e a permissão de app
Exchange.ManageAsApp + papel Exchange Administrator atribuído ao service
principal -- ver integrations/exchange_online/client.py.
"""
from core.exceptions.exchange import ExchangeAPIException
from core.logging.logger import logger
from customer.models import Customer
from integrations.exchange_online.client import ExchangeOnlineClient


class NativeForwardingCollector:
    """
    Não estende BaseCollector porque não usa GraphClient diretamente para
    o dado principal -- recebe o Customer direto, no mesmo padrão do
    SharePointQuotaCollector.
    """

    def __init__(self, customer: Customer):
        self._customer = customer

    def collect(self) -> list[dict]:
        """
        Retorna uma linha por CAIXA (todas, não só as com forwarding),
        cada uma já classificada -- pronto pro template listar tudo e
        destacar visualmente quem está ativo:

            [
                {
                    "userPrincipalName": "...",
                    "forwardingSmtpAddress": "..." | None,
                    "forwardingAddress": "..." | None,
                    "keepsCopy": bool,
                    "ativo": bool,
                    "interno": bool | None,   # None quando ativo=False
                },
                ...
            ]

        Lista vazia se o cliente não tiver certificado configurado.
        """
        if not self._customer.cert_pfx:
            logger.info(
                f"{self._customer.name}: sem certificado configurado -- "
                f"pulando encaminhamento nativo do Exchange."
            )
            return []

        try:
            with ExchangeOnlineClient(self._customer) as client:
                raw = client.get_native_forwarding()
                tenant_domains = client.list_verified_domains()
        except ExchangeAPIException:
            # já é um erro tratado e logado no client -- relança para quem
            # chama decidir (logar e seguir sem essa seção, etc).
            raise
        except Exception as exc:
            logger.exception(
                f"Erro inesperado ao coletar encaminhamento nativo para "
                f"{self._customer.name}"
            )
            raise ExchangeAPIException(
                f"Falha ao coletar encaminhamento nativo: {exc}"
            ) from exc

        return [self._normalize(entry, tenant_domains) for entry in raw]

    @staticmethod
    def _normalize(entry: dict, tenant_domains: set[str]) -> dict:
        """
        Normaliza UMA linha do Get-Mailbox -- toda caixa gera uma linha,
        com ou sem forwarding.
        """
        upn = entry.get("UserPrincipalName")
        smtp = entry.get("ForwardingSmtpAddress")
        addr = entry.get("ForwardingAddress")
        keeps_copy = bool(entry.get("DeliverToMailboxAndForward"))

        destino = smtp or addr
        ativo = bool(destino)

        return {
            "userPrincipalName": upn,
            "forwardingSmtpAddress": smtp,
            "forwardingAddress": addr,
            "keepsCopy": keeps_copy,
            "ativo": ativo,
            "interno": NativeForwardingCollector._is_internal(destino, tenant_domains) if ativo else None,
        }

    @staticmethod
    def _is_internal(address: str, tenant_domains: set[str]) -> bool:
        """
        True se o domínio do destino bater com algum domínio verificado do
        tenant. Endereços sem "@" (ex: ForwardingAddress vindo como DN/
        identity em vez de SMTP -- mesmo problema já visto em messageRules)
        são tratados como externo por padrão, por segurança: é melhor um
        falso positivo (aparecer como risco quando não é) do que um falso
        negativo (encaminhamento externo real passando despercebido).
        """
        if "@" not in address:
            return False
        domain = address.rsplit("@", 1)[-1].lower()
        return domain in tenant_domains