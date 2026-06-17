from sqlalchemy.orm import Session

from customer.models import Customer
from customer.orm import CustomerModel
from core.exceptions.customer import (
    CustomerNotFoundException,
    CustomerAlreadyExistsException,
)


class CustomerRepository:
    """Repositório de clientes — acesso direto ao banco via SQLAlchemy."""

    def __init__(self, db: Session):
        self._db = db

    # ── Leitura ──────────────────────────────────────────────────────────

    def get(self, customer_id: str) -> Customer:
        row = self._db.query(CustomerModel).filter_by(id=customer_id).first()
        if not row:
            raise CustomerNotFoundException(customer_id)
        return row.to_domain()

    def list_all(self) -> list[Customer]:
        rows = (
            self._db.query(CustomerModel)
            .order_by(CustomerModel.name)
            .all()
        )
        return [r.to_domain() for r in rows]

    def list_active(self) -> list[Customer]:
        rows = (
            self._db.query(CustomerModel)
            .filter_by(active=True)
            .order_by(CustomerModel.name)
            .all()
        )
        return [r.to_domain() for r in rows]

    def exists(self, customer_id: str) -> bool:
        return (
            self._db.query(CustomerModel)
            .filter_by(id=customer_id)
            .count() > 0
        )

    # ── Escrita ──────────────────────────────────────────────────────────

    def add(self, customer: Customer) -> None:
        if self.exists(customer.id):
            raise CustomerAlreadyExistsException(customer.id)
        row = CustomerModel.from_domain(customer)
        self._db.add(row)
        self._db.commit()

    def update(self, customer: Customer) -> None:
        row = self._db.query(CustomerModel).filter_by(id=customer.id).first()
        if not row:
            raise CustomerNotFoundException(customer.id)
        row.name            = customer.name
        row.contact_email   = customer.contact_email
        row.active          = customer.active
        row.tenant_id       = customer.credentials.tenant_id
        row.client_id       = customer.credentials.client_id
        row.recipient_email = customer.recipient_email
        row.recipient_name  = customer.recipient_name
        # client_secret só atualiza se vier criptografado do service
        if customer.credentials.client_secret:
            row.client_secret = customer.credentials.client_secret
        self._db.commit()

    def delete(self, customer_id: str) -> None:
        row = self._db.query(CustomerModel).filter_by(id=customer_id).first()
        if not row:
            raise CustomerNotFoundException(customer_id)
        self._db.delete(row)
        self._db.commit()

    def deactivate(self, customer_id: str) -> None:
        row = self._db.query(CustomerModel).filter_by(id=customer_id).first()
        if not row:
            raise CustomerNotFoundException(customer_id)
        row.active = False
        self._db.commit()