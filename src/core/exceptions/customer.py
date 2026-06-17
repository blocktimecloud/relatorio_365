from core.exceptions.base import ApplicationException


class CustomerNotFoundException(ApplicationException):
    def __init__(self, customer_id: str):
        super().__init__(f"Cliente não encontrado: {customer_id}")
        self.customer_id = customer_id


class CustomerAlreadyExistsException(ApplicationException):
    def __init__(self, customer_id: str):
        super().__init__(f"Cliente já existe: {customer_id}")
        self.customer_id = customer_id
        
class InvalidCNPJException(ApplicationException):
    def __init__(self, cnpj: str, reason: str = "formato inválido"):
        super().__init__(f"CNPJ inválido ('{cnpj}'): {reason}")
        self.cnpj = cnpj
        self.reason = reason