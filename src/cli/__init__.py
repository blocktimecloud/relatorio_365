import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import questionary
from questionary import Style

from core.database import get_db, create_tables
from customer.customer_service import CustomerService
from customer.validators import validate_cnpj, format_cnpj
from core.exceptions.customer import (
    CustomerNotFoundException,
    CustomerAlreadyExistsException,
    InvalidCNPJException,
)


# ── Estilo visual ────────────────────────────────────────────────────────

cli_style = Style([
    ("qmark",       "fg:#00bcd4 bold"),
    ("question",    "bold"),
    ("answer",      "fg:#00bcd4 bold"),
    ("pointer",     "fg:#00bcd4 bold"),
    ("selected",    "fg:#00bcd4 bold"),
    ("separator",   "fg:#666666"),
    ("instruction", "fg:#666666"),
])


# ── Helpers ──────────────────────────────────────────────────────────────

def _print_customer(c, show_secret: bool = False):
    secret = c.credentials.client_secret if show_secret else "****"
    status = "ativo" if c.active else "inativo"
    print(f"""
  ID              : {c.id}
  Nome fantasia   : {c.name}
  Razão social    : {c.razao_social}
  CNPJ            : {format_cnpj(c.cnpj)}
  Email contato   : {c.contact_email or '-'}
  Status          : {status}
  Criado em       : {c.created_at.strftime('%d/%m/%Y %H:%M')}
  Tenant ID       : {c.credentials.tenant_id}
  Client ID       : {c.credentials.client_id}
  Client Secret   : {secret}
  ─────────────────────────────────────────
  Destinatário    : {c.recipient_name or '-'}
  Email relatório : {c.recipient_email or '-'}
""")


def _ask(prompt, **kwargs):
    return questionary.text(prompt, style=cli_style, **kwargs).ask()


def _ask_optional(prompt):
    return questionary.text(
        prompt + " (opcional, Enter para pular)",
        style=cli_style,
    ).ask() or None


def _ask_secret(prompt):
    return questionary.password(prompt, style=cli_style).ask()


def _confirm(prompt):
    return questionary.confirm(prompt, style=cli_style, default=False).ask()


def _ask_cnpj(prompt="CNPJ:", current=None):
    """
    Pergunta o CNPJ e revalida até ser válido.
    Se `current` for informado, Enter vazio mantém o valor atual (modo update).
    """
    while True:
        raw = questionary.text(prompt, style=cli_style).ask()
        if not raw:
            if current is not None:
                return None  # mantém valor atual
            print("❌ CNPJ é obrigatório.")
            continue
        try:
            return validate_cnpj(raw)
        except InvalidCNPJException as e:
            print(f"❌ {e}")


# ── Comandos ─────────────────────────────────────────────────────────────

def cmd_migrate(_args):
    create_tables()
    print("✅ Tabelas criadas/verificadas no banco de dados.")


def cmd_add(_args):
    print("\n── Cadastrar novo cliente ──────────────────────────\n")

    razao_social = _ask("Razão social:")
    name         = _ask("Nome fantasia:")
    cnpj         = _ask_cnpj("CNPJ:")

    if not razao_social or not name:
        print("❌ Razão social e nome fantasia são obrigatórios.")
        sys.exit(1)

    email     = _ask_optional("Email de contato:")
    tenant_id = _ask("Tenant ID (Azure AD):")
    client_id = _ask("Client ID:")
    secret    = _ask_secret("Client Secret:")

    if not all([tenant_id, client_id, secret]):
        print("❌ Tenant ID, Client ID e Client Secret são obrigatórios.")
        sys.exit(1)

    print("\n── Destinatário do relatório ───────────────────────\n")
    recipient_name  = _ask_optional("Nome do destinatário:")
    recipient_email = _ask_optional("Email do destinatário:")

    print()
    confirmed = _confirm(f"Cadastrar '{name}'?")
    if not confirmed:
        print("Cancelado.")
        return

    db = next(get_db())
    svc = CustomerService(db)
    try:
        customer = svc.create(
            name=name,
            razao_social=razao_social,
            cnpj=cnpj,
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=secret,
            contact_email=email,
            recipient_name=recipient_name,
            recipient_email=recipient_email,
        )
        print("\n✅ Cliente criado com sucesso!")
        _print_customer(customer)
    except CustomerAlreadyExistsException as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except InvalidCNPJException as e:
        print(f"\n❌ {e}")
        sys.exit(1)


def cmd_list(args):
    db = next(get_db())
    svc = CustomerService(db)
    customers = svc.list_active() if args.active_only else svc.list_all()
    if not customers:
        print("\nNenhum cliente encontrado.")
        return
    print(f"\n{'='*60}")
    for c in customers:
        _print_customer(c)
        print(f"  {'─'*56}")


def cmd_get(args):
    db = next(get_db())
    svc = CustomerService(db)
    try:
        customer = svc.get(args.id)
        _print_customer(customer, show_secret=args.show_secret)
    except CustomerNotFoundException as e:
        print(f"\n❌ {e}")
        sys.exit(1)


def cmd_update(args):
    db = next(get_db())
    svc = CustomerService(db)
    try:
        customer = svc.get(args.id)
    except CustomerNotFoundException as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    print(f"\n── Atualizar cliente: {customer.name} ──────────────\n")
    print("  Deixe em branco para manter o valor atual.\n")

    name = questionary.text(
        f"Nome fantasia [{customer.name}]:",
        style=cli_style,
    ).ask() or None

    razao_social = questionary.text(
        f"Razão social [{customer.razao_social}]:",
        style=cli_style,
    ).ask() or None

    cnpj = _ask_cnpj(
        f"CNPJ [{format_cnpj(customer.cnpj)}] (Enter para manter):",
        current=customer.cnpj,
    )

    email = questionary.text(
        f"Email contato [{customer.contact_email or '-'}]:",
        style=cli_style,
    ).ask() or None

    tenant_id = questionary.text(
        f"Tenant ID [{customer.credentials.tenant_id}]:",
        style=cli_style,
    ).ask() or None

    client_id = questionary.text(
        f"Client ID [{customer.credentials.client_id}]:",
        style=cli_style,
    ).ask() or None

    rotate = _confirm("Deseja trocar o Client Secret?")
    secret = _ask_secret("Novo Client Secret:") if rotate else None

    print("\n── Destinatário do relatório ───────────────────────\n")

    recipient_name = questionary.text(
        f"Nome destinatário [{customer.recipient_name or '-'}]:",
        style=cli_style,
    ).ask() or None

    recipient_email = questionary.text(
        f"Email destinatário [{customer.recipient_email or '-'}]:",
        style=cli_style,
    ).ask() or None

    active = None
    if customer.active:
        if _confirm("Desativar este cliente?"):
            active = False
    else:
        if _confirm("Reativar este cliente?"):
            active = True

    print()
    confirmed = _confirm("Confirmar alterações?")
    if not confirmed:
        print("Cancelado.")
        return

    try:
        updated = svc.update(
            customer_id=args.id,
            name=name,
            razao_social=razao_social,
            cnpj=cnpj,
            contact_email=email,
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=secret,
            active=active,
            recipient_name=recipient_name,
            recipient_email=recipient_email,
        )
        print("\n✅ Cliente atualizado!")
        _print_customer(updated)
    except CustomerNotFoundException as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except InvalidCNPJException as e:
        print(f"\n❌ {e}")
        sys.exit(1)


def cmd_delete(args):
    db = next(get_db())
    svc = CustomerService(db)
    try:
        customer = svc.get(args.id)
    except CustomerNotFoundException as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    print(f"\n── Remover cliente ─────────────────────────────────")
    _print_customer(customer)

    if not args.force:
        confirmed = _confirm(
            f"Remover '{customer.name}' permanentemente? Esta ação não pode ser desfeita."
        )
        if not confirmed:
            print("Cancelado.")
            return

    svc.delete(args.id)
    print(f"\n✅ Cliente '{customer.name}' removido.")
# ── Parser ───────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli",
        description="Office 365 Reports — gerenciamento de clientes",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="Cria as tabelas no banco de dados")
    sub.add_parser("add",     help="Cadastrar novo cliente")

    p_list = sub.add_parser("list", help="Listar clientes")
    p_list.add_argument("--active-only", action="store_true")

    p_get = sub.add_parser("get", help="Exibir cliente pelo ID")
    p_get.add_argument("id")
    p_get.add_argument("--show-secret", action="store_true")

    p_upd = sub.add_parser("update", help="Atualizar dados do cliente")
    p_upd.add_argument("id")

    p_del = sub.add_parser("delete", help="Remover cliente permanentemente")
    p_del.add_argument("id")
    p_del.add_argument("--force", action="store_true")

    return parser


def main():
    from core.logging.logger import configure_logging
    configure_logging()

    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "migrate": cmd_migrate,
        "add":     cmd_add,
        "list":    cmd_list,
        "get":     cmd_get,
        "update":  cmd_update,
        "delete":  cmd_delete,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()