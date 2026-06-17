"""
Criptografia simétrica para proteger credenciais sensíveis no banco.
Usa Fernet (AES-128-CBC + HMAC-SHA256) da biblioteca cryptography.

Como gerar a SECRET_KEY:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Adicione o valor gerado no .env:
    SECRET_KEY=<valor_gerado>
"""
from cryptography.fernet import Fernet, InvalidToken
from core.config.settings import settings
from core.exceptions.base import ApplicationException


class EncryptionException(ApplicationException):
    pass


def _get_fernet() -> Fernet:
    key = settings.secret_key
    if not key or key == "GERE_UMA_CHAVE_AQUI":
        raise EncryptionException(
            "SECRET_KEY não configurada no .env. "
            "Gere uma com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt(plain_text: str) -> str:
    """Criptografa uma string e retorna o token como string."""
    return _get_fernet().encrypt(plain_text.encode()).decode()


def decrypt(token: str) -> str:
    """Descriptografa um token e retorna o texto original."""
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise EncryptionException(
            "Falha ao descriptografar credencial. "
            "Verifique se a SECRET_KEY no .env é a mesma usada ao cadastrar o cliente."
        )