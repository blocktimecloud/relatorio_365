"""
ORM — mapeamento da tabela `customers` no MySQL.
Este arquivo só conhece SQLAlchemy. Nada de lógica de negócio aqui.
"""
from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.mysql import CHAR

from core.database import Base
from core.security import encrypt, decrypt


class CustomerModel(Base):
    """Tabela `customers` no banco de dados."""

    __tablename__ = "customers"

    id            = Column(CHAR(36),    primary_key=True, index=True)
    name          = Column(String(255), nullable=False)  # nome fantasia
    razao_social  = Column(String(255), nullable=False)
    cnpj          = Column(CHAR(14),    nullable=False)   # apenas dígitos
    contact_email = Column(String(255), nullable=True)
    active        = Column(Boolean,     default=True,            nullable=False)
    created_at    = Column(DateTime,    default=lambda: datetime.now(timezone.utc), nullable=False)

    # Credenciais Azure AD
    tenant_id     = Column(CHAR(36),    nullable=False)
    client_id     = Column(CHAR(36),    nullable=False)
    client_secret = Column(Text,        nullable=False)

    # Destinatário do relatório
    recipient_email = Column(String(255), nullable=True)
    recipient_name  = Column(String(255), nullable=True)

    # ── Conversão ORM → domínio ──────────────────────────────────────────
    def to_domain(self):
        from customer.models import Customer, CustomerCredentials
        return Customer(
            id=self.id,
            name=self.name,
            razao_social=self.razao_social,
            cnpj=self.cnpj,
            contact_email=self.contact_email,
            active=self.active,
            created_at=self.created_at.replace(tzinfo=timezone.utc),
            recipient_email=self.recipient_email,
            recipient_name=self.recipient_name,
            credentials=CustomerCredentials(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=decrypt(self.client_secret),
            ),
        )

    # ── Conversão domínio → ORM ──────────────────────────────────────────
    @staticmethod
    def from_domain(customer) -> CustomerModel:
        return CustomerModel(
            id=customer.id,
            name=customer.name,
            razao_social=customer.razao_social,
            cnpj=customer.cnpj,
            contact_email=customer.contact_email,
            active=customer.active,
            created_at=customer.created_at.replace(tzinfo=None),
            tenant_id=customer.credentials.tenant_id,
            client_id=customer.credentials.client_id,
            client_secret=encrypt(customer.credentials.client_secret),
            recipient_email=customer.recipient_email,
            recipient_name=customer.recipient_name,
        )