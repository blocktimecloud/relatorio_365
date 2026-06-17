from pathlib import Path
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

# Caminho padrão para os templates
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_DIR = BASE_DIR / "templates"


class ReportEngine:
    def __init__(self, template_dir: str | Path = DEFAULT_TEMPLATE_DIR):
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

    def render_html(self, template_name: str, context: dict) -> str:
        """Renderiza o template Jinja2 e retorna o HTML como string."""
        context.setdefault(
            "generated_at",
            datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        template = self._env.get_template(template_name)
        return template.render(**context)

    def generate(self, template_name: str, context: dict) -> bytes:
        """Renderiza o template e converte para PDF em bytes."""
        html_content = self.render_html(template_name, context)
        return HTML(string=html_content).write_pdf()

    def generate_to_file(
        self,
        template_name: str,
        context: dict,
        output_path: str | Path
    ) -> Path:
        """Gera o PDF e salva em disco. Retorna o caminho do arquivo."""
        pdf_bytes = self.generate(template_name, context)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf_bytes)
        return path