from core.exceptions.base import ApplicationException


class GraphAPIException(ApplicationException):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GraphAuthenticationException(GraphAPIException):
    def __init__(self, tenant_id: str):
        super().__init__(
            f"Falha ao autenticar no Microsoft Graph para o tenant: {tenant_id}"
        )
        self.tenant_id = tenant_id