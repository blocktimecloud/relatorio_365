"""
Detector de achados: lê os dados coletados e produz a lista de achados
que devem virar chamados no Desk Manager (via Maestro).
Não faz chamadas de API — apenas transforma o context já coletado.
"""


def detectar_achados(customer, context: dict, dias_licenca: int = 15) -> list[dict]:
    """
    Produz a lista de achados (payloads para o Maestro) a partir do context.

    customer: objeto Customer (usa .name e o e-mail de contato)
    context:  o mesmo dict usado no relatório (precisa de 'mfa';
              as licenças vencendo são buscadas à parte)
    Retorna: lista de dicts {tipo, cliente, solicitante_email, alvo, titulo, descricao}
    """
    achados = []
    cliente = customer.name

    # e-mail de contato do cliente — solicitante do chamado
    solicitante = getattr(customer, "contact_email", "") or getattr(customer, "recipient_email", "")

    # ── Achados de MFA: 1 por usuário sem MFA ────────────────────────
    for user in context.get("mfa", []):
        if user.get("isMfaRegistered") is False:
            upn = user.get("userPrincipalName", "") or user.get("displayName", "desconhecido")
            achados.append({
                "tipo":              "mfa",
                "cliente":           cliente,
                "solicitante_email": solicitante,
                "alvo":              upn,
                "titulo":            f"Usuário sem MFA: {upn}",
                "descricao": (
                    f"O usuário {upn} não possui autenticação multifator (MFA) "
                    f"registrada. Recomenda-se habilitar o MFA para reduzir o risco "
                    f"de comprometimento da conta."
                ),
            })

    # ── Achados de licença: 1 por licença vencendo ───────────────────
    for lic in context.get("licencas_vencendo", []):
        nome = lic.get("nome", lic.get("skuId", "licença"))
        dias = lic.get("dias_para_vencer", "?")
        venc = lic.get("data_vencimento", "?")
        achados.append({
            "tipo":              "licenca_vencendo",
            "cliente":           cliente,
            "solicitante_email": solicitante,
            "alvo":              nome,
            "titulo":            f"Licença vencendo em {dias} dias: {nome}",
            "descricao": (
                f"A licença {nome} vence em {dias} dias ({venc}). "
                f"Recomenda-se providenciar a renovação para evitar interrupção "
                f"dos serviços."
            ),
        })

    return achados