import sys
sys.path.insert(0, "src")
from integrations.maestro.client import MaestroClient

# URL e token da pipeline de LICENÇA (troque pelos reais)
URL_LICENCA   = "https://ue2pct2dnqdukbie6pcbshugcq0pkxcf.lambda-url.us-east-1.on.aws/"
TOKEN_LICENCA = "blocktime.578461.N2GjgByzsYiRbiLO05x8LDzUroKIb8RfnUqaF0AID4dfuPeSaXHr3lFYwhXMC7G5"

# rota manual só pra este teste
routes = {
    "licenca_vencendo": (URL_LICENCA, TOKEN_LICENCA),
}

payload = {
    "tipo": "licenca_vencendo",
    "cliente": "DUCO TRAVEL SUMMIT",
    "solicitante_email": "admin@ducotravelsummit.com",
    "alvo": "Microsoft 365 Business Premium",
    "dias_para_vencer": 12,
    "titulo": "Licença vencendo em 12 dias: Microsoft 365 Business Premium",
    "descricao": "A licença Microsoft 365 Business Premium vence em 12 dias (23/06/2026). Recomenda-se providenciar a renovação para evitar interrupção dos serviços.",
}

with MaestroClient(routes=routes) as m:
    cod = m.abrir_chamado(payload)
    print(f">>> Chamado de licença aberto: {cod}")