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