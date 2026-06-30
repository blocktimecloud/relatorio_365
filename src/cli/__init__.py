import re
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


_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _ask_guid(prompt, current=None):
    """
    Pergunta um GUID (Tenant ID / Client ID do Azure AD) e revalida até
    bater no formato esperado (8-4-4-4-12 hex). Existe porque é comum
    colar o valor junto com o rótulo da tela do Azure (ex: 'Tenant ID -
    e160359b-...'), o que passa pela validação de "não vazio" mas quebra
    no banco (a coluna é CHAR(36), exatamente o tamanho de um GUID puro).

    Se `current` for informado, Enter vazio mantém o valor atual (modo update).
    """
    while True:
        raw = questionary.text(prompt, style=cli_style).ask()
        if not raw:
            if current is not None:
                return None  # mantém valor atual
            print("❌ Este campo é obrigatório.")
            continue
        valor = raw.strip()
        if _GUID_RE.match(valor):
            return valor.lower()
        print(
            "❌ Isso não parece um GUID válido (formato esperado: "
            "8-4-4-4-12 caracteres hexadecimais, ex: "
            "e160359b-a7d9-4970-a9aa-0f8198a7b720).\n"
            "   Confira se não colou um rótulo junto (ex: 'Tenant ID - ...')."
        )


# ── Comandos ─────────────────────────────────────────────────────────────

def cmd_migrate(_args):
    create_tables()
    print("✅ Tabelas criadas/verificadas no banco de dados.")


def _gerar_certificado_e_instruir(svc, customer):
    """
    Gera o certificado do cliente, exporta o .cer e mostra as instruções
    para subir no Azure. Usado no cadastro e na importação.
    Não interrompe o fluxo se a geração falhar — o cliente já existe.
    """
    from core import cert_manager
    try:
        resultado = svc.gerar_e_salvar_certificado(customer.id)
        caminho = cert_manager.exportar_cer(
            resultado.cer_bytes,
            f"{customer.name}_{customer.id[:8]}",
        )
        print("\n── Certificado SharePoint gerado ───────────────────")
        print(f"  Arquivo .cer : {caminho}")
        print(f"  Thumbprint   : {resultado.thumbprint}")
        print(f"  Validade até : {resultado.not_after:%d/%m/%Y}")
        print("\n  ⚠️  AÇÃO NECESSÁRIA no Azure (App Registration deste cliente):")
        print("     1. Certificates & secrets → Certificates → Upload")
        print(f"        suba o arquivo: {caminho}")
        print("     2. API permissions → adicione SharePoint → Sites.FullControl.All")
        print("     3. Conceda o consentimento de admin")
        print("     Sem isso, a leitura da cota do SharePoint não funcionará.\n")
    except Exception as e:
        print(f"\n⚠️  Cliente criado, mas falhou ao gerar o certificado: {e}")
        print(f"   Você pode gerar depois com: python -m src.cli cert-generate {customer.id}\n")


def cmd_add(_args):
    print("\n── Cadastrar novo cliente ──────────────────────────\n")

    razao_social = _ask("Razão social:")
    name         = _ask("Nome fantasia:")
    cnpj         = _ask_cnpj("CNPJ:")

    if not razao_social or not name:
        print("❌ Razão social e nome fantasia são obrigatórios.")
        sys.exit(1)

    email     = _ask_optional("Email de contato:")
    tenant_id = _ask_guid("Tenant ID (Azure AD):")
    client_id = _ask_guid("Client ID:")
    secret    = _ask_secret("Client Secret:")

    if not all([tenant_id, client_id, secret]):
        print("❌ Tenant ID, Client ID e Client Secret são obrigatórios.")
        sys.exit(1)

    sharepoint_name = _ask("Nome do SharePoint (ex: 'duco' para duco.sharepoint.com):")
    if not sharepoint_name:
        print("❌ Nome do SharePoint é obrigatório.")
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
            sharepoint_name=sharepoint_name,
        )
        print("\n✅ Cliente criado com sucesso!")
        _print_customer(customer)
        _gerar_certificado_e_instruir(svc, customer)
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


def cmd_cert_generate(args):
    """
    Gera (ou regenera) o certificado SharePoint de um cliente já
    cadastrado. Útil quando a geração falhou no cadastro/import, ou
    quando o certificado precisa ser renovado.

    Regenerar sobrescreve o certificado anterior no banco (cert_pfx,
    thumbprint, x5t e validade) — o .cer antigo deixa de ser válido
    para autenticação a partir do momento em que o novo for o único
    salvo. Se o cliente já tem um certificado ativo sendo usado em
    produção, suba o novo .cer no Azure ANTES de remover o antigo lá,
    para não haver uma janela sem certificado funcionando.
    """
    db = next(get_db())
    svc = CustomerService(db)
    try:
        customer = svc.get(args.id)
    except CustomerNotFoundException as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    if customer.cert_pfx and not args.force:
        print(f"\n⚠️  '{customer.name}' já tem um certificado "
              f"(thumbprint={customer.cert_thumbprint}, "
              f"expira em {customer.cert_not_after:%d/%m/%Y}).")
        if not _confirm("Gerar um novo certificado (substitui o atual)?"):
            print("Cancelado.")
            return

    _gerar_certificado_e_instruir(svc, customer)


def cmd_cert_check(args):
    """Lista clientes sem certificado e os com certificado expirando."""
    from core import cert_manager

    db = next(get_db())
    svc = CustomerService(db)
    customers = svc.list_active()

    sem_cert = [c for c in customers if not c.cert_pfx]
    expirando = []
    ok = []
    for c in customers:
        if not c.cert_pfx:
            continue
        dias = cert_manager.dias_para_expirar(c.cert_not_after)
        if dias is not None and dias <= args.dias:
            expirando.append((c, dias))
        else:
            ok.append(c)

    print(f"\n{'='*60}")
    print(f"Certificados SharePoint — {len(customers)} cliente(s) ativo(s)")
    print(f"{'='*60}\n")

    if sem_cert:
        print(f"❌ Sem certificado ({len(sem_cert)}):")
        for c in sem_cert:
            print(f"   {c.name} (id={c.id})")
        print()

    if expirando:
        print(f"⚠️  Expirando em até {args.dias} dia(s) ({len(expirando)}):")
        for c, dias in sorted(expirando, key=lambda t: t[1]):
            urgencia = "JÁ EXPIRADO" if dias < 0 else f"{dias} dia(s)"
            print(f"   {c.name} (id={c.id}) — {urgencia}")
        print()

    if ok:
        print(f"✅ OK ({len(ok)}):")
        for c in ok:
            dias = cert_manager.dias_para_expirar(c.cert_not_after)
            print(f"   {c.name} — expira em {c.cert_not_after:%d/%m/%Y} ({dias} dias)")

    if not sem_cert and not expirando:
        print("Nenhuma ação necessária.")


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

    tenant_id = _ask_guid(
        f"Tenant ID [{customer.credentials.tenant_id}] (Enter para manter):",
        current=customer.credentials.tenant_id,
    )

    client_id = _ask_guid(
        f"Client ID [{customer.credentials.client_id}] (Enter para manter):",
        current=customer.credentials.client_id,
    )

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
def cmd_import(args):
    from customer.customer_import import (
        ler_planilha,
        validar_colunas,
        importar_clientes,
        TODAS_AS_COLUNAS,
        COLUNAS_OBRIGATORIAS,
    )

    print("\n── Importar clientes de planilha ───────────────────\n")

    # 1. lê a planilha
    try:
        registros = ler_planilha(args.arquivo)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except ImportError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if not registros:
        print("❌ A planilha está vazia ou só tem o cabeçalho.")
        sys.exit(1)

    # 2. valida o cabeçalho
    faltando = validar_colunas(registros)
    if faltando:
        print(f"❌ Colunas obrigatórias ausentes no cabeçalho: {', '.join(faltando)}")
        print(f"\n  Colunas obrigatórias: {', '.join(COLUNAS_OBRIGATORIAS)}")
        print(f"  Cabeçalho completo  : {', '.join(TODAS_AS_COLUNAS)}")
        sys.exit(1)

    # 3. confirma antes de gravar
    print(f"  Linhas encontradas na planilha: {len(registros)}")
    if not args.yes:
        if not _confirm(f"Importar {len(registros)} cliente(s)?"):
            print("Cancelado.")
            return

    # 4. importa
    db = next(get_db())
    resultado = importar_clientes(db, registros)

    # 5. relatório final
    print(resultado.resumo())
    # código de saída != 0 se houve qualquer erro, útil para automação
    if resultado.erros and resultado.criados == 0:
        sys.exit(1)


def cmd_import_modelo(args):
    """Gera um arquivo CSV modelo com o cabeçalho correto."""
    from customer.customer_import import TODAS_AS_COLUNAS
    import csv

    destino = args.saida or "modelo_clientes.csv"
    exemplo = {
        "razao_social":    "EMPRESA EXEMPLO LTDA",
        "name":            "Empresa Exemplo",
        "cnpj":            "00.000.000/0001-91",
        "tenant_id":       "00000000-0000-0000-0000-000000000000",
        "client_id":       "00000000-0000-0000-0000-000000000000",
        "client_secret":   "seu-client-secret-aqui",
        "contact_email":   "contato@exemplo.com.br",
        "recipient_name":  "Destinatário Exemplo",
        "recipient_email": "relatorios@exemplo.com.br",
    }
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=TODAS_AS_COLUNAS)
        writer.writeheader()
        writer.writerow(exemplo)

    print(f"✅ Modelo gerado em: {destino}")
    print("   Preencha uma linha por cliente e importe com:")
    print(f"   python -m src.cli import {destino}")


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

    p_certgen = sub.add_parser("cert-generate",
                                help="Gerar/regenerar certificado SharePoint de um cliente")
    p_certgen.add_argument("id")
    p_certgen.add_argument("--force", action="store_true",
                            help="Não pedir confirmação se já existir um certificado")

    p_certchk = sub.add_parser("cert-check",
                                help="Listar clientes sem certificado ou com certificado expirando")
    p_certchk.add_argument("--dias", type=int, default=30,
                            help="Alertar certificados que expiram em até N dias (padrão: 30)")

    p_upd = sub.add_parser("update", help="Atualizar dados do cliente")
    p_upd.add_argument("id")

    p_del = sub.add_parser("delete", help="Remover cliente permanentemente")
    p_del.add_argument("id")
    p_del.add_argument("--force", action="store_true")

    p_imp = sub.add_parser("import", help="Importar clientes de planilha (CSV/XLSX)")
    p_imp.add_argument("arquivo", help="Caminho da planilha .csv ou .xlsx")
    p_imp.add_argument("--yes", "-y", action="store_true",
                       help="Não pedir confirmação antes de importar")

    p_mod = sub.add_parser("import-modelo",
                           help="Gerar planilha modelo (CSV) para importação")
    p_mod.add_argument("--saida", "-o", help="Caminho do arquivo a gerar "
                                             "(padrão: modelo_clientes.csv)")

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
        "cert-generate": cmd_cert_generate,
        "cert-check":    cmd_cert_check,
        "update":  cmd_update,
        "delete":  cmd_delete,
        "import":  cmd_import,
        "import-modelo": cmd_import_modelo,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()