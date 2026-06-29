"""
Objetos de domínio — representam um cliente na lógica da aplicação.
Sem dependência de SQLAlchemy ou banco de dados.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CustomerCredentials:
    """Credenciais do Azure AD para autenticação na Graph API."""
    tenant_id:     str
    client_id:     str
    client_secret: str  # valor em texto claro (nunca persistido assim)


@dataclass
class Customer:
    """Entidade cliente — usada em toda a lógica de negócio."""
    id:            str
    name:          str  # nome fantasia (usado em relatório, pasta e email)
    credentials:   CustomerCredentials
    razao_social:  str
    cnpj:          str  # armazenado limpo (14 dígitos)
    contact_email: str | None = None
    created_at:    datetime   = field(default_factory=lambda: datetime.now(timezone.utc))
    active:        bool       = True
    recipient_email: str | None = None
    recipient_name:  str | None = None
    sharepoint_name: str | None = None  # ex: 'duco' → duco.sharepoint.com

    # Certificado para autenticação app-only no SharePoint (cifrado no banco)
    cert_pfx:        str | None = None  # .pfx cifrado (Fernet, base64)
    cert_thumbprint: str | None = None  # SHA-1 hex maiúsculo (Azure)
    cert_x5t:        str | None = None  # base64url (header do JWT)
    cert_not_after:  datetime | None = None  # expiração (UTC)