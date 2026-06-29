import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from customer.models import Customer, CustomerCredentials
from customer.customer_repository import CustomerRepository
from core.security import encrypt
from core.logging.logger import logger


class CustomerService:

    def __init__(self, db: Session):
        self._repo = CustomerRepository(db)

    # ── Criação ──────────────────────────────────────────────────────────

    def create(
        self,
        name:            str,
        tenant_id:       str,
        client_id:       str,
        client_secret:   str,
        razao_social:    str | None = None,
        cnpj:            str | None = None,
        contact_email:   str | None = None,
        recipient_email: str | None = None,
        recipient_name:  str | None = None,
        sharepoint_name: str | None = None,
    ) -> Customer:
        customer = Customer(
            id=str(uuid.uuid4()),
            name=name.strip(),
            razao_social=razao_social.strip() if razao_social else None,
            cnpj=cnpj.strip() if cnpj else None,
            contact_email=contact_email.strip() if contact_email else None,
            active=True,
            created_at=datetime.now(timezone.utc),
            recipient_email=recipient_email.strip() if recipient_email else None,
            recipient_name=recipient_name.strip()  if recipient_name  else None,
            sharepoint_name=sharepoint_name.strip() if sharepoint_name else None,
            credentials=CustomerCredentials(
                tenant_id=tenant_id.strip(),
                client_id=client_id.strip(),
                client_secret=client_secret.strip(),
            ),
        )
        self._repo.add(customer)
        logger.info(f"Cliente criado: {customer.name} (id={customer.id})")
        return customer

    # ── Certificado SharePoint ───────────────────────────────────────────

    def gerar_e_salvar_certificado(self, customer_id: str):
        """
        Gera um novo certificado para o cliente, salva no banco (.pfx cifrado +
        metadados) e retorna o resultado para o CLI exibir/exportar o .cer.

        Usado tanto no cadastro quanto na renovação.
        """
        from core import cert_manager

        # nome do certificado: identifica o cliente no Azure
        customer = self._repo.get(customer_id)
        common_name = f"blocktime-office365-{customer.id}"

        resultado = cert_manager.gerar_certificado(common_name)

        self._repo.salvar_certificado(
            customer_id=customer_id,
            cert_pfx=resultado.pfx_b64_cifrado,
            cert_thumbprint=resultado.thumbprint,
            cert_x5t=resultado.x5t,
            cert_not_after=resultado.not_after.replace(tzinfo=None),
        )
        logger.info(
            f"Certificado gerado para {customer.name} "
            f"(thumbprint={resultado.thumbprint}, expira={resultado.not_after:%d/%m/%Y})"
        )
        return resultado

    # ── Leitura ──────────────────────────────────────────────────────────

    def get(self, customer_id: str) -> Customer:
        return self._repo.get(customer_id)

    def list_all(self) -> list[Customer]:
        return self._repo.list_all()

    def list_active(self) -> list[Customer]:
        return self._repo.list_active()

    # ── Atualização ──────────────────────────────────────────────────────

    def update(
        self,
        customer_id:     str,
        name:            str | None = None,
        razao_social:    str | None = None,
        cnpj:            str | None = None,
        contact_email:   str | None = None,
        tenant_id:       str | None = None,
        client_id:       str | None = None,
        client_secret:   str | None = None,
        active:          bool | None = None,
        recipient_email: str | None = None,
        recipient_name:  str | None = None,
    ) -> Customer:
        customer = self._repo.get(customer_id)

        if name            is not None: customer.name            = name.strip()
        if razao_social    is not None: customer.razao_social    = razao_social.strip()
        if cnpj            is not None: customer.cnpj            = cnpj.strip()
        if contact_email   is not None: customer.contact_email   = contact_email.strip()
        if active          is not None: customer.active          = active
        if recipient_email is not None: customer.recipient_email = recipient_email.strip()
        if recipient_name  is not None: customer.recipient_name  = recipient_name.strip()
        if tenant_id       is not None: customer.credentials.tenant_id = tenant_id.strip()
        if client_id       is not None: customer.credentials.client_id = client_id.strip()

        if client_secret is not None:
            customer.credentials.client_secret = encrypt(client_secret.strip())
        else:
            customer.credentials.client_secret = encrypt(customer.credentials.client_secret)

        self._repo.update(customer)
        logger.info(f"Cliente atualizado: {customer.name} (id={customer_id})")
        return customer

    # ── Desativação e remoção ─────────────────────────────────────────────

    def deactivate(self, customer_id: str) -> None:
        customer = self._repo.get(customer_id)
        self._repo.deactivate(customer_id)
        logger.info(f"Cliente desativado: {customer.name} (id={customer_id})")

    def delete(self, customer_id: str) -> None:
        customer = self._repo.get(customer_id)
        self._repo.delete(customer_id)
        logger.info(f"Cliente removido: {customer.name} (id={customer_id})")