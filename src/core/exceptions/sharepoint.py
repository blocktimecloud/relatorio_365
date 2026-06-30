from core.exceptions.base import ApplicationException


class SharePointAPIException(ApplicationException):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SharePointAuthenticationException(SharePointAPIException):
    def __init__(self, tenant_id: str, detalhe: str = ""):
        msg = f"Falha ao autenticar no SharePoint para o tenant: {tenant_id}"
        if detalhe:
            msg += f" ({detalhe})"
        super().__init__(msg)
        self.tenant_id = tenant_id