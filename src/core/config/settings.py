from pydantic import field_validator
from pydantic_settings import BaseSettings
from urllib.parse import quote_plus


class Settings(BaseSettings):

    # ── Aplicação ──────────────────────────
    app_name:         str
    environment:      str
    log_level:        str
    storage_provider: str

    # ── MySQL ───────────────────────────────
    db_host:     str = "localhost"
    db_port:     int = 3306
    db_name:     str = "office365_reports"
    db_user:     str = "office365"
    db_password: str = ""

    # ── Criptografia ────────────────────────
    secret_key: str = ""

    # ── SMTP ────────────────────────────────
    smtp_host:         str  = "smtp.office365.com"
    smtp_port:         int  = 587
    smtp_user:         str  = ""
    smtp_password:     str  = ""
    smtp_sender_name:  str  = "Blocktime Relatórios"
    smtp_sender_email: str  = ""
    smtp_use_tls:      bool = True
    smtp_send_enabled: bool = True

    maestro_enabled: bool = False
    maestro_mfa_url:   str = ""
    maestro_mfa_token: str = ""
    maestro_licenca_url:   str = ""
    maestro_licenca_token: str = ""
    
    maestro_admin_email: str = ""

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment deve ser um de: {allowed}")
        return v

#    @property
#    def database_url(self) -> str:
#        return (
#            f"mysql+pymysql://{self.db_user}:{self.db_password}"
#            f"@{self.db_host}:{self.db_port}/{self.db_name}"
#            f"?charset=utf8mb4"
#
#        )
    @property
    def database_url(self) -> str:
        password = quote_plus(self.db_password)

        return (
            f"mysql+pymysql://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
    )
    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def smtp_configured(self) -> bool:
        """Retorna True se o SMTP está configurado no .env."""
        return bool(self.smtp_user and self.smtp_password)
    
    @property
    def maestro_routes(self) -> dict:
        """Mapa {tipo do achado: (invoke_url, token)}."""
        return {
            "mfa":              (self.maestro_mfa_url,     self.maestro_mfa_token),
            "licenca_vencendo": (self.maestro_licenca_url, self.maestro_licenca_token),
        }

    @property
    def maestro_configured(self) -> bool:
        return any(url and token for url, token in self.maestro_routes.values())

    class Config:
        env_file = ".env"


settings = Settings()