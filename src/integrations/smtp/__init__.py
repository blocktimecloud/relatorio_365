import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from email.utils import formataddr

from core.config.settings import settings
from core.logging.logger import logger


class SmtpException(Exception):
    pass


class SmtpService:
    """Serviço de envio de email — configuração única no .env."""

    @property
    def _sender(self) -> str:
        """Endereço remetente. No SES o smtp_user é um ID (AKIA...), não um
        e-mail, então usamos smtp_sender_email quando disponível."""
        return settings.smtp_sender_email or settings.smtp_user

    def _connect(self) -> smtplib.SMTP:
        """Abre a conexão com o servidor SMTP."""
        if not settings.smtp_configured:
            raise SmtpException(
                "SMTP não configurado. Preencha SMTP_USER e SMTP_PASSWORD no .env."
            )
        try:
            smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
            if settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            return smtp
        except Exception as e:
            raise SmtpException(f"Falha ao conectar ao servidor SMTP: {e}")

    def send_report(
        self,
        recipient_email: str,
        recipient_name:  str | None,
        customer_name:   str,
        pdf_path:        Path,
        generated_at:    str,
        cc_email=settings.smtp_cc_email,
    ) -> None:
        """
        Envia o relatório PDF por email para o destinatário do cliente.

        `cc_email` é opcional -- se informado, entra em cópia (Cc) e também
        recebe o email de verdade (o cabeçalho Cc por si só não envia nada,
        só avisa quem mais recebeu; quem decide quem recebe é o `sendmail`).
        """

        # ── Monta o email ────────────────────────────────────────────────
        msg = MIMEMultipart()
        msg["From"] = formataddr((settings.smtp_sender_name, self._sender))
        msg["To"] = formataddr((recipient_name, recipient_email)) if recipient_name else recipient_email
        if cc_email:
            msg["Cc"] = cc_email
        msg["Subject"] = f"Relatório Office 365 — {customer_name} — {generated_at}"

        # ── Corpo do email ───────────────────────────────────────────────
        body = f"""Olá {customer_name},

Você possui um novo relatório de segurança - Microsoft Office 365: {pdf_path.name}.

Caso tenha dúvidas ou encontrar alguma informação divergente, favor comunicar a Blocktime através da nossa equipe de suporte: www.blocktime.help/suporte ou whatsapp: (11)3087-3400.

Este e-mail é automático, por favor, não responda.
"""
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # ── Anexo PDF ────────────────────────────────────────────────────
        if not pdf_path.exists():
            raise SmtpException(f"PDF não encontrado: {pdf_path}")

        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())

        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{pdf_path.name}"',
        )
        msg.attach(part)

        # ── Envia ────────────────────────────────────────────────────────
        # O cabeçalho "Cc" no msg é só o que aparece pro destinatário --
        # quem efetivamente recebe é definido pela lista passada ao
        # sendmail(), por isso o cc_email precisa entrar aqui também.
        destinatarios = [recipient_email] + ([cc_email] if cc_email else [])

        try:
            smtp = self._connect()
            smtp.sendmail(self._sender, destinatarios, msg.as_string())
            smtp.quit()
            logger.info(
                f"Email enviado para {recipient_email} ({customer_name})"
                + (f", cc: {cc_email}" if cc_email else "")
            )
        except SmtpException:
            raise
        except Exception as e:
            raise SmtpException(f"Falha ao enviar email para {recipient_email}: {e}")
        
    def send_ticket_failure_alert(
        self,
        admin_email: str,
        customer_name: str,
        falhas: list[dict],
    ) -> None:
        """Avisa o admin sobre chamados que falharam ao abrir."""
        if not admin_email or not falhas:
            return

        linhas = "\n".join(
            f"- [{f.get('tipo')}] {f.get('alvo')}: {f.get('erro')}"
            for f in falhas
        )
        body = (
            f"Atenção: {len(falhas)} chamado(s) falharam ao abrir no Desk Manager "
            f"durante a geração do relatório de {customer_name}.\n\n"
            f"{linhas}\n\n"
            f"O relatório foi gerado normalmente; apenas a abertura destes "
            f"chamados não foi concluída."
        )

        msg = MIMEMultipart()
        msg["From"]    = formataddr((settings.smtp_sender_name, self._sender))
        msg["To"]      = admin_email
        msg["Subject"] = f"[ALERTA] Falha ao abrir chamados — {customer_name}"
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            smtp = self._connect()
            smtp.sendmail(self._sender, admin_email, msg.as_string())
            smtp.quit()
            logger.info(f"Alerta de falha de chamados enviado para {admin_email}")
        except Exception as e:
            logger.warning(f"Não foi possível enviar alerta de falha ao admin: {e}")