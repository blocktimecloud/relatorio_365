import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.bootstrap import initialize
from core.database import get_db
from customer.customer_service import CustomerService
from report_engine.engine import ReportEngine
from report_engine.report_service import ReportService


def main():
    initialize()

    # A sessão de banco só é necessária para buscar a lista de clientes --
    # generate_for_customer() não toca no banco (usa GraphClient/
    # SharePointClient/ExchangeOnlineClient, autenticados por credencial/
    # certificado). Sem fechar aqui, a conexão MySQL ficava aberta e ociosa
    # durante todo o loop (que pode passar de 30-40min com dezenas de
    # clientes, cada um chamando Connect-ExchangeOnline via pwsh) --
    # tempo suficiente para o servidor ou a rede derrubar a conexão por
    # trás, causando "MySQL server has gone away" mais adiante.
    db = next(get_db())
    try:
        svc = CustomerService(db)
        customers = svc.list_active()
    finally:
        db.close()

    if not customers:
        print("Nenhum cliente ativo encontrado no banco de dados.")
        return

    engine = ReportEngine()
    service = ReportService(engine, output_dir="reports")

    for customer in customers:
        try:
            pdf_path = service.generate_for_customer(customer)
            print(f"✅ {customer.name} → {pdf_path}")
        except Exception as e:
            print(f"❌ {customer.name} → Erro: {e}")


if __name__ == "__main__":
    main()