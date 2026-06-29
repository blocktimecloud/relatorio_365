"""
Gerenciador de certificados X.509 para autenticação app-only no SharePoint.

O SharePoint Online exige certificado (em vez de client_secret) para
autenticação app-only via MSAL. Este módulo cobre:

    - geração do par de chaves X.509 (gerar_certificado)
    - cifragem/decifragem do .pfx usando a mesma camada Fernet que já
      protege os client_secret (core.security)
    - extração da chave privada em PEM, formato exigido pela MSAL
      (obter_chave_privada_pem)
    - utilitários para o fluxo de renovação (dias_para_expirar)

O .pfx é gerado SEM senha própria: a proteção vem inteiramente da
camada Fernet (o token cifrado já é opaco e autenticado). Isso evita
gerenciar uma segunda senha além da SECRET_KEY do projeto.

Nada aqui depende de rede ou do Azure — é só criptografia local. O
upload do .cer no App Registration de cada cliente é manual (ver
exportar_cer) por causa da permissão Application.ReadWrite.All, que um
MSP normalmente não tem em tenants de clientes.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from core.exceptions.base import ApplicationException
from core.security import decrypt, encrypt

_RSA_KEY_SIZE = 2048
_VALIDADE_ANOS_DEFAULT = 2


class CertificateException(ApplicationException):
    pass


@dataclass
class CertificadoGerado:
    """Resultado de gerar_certificado(): tudo que o cadastro precisa."""

    cer_bytes: bytes          # certificado público (.cer), para upload no Azure
    pfx_cifrado: str          # .pfx privado, já cifrado (Fernet) — vai pro banco
    thumbprint: str           # SHA-1 hex maiúsculo — identifica o cert no Azure
    x5t: str                  # SHA-1 base64url — vai no header do JWT
    not_after: datetime       # data de expiração (UTC, sem tzinfo p/ o ORM)


# ── Geração ──────────────────────────────────────────────────────────────


def gerar_certificado(
    common_name: str,
    validade_anos: int = _VALIDADE_ANOS_DEFAULT,
) -> CertificadoGerado:
    """
    Gera um par de chaves X.509 autoassinado, pronto para:
      - subir o .cer público no App Registration do cliente (Azure)
      - guardar o .pfx privado (já cifrado) no banco

    `common_name` aparece no certificado só como identificação (ex: o
    nome fantasia do cliente) — não precisa bater com nada no Azure.
    """
    chave_privada = rsa.generate_private_key(
        public_exponent=65537,
        key_size=_RSA_KEY_SIZE,
    )

    assunto = emissor = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    )

    agora = datetime.now(timezone.utc)
    not_after = agora + timedelta(days=365 * validade_anos)

    certificado = (
        x509.CertificateBuilder()
        .subject_name(assunto)
        .issuer_name(emissor)
        .public_key(chave_privada.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora)
        .not_valid_after(not_after)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]),
            critical=False,
        )
        .sign(chave_privada, hashes.SHA256())
    )

    cer_bytes = certificado.public_bytes(serialization.Encoding.PEM)

    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=common_name.encode(),
        key=chave_privada,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # O .pfx é binário; cifra-se a versão base64 (string) com o Fernet
    # do projeto, que só trabalha com str.
    pfx_b64 = base64.b64encode(pfx_bytes).decode()
    pfx_cifrado = encrypt(pfx_b64)

    thumbprint = calcular_thumbprint(certificado)
    x5t = _thumbprint_para_x5t(thumbprint)

    return CertificadoGerado(
        cer_bytes=cer_bytes,
        pfx_cifrado=pfx_cifrado,
        thumbprint=thumbprint,
        x5t=x5t,
        not_after=not_after.replace(tzinfo=None),
    )


# ── Carregamento (runtime) ───────────────────────────────────────────────


def carregar_pfx(pfx_cifrado: str) -> tuple:
    """
    Decifra o .pfx guardado no banco e devolve (chave_privada, certificado).
    Usado tanto pela extração de PEM (abaixo) quanto por qualquer outra
    rotina que precise da chave privada original.
    """
    try:
        pfx_b64 = decrypt(pfx_cifrado)
        pfx_bytes = base64.b64decode(pfx_b64)
    except Exception as exc:
        raise CertificateException(
            "Falha ao decifrar o certificado. Verifique a SECRET_KEY."
        ) from exc

    chave_privada, certificado, _ = pkcs12.load_key_and_certificates(
        pfx_bytes, password=None
    )
    if chave_privada is None or certificado is None:
        raise CertificateException("Certificado armazenado está corrompido ou incompleto.")

    return chave_privada, certificado


def obter_chave_privada_pem(pfx_cifrado: str) -> str:
    """
    Decifra o .pfx e devolve a chave privada em PEM (PKCS8, sem senha) —
    formato exigido pela MSAL em `client_credential["private_key"]`.
    """
    chave_privada, _certificado = carregar_pfx(pfx_cifrado)
    pem_bytes = chave_privada.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode()


# ── Exportação para o cadastro ───────────────────────────────────────────


def exportar_cer(cer_bytes: bytes, nome_cliente: str, diretorio: str | Path = "certs") -> Path:
    """
    Salva o .cer público em disco, com nome de arquivo seguro, e devolve
    o caminho. É esse arquivo que precisa ser enviado para
    Certificates & secrets → Certificates → Upload, no App Registration
    do cliente no Azure.
    """
    pasta = Path(diretorio)
    pasta.mkdir(parents=True, exist_ok=True)

    nome_seguro = re.sub(r"[^A-Za-z0-9_-]+", "_", nome_cliente).strip("_") or "cliente"
    sufixo = base64.urlsafe_b64encode(nome_cliente.encode()).decode()[:8]
    caminho = pasta / f"{nome_seguro}_{sufixo}.cer"

    caminho.write_bytes(cer_bytes)
    return caminho


# ── Utilitários ───────────────────────────────────────────────────────────


def calcular_thumbprint(certificado: x509.Certificate) -> str:
    """SHA-1 do certificado em hex maiúsculo — é o identificador que o
    Azure mostra em Certificates & secrets e que a MSAL exige."""
    return certificado.fingerprint(hashes.SHA1()).hex().upper()


def _thumbprint_para_x5t(thumbprint_hex: str) -> str:
    """Converte o thumbprint hex para o formato x5t (base64url) usado
    no header do JWT assinado."""
    raw = bytes.fromhex(thumbprint_hex)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def dias_para_expirar(not_after: datetime | None) -> int | None:
    """Quantos dias faltam até o certificado expirar. None se não houver
    certificado (not_after vazio)."""
    if not_after is None:
        return None
    referencia = not_after if not_after.tzinfo else not_after.replace(tzinfo=timezone.utc)
    delta = referencia - datetime.now(timezone.utc)
    return delta.days