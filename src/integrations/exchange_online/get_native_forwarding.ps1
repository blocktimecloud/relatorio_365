<#
    Coleta o encaminhamento NATIVO de TODAS as caixas do tenant
    (ForwardingSmtpAddress / ForwardingAddress / DeliverToMailboxAndForward),
    configuração que só existe no Exchange, fora do alcance do Graph API.

    Saída: JSON no stdout, uma lista com TODAS as caixas do tenant (não só
    as que têm forwarding) -- a classificação de quem está ativo e se é
    interno/externo é feita no lado Python (collector), que já sabe os
    domínios verificados do tenant.

    Uso:
        pwsh -NoProfile -NonInteractive -File get_native_forwarding.ps1 `
            -AppId <app-id> -Organization <tenant>.onmicrosoft.com `
            -CertPath /caminho/cert.pfx
#>
param(
    [Parameter(Mandatory = $true)][string]$AppId,
    [Parameter(Mandatory = $true)][string]$Organization,
    [Parameter(Mandatory = $true)][string]$CertPath
)

$ErrorActionPreference = "Stop"

try {
    # O .pfx foi gravado sem senha própria (a proteção real é a camada
    # Fernet do lado Python, já removida antes de chegar aqui) -- por
    # isso passamos uma SecureString vazia em vez de pedir senha.
    Connect-ExchangeOnline `
        -AppId $AppId `
        -Organization $Organization `
        -CertificateFilePath $CertPath `
        -CertificatePassword (New-Object System.Security.SecureString) `
        -ShowBanner:$false

    # -ResultSize Unlimited é obrigatório -- sem isso o cmdlet trunca em 1000
    # silenciosamente, sem erro nem warning. Sem -Filter aqui de propósito:
    # queremos TODAS as caixas, pra listar quem tem e quem não tem forwarding.
    $result = Get-Mailbox -ResultSize Unlimited |
        Select-Object UserPrincipalName, ForwardingSmtpAddress, ForwardingAddress, DeliverToMailboxAndForward

    # ConvertTo-Json com array de 1 item vira objeto solto, não lista --
    # forçamos -AsArray pra manter o contrato estável no lado Python.
    $result | ConvertTo-Json -Depth 5 -AsArray
}
finally {
    Disconnect-ExchangeOnline -Confirm:$false -ErrorAction SilentlyContinue
}