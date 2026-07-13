import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.bootstrap import initialize
from core.database import get_db
from customer.customer_service import CustomerService
from core.exceptions.customer import CustomerNotFoundException
from report_engine.engine import ReportEngine
from report_engine.report_service import ReportService


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Gera o relatório de Office 365. Sem argumentos, roda "
                     "para TODOS os clientes ativos (rotina mensal). Use "
                     "--id ou --name para rodar só um cliente (homologação)."
    )
    parser.add_argument(
        "--id",
        help="ID de um cliente específico (roda só ele, ignora --name).",
    )
    parser.add_argument(
        "--name",
        help="Filtra por nome fantasia (substring, sem diferenciar "
             "maiúsculas/minúsculas). Roda todos os que baterem -- útil "
             "quando não sabe o ID de cor.",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Gera o PDF mas não envia por e-mail, mesmo se o cliente "
             "tiver destinatário configurado -- útil para homologação, "
             "para não mandar relatório de teste pro cliente de verdade.",
    )
    return parser.parse_args()


def _resolve_customers(svc: CustomerService, args) -> list:
    """
    Decide quais clientes processar com base nos argumentos:
      --id     -> só esse cliente (erro se não existir)
      --name   -> todos cujo nome contém o texto (case-insensitive)
      nenhum   -> todos os ativos (comportamento padrão, rotina mensal)
    """
    if args.id:
        try:
            return [svc.get(args.id)]
        except CustomerNotFoundException as e:
            print(f"❌ {e}")
            sys.exit(1)

    if args.name:
        termo = args.name.strip().lower()
        encontrados = [c for c in svc.list_active() if termo in c.name.lower()]
        if not encontrados:
            print(f"Nenhum cliente ativo com nome contendo '{args.name}'.")
            sys.exit(1)
        return encontrados

    return svc.list_active()


def main():
    args = _parse_args()
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
        customers = _resolve_customers(svc, args)
    finally:
        db.close()

    if not customers:
        print("Nenhum cliente ativo encontrado no banco de dados.")
        return

    if len(customers) == 1:
        print(f"Rodando para 1 cliente: {customers[0].name}")
    else:
        print(f"Rodando para {len(customers)} cliente(s).")

    engine = ReportEngine()
    service = ReportService(engine, output_dir="reports")

    for customer in customers:
        try:
            pdf_path = service.generate_for_customer(
                customer,
                send_email=False if args.no_email else None,
            )
            print(f"✅ {customer.name} → {pdf_path}")
        except Exception as e:
            print(f"❌ {customer.name} → Erro: {e}")


if __name__ == "__main__":
    main()