import re
from pathlib import Path
from datetime import datetime, timezone

from customer.models import Customer
from integrations.graph.client import GraphClient
from integrations.smtp import SmtpService
from collectors.mfa.collector import MFACollector
from collectors.licenses.collector import LicensesCollector
from collectors.groups.collector import GroupsCollector
from collectors.mail_forwarding.collector import MailForwardingCollector
from collectors.sharepoint.collector import SharePointCollector
from report_engine.engine import ReportEngine
from core.config.settings import settings
from core.logging.logger import logger
from customer.validators import format_cnpj
from report_engine.findings import detectar_achados
from report_engine.ticket_dispatch import disparar_achados


class ReportService:
    def __init__(
        self,
        report_engine: ReportEngine,
        output_dir: str | Path = "reports"
    ):
        self._engine    = report_engine
        self._output_dir = Path(output_dir)
        self._smtp      = SmtpService()

    @staticmethod
    def _safe_folder_name(name: str) -> str:
        """
        Gera um nome de pasta seguro a partir do nome do cliente,
        removendo separadores de caminho e caracteres problemáticos.
        """
        cleaned = re.sub(r"[^\w.\- ]", "", name.strip()).replace(" ", "_")
        cleaned = cleaned.strip("._") or "cliente"
        return cleaned

    def generate_for_customer(self, customer: Customer, send_email: bool | None = None) -> Path:
        # Se não for especificado, usa o padrão global do .env (SMTP_SEND_ENABLED)
        if send_email is None:
            send_email = settings.smtp_send_enabled

        logger.info(f"Gerando relatório para {customer.name}")

        # 1. Autentica no tenant do cliente
        graph = GraphClient(customer.credentials)

        try:
            # 2. Instancia os collectors
            licenses_collector   = LicensesCollector(graph)
            sharepoint_collector = SharePointCollector(graph)

            # 3. Coleta todos os dados
            generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            context = {
                "customer":           customer,
                "customer_cnpj":      format_cnpj(customer.cnpj),
                "generated_at":       generated_at,
                "mfa":                MFACollector(graph).collect(),
                "licenses":           licenses_collector.collect(),
                "user_licenses":      licenses_collector.collect_user_licenses(),
                "groups":             GroupsCollector(graph).collect(),
                "forwarding":         MailForwardingCollector(graph).collect(),
                "sharepoint":         sharepoint_collector.collect(),
                "sharepoint_storage": sharepoint_collector.collect_storage(),
                "sku_names":          licenses_collector.collect_sku_names(),
                "licencas_vencendo":  licenses_collector.collect_expiring_licenses(),
            }
        finally:
            graph.close()

        # 3.5. Abre chamados no Desk (via Maestro) se habilitado
        context["chamados_abertos"] = []
        if settings.maestro_enabled:
            achados = detectar_achados(customer, context)
            resultado = disparar_achados(achados)
            context["chamados_abertos"] = resultado["abertos"]

            if resultado["falhas"]:
                self._smtp.send_ticket_failure_alert(
                    admin_email=settings.maestro_admin_email,
                    customer_name=customer.name,
                    falhas=resultado["falhas"],
                )
        else:
            logger.info("Abertura de chamados desativada (MAESTRO_ENABLED=false).")

        # 4. Gera e salva o PDF
        filename    = f"Relatorio_office_365_{generated_at}.pdf"
        folder_name = self._safe_folder_name(customer.name)
        output_path = self._output_dir / folder_name / filename

        pdf_path = self._engine.generate_to_file("report.html", context, output_path)
        logger.info(f"Relatório salvo em {pdf_path}")

        # 5. Envia por email (se habilitado e o cliente tiver destinatário configurado)
        if not send_email:
            logger.info("Envio de email desativado para esta execução.")
        elif not customer.recipient_email:
            logger.info("Cliente sem destinatário configurado — email não enviado.")
        elif not settings.smtp_configured:
            logger.warning("SMTP não configurado — email não enviado.")
        else:
            try:
                self._smtp.send_report(
                    recipient_email=customer.recipient_email,
                    recipient_name=customer.recipient_name,
                    customer_name=customer.name,
                    pdf_path=pdf_path,
                    generated_at=generated_at,
                )
            except Exception as e:
                logger.warning(f"PDF gerado mas email não enviado: {e}")

        return pdf_path