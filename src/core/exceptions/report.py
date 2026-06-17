from core.exceptions.base import ApplicationException


class ReportGenerationException(ApplicationException):
    def __init__(self, customer_name: str, reason: str):
        super().__init__(
            f"Falha ao gerar relatório para {customer_name}: {reason}"
        )
        self.customer_name = customer_name
        self.reason = reason