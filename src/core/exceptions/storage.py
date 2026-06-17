from core.exceptions.base import ApplicationException


class StorageUploadException(ApplicationException):
    def __init__(self, path: str, reason: str):
        super().__init__(
            f"Falha ao salvar arquivo em {path}: {reason}"
        )
        self.path = path
        self.reason = reason