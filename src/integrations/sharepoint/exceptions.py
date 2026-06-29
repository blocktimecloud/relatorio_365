class SharePointError(Exception):
    """Erro genérico da API do SharePoint."""


class SharePointAuthenticationError(SharePointError):
    """Erro de autenticação."""


class SharePointAuthorizationError(SharePointError):
    """Permissão insuficiente."""


class SharePointNotFoundError(SharePointError):
    """Recurso não encontrado."""


class SharePointRateLimitError(SharePointError):
    """Limite de requisições excedido."""


class SharePointServerError(SharePointError):
    """Erro interno do SharePoint."""