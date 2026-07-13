class ExchangeAPIException(Exception):
    """
    Erro genérico ao operar contra o Exchange Online (via
    ExchangeOnlineManagement/PowerShell). `exit_code` guarda o código de
    saída do processo `pwsh`, quando disponível -- equivalente ao
    `status_code` usado em GraphAPIException/SharePointAPIException, só
    que aqui não existe HTTP direto (a chamada é via subprocess).
    """

    def __init__(self, message: str, exit_code: int | None = None):
        super().__init__(message)
        self.exit_code = exit_code


class ExchangeAuthenticationException(ExchangeAPIException):
    def __init__(self, tenant_id: str, detalhe: str = ""):
        msg = f"Falha ao autenticar no Exchange Online para o tenant: {tenant_id}"
        if detalhe:
            msg += f" ({detalhe})"
        super().__init__(msg)
        self.tenant_id = tenant_id