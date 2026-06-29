from enum import Enum


class ReportStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportType(str, Enum):
    MFA = "mfa"
    LICENSES = "licenses"
    GROUPS = "groups"
    MAIL_FORWARDING = "mail_forwarding"
    SHAREPOINT = "sharepoint"


# Microsoft Graph API
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

# O token é específico por tenant; o escopo usa o domínio do cliente.
SHAREPOINT_AUTHORITY = "https://login.microsoftonline.com/{tenant_id}"
SHAREPOINT_SCOPE = "https://{dominio}/.default"
# Domínio do site de administração, onde mora a cota do tenant.
SHAREPOINT_ADMIN_DOMAIN = "{nome}-admin.sharepoint.com"