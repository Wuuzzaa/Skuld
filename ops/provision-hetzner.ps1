<#
.SYNOPSIS
    Verwaltet Hetzner Cloud Server fuer Skuld per Cloud-Init.

.DESCRIPTION
    Kann einen neuen Server erstellen, bestehende Server auflisten, einen
    bestehenden Server loeschen oder einen Server per Recreate neu aufsetzen.
    Beim Erstellen wird automatisch vorkonfiguriertes Cloud-Init fuer Docker,
    Tailscale, UFW und SSH-Haertung uebergeben.
    
    Voraussetzungen:
      - Hetzner Cloud API Token (Read/Write): https://console.hetzner.cloud/
      - Tailscale Auth Key (Einmal-Key): https://login.tailscale.com/admin/settings/keys
      - SSH Public Key

.EXAMPLE
    .\provision-hetzner.ps1
    # Interaktives Menue fuer Create/Delete/Recreate/List

    .\provision-hetzner.ps1 -Action Create -ServerName "skuld-prod" -ServerType "cx22" -Location "fsn1"
    # Erstellt einen neuen Server

    .\provision-hetzner.ps1 -Action Recreate -ServerName "skuld-prod"
    # Loescht den bestehenden Server und erstellt ihn neu

.NOTES
    Locations: fsn1 (Falkenstein), nbg1 (Nürnberg), hel1 (Helsinki), ash (Ashburn)
    Server Types: cx22 (2 vCPU/4GB), cx32 (4 vCPU/8GB), cx42 (8 vCPU/16GB)
#>

[CmdletBinding()]
param(
    [ValidateSet("Prompt", "Create", "Delete", "Recreate", "List")]
    [string]$Action = "Prompt",
    [ValidateSet("Prompt", "Tailscale", "PublicSsh")]
    [string]$AccessMode = "Prompt",
    [string]$ServerName = "skuld-prod",
    [string]$ServerType = "cx23",
    [string]$Location = "fsn1",
    [string]$Image = "ubuntu-24.04",
    [string]$ServerId,
    [switch]$Force,
    [string]$HetznerApiToken,
    [string]$TailscaleAuthKey,
    [string]$SshPublicKeyPath = "$env:USERPROFILE\.ssh\id_ed25519.pub"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalConfigPath = Join-Path $ScriptDir "provision.local.json"

function Get-LocalProvisionConfig {
    param([string]$ConfigPath)

    if (-not (Test-Path $ConfigPath)) {
        return $null
    }

    try {
        return Get-Content $ConfigPath -Raw | ConvertFrom-Json
    } catch {
        throw "Lokale Config konnte nicht gelesen werden: $ConfigPath"
    }
}

function Get-ConfigValue {
    param(
        [object]$Config,
        [string]$Name
    )

    if ($null -eq $Config) {
        return $null
    }

    $Property = $Config.PSObject.Properties[$Name]
    if ($null -eq $Property) {
        return $null
    }

    return $Property.Value
}

function ConvertTo-PlainText {
    param([Security.SecureString]$SecureString)

    $Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto($Bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
    }
}

function Invoke-HetznerApi {
    param(
        [string]$Path,
        [string]$Method = "Get",
        [object]$Body
    )

    $Uri = if ($Path.StartsWith("http")) { $Path } else { "$ApiBase$Path" }
    $Request = @{
        Uri     = $Uri
        Headers = $Headers
        Method  = $Method
    }

    if ($null -ne $Body) {
        $JsonBody = $Body | ConvertTo-Json -Depth 8
        $Request.Body = [System.Text.Encoding]::UTF8.GetBytes($JsonBody)
        $Request.ContentType = "application/json; charset=utf-8"
    }

    try {
        return Invoke-RestMethod @Request
    } catch {
        $ErrorBody = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($ErrorBody -and $ErrorBody.error) {
            throw "Hetzner API Fehler: $($ErrorBody.error.message) (Code: $($ErrorBody.error.code))"
        }

        throw "Hetzner API Fehler: $($_.Exception.Message)"
    }
}

function Get-ExistingServers {
    $Response = Invoke-HetznerApi -Path "/servers"
    return @($Response.servers | Sort-Object name)
}

function Show-Servers {
    param([array]$Servers)

    if (-not $Servers -or $Servers.Count -eq 0) {
        Write-Host "Keine Hetzner Server gefunden." -ForegroundColor Yellow
        return
    }

    Write-Host ""
    Write-Host "Vorhandene Server:" -ForegroundColor Cyan
    for ($Index = 0; $Index -lt $Servers.Count; $Index++) {
        $Server = $Servers[$Index]
        Write-Host ("  [{0}] {1} | ID={2} | {3} | {4}" -f ($Index + 1), $Server.name, $Server.id, $Server.server_type.name, $Server.public_net.ipv4.ip) -ForegroundColor White
    }
    Write-Host ""
}

function Select-Server {
    param(
        [array]$Servers,
        [string]$SelectedServerId,
        [string]$SelectedServerName
    )

    if ($SelectedServerId) {
        return $Servers | Where-Object { $_.id.ToString() -eq $SelectedServerId } | Select-Object -First 1
    }

    if ($SelectedServerName) {
        return $Servers | Where-Object { $_.name -eq $SelectedServerName } | Select-Object -First 1
    }

    Show-Servers -Servers $Servers
    $Choice = Read-Host "Welchen Server willst du verwenden? Gib Nummer, ID oder exakten Namen ein"
    if ([string]::IsNullOrWhiteSpace($Choice)) {
        throw "Es wurde kein Server ausgewaehlt."
    }

    if ($Choice -match '^\d+$') {
        $NumericChoice = [int]$Choice
        if ($NumericChoice -ge 1 -and $NumericChoice -le $Servers.Count) {
            return $Servers[$NumericChoice - 1]
        }

        return $Servers | Where-Object { $_.id.ToString() -eq $Choice } | Select-Object -First 1
    }

    return $Servers | Where-Object { $_.name -eq $Choice } | Select-Object -First 1
}

function Get-CloudInitContent {
    param(
        [string]$TemplatePath,
        [string]$ResolvedSshPublicKey,
        [string]$ResolvedTailscaleAuthKey,
        [string]$ResolvedAccessMode
    )

    if (-not (Test-Path $TemplatePath)) {
        throw "Cloud-Init Template nicht gefunden: $TemplatePath"
    }

    Write-Host ""
    Write-Host "Cloud-Init Template laden..." -ForegroundColor Gray
    $ResolvedCloudInit = Get-Content $TemplatePath -Raw
    $ResolvedCloudInit = $ResolvedCloudInit.Replace('<SSH_PUBLIC_KEY>', $ResolvedSshPublicKey)

    if ($ResolvedAccessMode -eq "Tailscale") {
        $TailscaleInstallBlock = @(
            '  - curl -fsSL https://tailscale.com/install.sh | sh',
            '  - tailscale up --authkey=<TAILSCALE_AUTH_KEY>'
        ) -join "`r`n"
        $SshFirewallBlock = @(
            '  # SSH - nur aus dem Tailscale-Netz',
            '  - ufw allow from 100.64.0.0/10 to any port 22',
            '  - ufw allow from fd7a:115c:a1e0::/48 to any port 22',
            '  - ufw deny 22'
        ) -join "`r`n"
        $SshListenAddressBlock = @(
            "  - sed -i '/^#*ListenAddress/d' /etc/ssh/sshd_config",
            '  - echo "ListenAddress $(tailscale ip -4)" >> /etc/ssh/sshd_config',
            '  - echo "ListenAddress $(tailscale ip -6)" >> /etc/ssh/sshd_config'
        ) -join "`r`n"
        $ResolvedCloudInit = $ResolvedCloudInit.Replace('<TAILSCALE_AUTH_KEY>', $ResolvedTailscaleAuthKey)
    } else {
        $TailscaleInstallBlock = '  # Tailscale deaktiviert'
        $SshFirewallBlock = @(
            '  # SSH - oeffentlich offen, aber nur Key-Auth ist erlaubt',
            '  - ufw allow 22/tcp'
        ) -join "`r`n"
        $SshListenAddressBlock = "  - sed -i '/^#*ListenAddress/d' /etc/ssh/sshd_config"
    }

    $ResolvedCloudInit = $ResolvedCloudInit.Replace('<TAILSCALE_INSTALL_BLOCK>', $TailscaleInstallBlock)
    $ResolvedCloudInit = $ResolvedCloudInit.Replace('<SSH_FIREWALL_BLOCK>', $SshFirewallBlock)
    $ResolvedCloudInit = $ResolvedCloudInit.Replace('<SSH_LISTEN_ADDRESS_BLOCK>', $SshListenAddressBlock)

    $RemainingPlaceholders = [regex]::Matches($ResolvedCloudInit, '<[A-Z_]+>')
    if ($RemainingPlaceholders.Count -gt 0) {
        Write-Warning "Ungelöste Platzhalter im Cloud-Init: $($RemainingPlaceholders.Value -join ', ')"
    }

    return $ResolvedCloudInit
}

function Resolve-AccessMode {
    if ($Action -notin @("Create", "Recreate")) {
        return $AccessMode
    }

    if ($AccessMode -ne "Prompt") {
        return $AccessMode
    }

    Write-Host "Zugriffsmode waehlen:" -ForegroundColor Cyan
    Write-Host "  [1] Tailscale - SSH nur ueber VPN" -ForegroundColor White
    Write-Host "  [2] PublicSsh - SSH oeffentlich mit Key-Auth" -ForegroundColor White
    $Choice = Read-Host "Auswahl"

    if ($Choice -eq "1") {
        return "Tailscale"
    }

    if ($Choice -eq "2") {
        return "PublicSsh"
    }

    throw "Ungueltige Auswahl: $Choice"
}

function Get-ConnectionHint {
    param(
        [string]$ResolvedAccessMode,
        [string]$ServerPublicIp,
        [string]$ResolvedServerName
    )

    if ($ResolvedAccessMode -eq "Tailscale") {
        return @(
            "  2. Tailscale auf deinem PC verbinden und im gleichen Tailnet sein",
            "  3. Im Tailscale Admin nach dem neuen Server schauen",
            "  4. SSH testen: ssh holu@<TAILSCALE_IP>",
            ("     oder mit MagicDNS: ssh holu@{0}" -f $ResolvedServerName)
        )
    }

    return @(
        "  2. SSH ueber die oeffentliche IP testen",
        ("  3. SSH testen: ssh holu@{0}" -f $ServerPublicIp)
    )
}

function Resolve-SshKeyPaths {
    param([string]$RequestedPath)

    if ($RequestedPath.EndsWith('.pub')) {
        return @{
            PublicKeyPath  = $RequestedPath
            PrivateKeyPath = $RequestedPath.Substring(0, $RequestedPath.Length - 4)
        }
    }

    return @{
        PublicKeyPath  = "$RequestedPath.pub"
        PrivateKeyPath = $RequestedPath
    }
}

function Ensure-SshPublicKey {
    param([string]$RequestedPath)

    $KeyPaths = Resolve-SshKeyPaths -RequestedPath $RequestedPath
    if (Test-Path $KeyPaths.PublicKeyPath) {
        return $KeyPaths.PublicKeyPath
    }

    Write-Host "SSH Public Key nicht gefunden unter: $($KeyPaths.PublicKeyPath)" -ForegroundColor Yellow
    $AlternativePath = Read-Host "Pfad zu vorhandenem SSH Public Key oder Private Key (ENTER fuer Standard)"
    if (-not [string]::IsNullOrWhiteSpace($AlternativePath)) {
        $KeyPaths = Resolve-SshKeyPaths -RequestedPath $AlternativePath
        if (Test-Path $KeyPaths.PublicKeyPath) {
            return $KeyPaths.PublicKeyPath
        }
    }

    $SshKeygenCommand = Get-Command ssh-keygen -ErrorAction SilentlyContinue
    if ($null -eq $SshKeygenCommand) {
        throw "ssh-keygen wurde nicht gefunden. Installiere den OpenSSH Client oder gib einen vorhandenen Public Key an."
    }

    if (Test-Path $KeyPaths.PrivateKeyPath) {
        Write-Host "Bestehender Private Key gefunden. Erzeuge dazu den Public Key..." -ForegroundColor Yellow
        $DerivedPublicKey = & $SshKeygenCommand.Source -y -f $KeyPaths.PrivateKeyPath
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($DerivedPublicKey)) {
            throw "Public Key konnte aus dem bestehenden Private Key nicht erzeugt werden."
        }

        $PublicKeyDirectory = Split-Path -Parent $KeyPaths.PublicKeyPath
        if (-not [string]::IsNullOrWhiteSpace($PublicKeyDirectory) -and -not (Test-Path $PublicKeyDirectory)) {
            New-Item -ItemType Directory -Path $PublicKeyDirectory -Force | Out-Null
        }

        Set-Content -Path $KeyPaths.PublicKeyPath -Value $DerivedPublicKey
        return $KeyPaths.PublicKeyPath
    }

    $GenerateKeyChoice = Read-Host "Kein SSH-Key gefunden. Neuen ed25519 Key lokal erzeugen? (j/N)"
    if ($GenerateKeyChoice -ne 'j') {
        throw "Es wurde kein SSH-Key bereitgestellt."
    }

    $PrivateKeyDirectory = Split-Path -Parent $KeyPaths.PrivateKeyPath
    if (-not [string]::IsNullOrWhiteSpace($PrivateKeyDirectory) -and -not (Test-Path $PrivateKeyDirectory)) {
        New-Item -ItemType Directory -Path $PrivateKeyDirectory -Force | Out-Null
    }

    & $SshKeygenCommand.Source -t ed25519 -a 64 -f $KeyPaths.PrivateKeyPath -N '' -C "$env:USERNAME@$env:COMPUTERNAME"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $KeyPaths.PublicKeyPath)) {
        throw "SSH-Key konnte nicht erzeugt werden."
    }

    Write-Host "SSH-Key erzeugt: $($KeyPaths.PublicKeyPath)" -ForegroundColor Green
    return $KeyPaths.PublicKeyPath
}

function Remove-Server {
    param(
        [object]$TargetServer,
        [string]$RemovalAction
    )

    Write-Host ""
    Write-Host "Server wird ${RemovalAction}:" -ForegroundColor Yellow
    Write-Host "  Name: $($TargetServer.name)" -ForegroundColor White
    Write-Host "  ID:   $($TargetServer.id)" -ForegroundColor White
    Write-Host "  IP:   $($TargetServer.public_net.ipv4.ip)" -ForegroundColor White

    $IsProductionLike = $TargetServer.name -match '(?i)prod|live|main' -or $TargetServer.labels.environment -eq 'production'

    if (-not $Force) {
        $Confirmation = Read-Host "Tippe exakt den Servernamen '$($TargetServer.name)' zur Bestaetigung"
        if ($Confirmation -ne $TargetServer.name) {
            Write-Host "Abgebrochen." -ForegroundColor Yellow
            exit 0
        }

        if ($IsProductionLike) {
            $SecondConfirmation = Read-Host "Produktionsschutz aktiv. Tippe '$RemovalAction $($TargetServer.name)'"
            if ($SecondConfirmation -ne "$RemovalAction $($TargetServer.name)") {
                Write-Host "Abgebrochen." -ForegroundColor Yellow
                exit 0
            }
        }
    } else {
        Write-Host "-Force gesetzt: Schutzabfragen werden uebersprungen." -ForegroundColor Yellow
    }

    Invoke-HetznerApi -Path "/servers/$($TargetServer.id)" -Method Delete | Out-Null
    Write-Host "Loeschung angestossen." -ForegroundColor Green
}

function Wait-ForServerDeletion {
    param([int]$DeletedServerId)

    $MaxWait = 120
    $Elapsed = 0
    $Interval = 5

    while ($Elapsed -lt $MaxWait) {
        Start-Sleep -Seconds $Interval
        $Elapsed += $Interval

        try {
            Invoke-HetznerApi -Path "/servers/$DeletedServerId" | Out-Null
            Write-Host "  Loeschung laeuft (${Elapsed}s / ${MaxWait}s)..." -ForegroundColor Gray
        } catch {
            if ($_.Exception.Message -match 'not_found|not found|resource_not_found') {
                Write-Host "Server ist geloescht." -ForegroundColor Green
                return
            }

            Write-Host "  Status der Loeschung konnte nicht geprueft werden, versuche erneut..." -ForegroundColor Yellow
        }
    }

    Write-Host "Timeout beim Warten auf die Loeschung. Pruefe den Status manuell in Hetzner." -ForegroundColor Yellow
}

function Wait-ForServerRunning {
    param([int]$CreatedServerId)

    Write-Host "Warte auf Server-Start..." -ForegroundColor Gray
    $MaxWait = 120
    $Elapsed = 0
    $Interval = 5

    while ($Elapsed -lt $MaxWait) {
        Start-Sleep -Seconds $Interval
        $Elapsed += $Interval

        try {
            $StatusCheck = Invoke-HetznerApi -Path "/servers/$CreatedServerId"
            $CurrentStatus = $StatusCheck.server.status

            if ($CurrentStatus -eq "running") {
                Write-Host "Server laeuft! (nach ${Elapsed}s)" -ForegroundColor Green
                Write-Host ""
                Write-Host "Oeffentliche IPv4: $($StatusCheck.server.public_net.ipv4.ip)" -ForegroundColor Cyan
                Write-Host ""
                Write-Host "Cloud-Init konfiguriert jetzt den Server (Docker, optional Tailscale, UFW, SSH)." -ForegroundColor Yellow
                Write-Host "Das dauert ca. 2-3 Minuten. Danach kannst du dich je nach Zugriffsmode verbinden." -ForegroundColor Yellow
                return
            }

            Write-Host "  Status: $CurrentStatus (${Elapsed}s / ${MaxWait}s)..." -ForegroundColor Gray
        } catch {
            Write-Host "  API-Abfrage fehlgeschlagen, versuche erneut..." -ForegroundColor Yellow
        }
    }

    Write-Host "Timeout beim Warten auf den Server. Pruefe den Status manuell in der Hetzner Console." -ForegroundColor Yellow
}

function New-Server {
    param(
        [string]$ResolvedCloudInit,
        [string]$ResolvedAccessMode
    )

    Write-Host ""
    Write-Host "Erstelle Server..." -ForegroundColor Cyan
    Write-Host "  Name:     $ServerName" -ForegroundColor White
    Write-Host "  Typ:      $ServerType" -ForegroundColor White
    Write-Host "  Location: $Location" -ForegroundColor White
    Write-Host "  Image:    $Image" -ForegroundColor White
    Write-Host ""

    $Body = @{
        name        = $ServerName
        server_type = $ServerType
        location    = $Location
        image       = $Image
        user_data   = $ResolvedCloudInit
        labels      = @{
            project     = "skuld"
            environment = "production"
            managed_by  = "cloud-init"
        }
        public_net  = @{
            enable_ipv4 = $true
            enable_ipv6 = $true
        }
    }

    $Response = Invoke-HetznerApi -Path "/servers" -Method Post -Body $Body
    $CreatedServer = $Response.server
    $RootPassword = $Response.root_password

    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  Server erfolgreich erstellt!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Server ID:  $($CreatedServer.id)" -ForegroundColor White
    Write-Host "  Name:       $($CreatedServer.name)" -ForegroundColor White
    Write-Host "  Status:     $($CreatedServer.status)" -ForegroundColor White
    Write-Host "  IPv4:       $($CreatedServer.public_net.ipv4.ip)" -ForegroundColor White
    Write-Host "  IPv6:       $($CreatedServer.public_net.ipv6.ip)" -ForegroundColor White
    Write-Host "  Datacenter: $($CreatedServer.datacenter.name)" -ForegroundColor White

    if ($RootPassword) {
        Write-Host ""
        Write-Host "  Root Passwort (einmalig, wird nicht nochmal angezeigt):" -ForegroundColor Yellow
        Write-Host "  $RootPassword" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "NAECHSTE SCHRITTE:" -ForegroundColor Cyan
    Write-Host "  1. Warte 2-3 Minuten bis Cloud-Init fertig ist" -ForegroundColor White
    foreach ($Hint in (Get-ConnectionHint -ResolvedAccessMode $ResolvedAccessMode -ServerPublicIp $CreatedServer.public_net.ipv4.ip -ResolvedServerName $CreatedServer.name)) {
        Write-Host $Hint -ForegroundColor White
    }
    Write-Host "  5. Deployment starten (z.B. mit Kamal oder docker compose)" -ForegroundColor White
    Write-Host ""

    Wait-ForServerRunning -CreatedServerId $CreatedServer.id
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Skuld - Hetzner Server Provisioning" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Parameter einsammeln
# ---------------------------------------------------------------------------

$LocalConfig = Get-LocalProvisionConfig -ConfigPath $LocalConfigPath

if (-not $HetznerApiToken) {
    $HetznerApiToken = if ($env:HETZNER_API_TOKEN) { $env:HETZNER_API_TOKEN } else { Get-ConfigValue -Config $LocalConfig -Name "HetznerApiToken" }
}

if (-not $TailscaleAuthKey) {
    $TailscaleAuthKey = if ($env:TAILSCALE_AUTH_KEY) { $env:TAILSCALE_AUTH_KEY } else { Get-ConfigValue -Config $LocalConfig -Name "TailscaleAuthKey" }
}

if ($AccessMode -eq "Prompt") {
    $ConfiguredAccessMode = Get-ConfigValue -Config $LocalConfig -Name "AccessMode"
    if ($ConfiguredAccessMode) {
        $AccessMode = $ConfiguredAccessMode
    }
}

if ($ServerName -eq "skuld-prod") {
    $ConfiguredServerName = Get-ConfigValue -Config $LocalConfig -Name "ServerName"
    if ($ConfiguredServerName) {
        $ServerName = $ConfiguredServerName
    }
}

if ($ServerType -eq "cx23") {
    $ConfiguredServerType = Get-ConfigValue -Config $LocalConfig -Name "ServerType"
    if ($ConfiguredServerType) {
        $ServerType = $ConfiguredServerType
    }
}

if ($Location -eq "fsn1") {
    $ConfiguredLocation = Get-ConfigValue -Config $LocalConfig -Name "Location"
    if ($ConfiguredLocation) {
        $Location = $ConfiguredLocation
    }
}

if ($Image -eq "ubuntu-24.04") {
    $ConfiguredImage = Get-ConfigValue -Config $LocalConfig -Name "Image"
    if ($ConfiguredImage) {
        $Image = $ConfiguredImage
    }
}

if ($SshPublicKeyPath -eq "$env:USERPROFILE\.ssh\id_ed25519.pub") {
    $ConfiguredSshPublicKeyPath = Get-ConfigValue -Config $LocalConfig -Name "SshPublicKeyPath"
    if ($ConfiguredSshPublicKeyPath) {
        $SshPublicKeyPath = $ConfiguredSshPublicKeyPath
    }
}

# Hetzner API Token
if (-not $HetznerApiToken) {
    $HetznerApiToken = ConvertTo-PlainText (Read-Host -Prompt "Hetzner Cloud API Token (Read/Write)" -AsSecureString)
}
if ([string]::IsNullOrWhiteSpace($HetznerApiToken)) {
    Write-Error "Hetzner API Token darf nicht leer sein."
    exit 1
}

# Hetzner API Header
$Headers = @{
    "Authorization" = "Bearer $HetznerApiToken"
    "Content-Type"  = "application/json"
}
$ApiBase = "https://api.hetzner.cloud/v1"

if ($Action -eq "Prompt") {
    Write-Host "Aktion waehlen:" -ForegroundColor Cyan
    Write-Host "  [1] Create   - Neuen Server aufsetzen" -ForegroundColor White
    Write-Host "  [2] Delete   - Bestehenden Server loeschen" -ForegroundColor White
    Write-Host "  [3] Recreate - Bestehenden Server loeschen und neu erstellen" -ForegroundColor White
    Write-Host "  [4] List     - Vorhandene Server anzeigen" -ForegroundColor White
    $ActionChoice = Read-Host "Auswahl"
    $Action = switch ($ActionChoice) {
        "1" { "Create" }
        "2" { "Delete" }
        "3" { "Recreate" }
        "4" { "List" }
        default { throw "Ungueltige Auswahl: $ActionChoice" }
    }
}

$AccessMode = Resolve-AccessMode

$ExistingServers = Get-ExistingServers

if ($Action -eq "List") {
    Show-Servers -Servers $ExistingServers
    exit 0
}

$ExistingServer = $null
if ($Action -in @("Delete", "Recreate")) {
    if (-not $ExistingServers -or $ExistingServers.Count -eq 0) {
        Write-Error "Es gibt keine bestehenden Server fuer diese Aktion."
        exit 1
    }

    $ExistingServer = Select-Server -Servers $ExistingServers -SelectedServerId $ServerId -SelectedServerName $ServerName
    if (-not $ExistingServer) {
        Write-Error "Kein passender Server gefunden."
        exit 1
    }

    $ServerName = $ExistingServer.name
}

if ($Action -eq "Create") {
    $NameMatches = @($ExistingServers | Where-Object { $_.name -eq $ServerName })
    if ($NameMatches.Count -gt 0) {
        Write-Host ""
        Write-Host "Ein Server mit dem Namen '$ServerName' existiert bereits." -ForegroundColor Yellow
        Show-Servers -Servers $NameMatches
        if ($Force) {
            throw "Create mit vorhandenem Namen und -Force ist nicht erlaubt. Nutze -Action Recreate."
        }

        $NextStep = Read-Host "Tippe RECREATE fuer Loeschen+Neuaufsetzen oder ENTER zum Abbrechen"
        if ($NextStep -eq "RECREATE") {
            $Action = "Recreate"
            $ExistingServer = $NameMatches[0]
        } else {
            Write-Host "Abgebrochen." -ForegroundColor Yellow
            exit 0
        }
    }
}

# Tailscale Auth Key
if ($Action -in @("Create", "Recreate") -and $AccessMode -eq "Tailscale" -and -not $TailscaleAuthKey) {
    Write-Host ""
    Write-Host "Tailscale Auth-Key generieren:" -ForegroundColor Yellow
    Write-Host "  1. In Tailscale einloggen" -ForegroundColor Yellow
    Write-Host "  2. Admin Console oeffnen" -ForegroundColor Yellow
    Write-Host "  3. Settings -> Keys -> Generate auth key" -ForegroundColor Yellow
    Write-Host "  3. Reusable: No | Ephemeral: Yes empfohlen" -ForegroundColor Yellow
    Write-Host "  4. Den erzeugten Key direkt hier einfuegen" -ForegroundColor Yellow
    Write-Host ""
    $TailscaleAuthKey = Read-Host -Prompt "Tailscale Auth Key"
}
if ($Action -in @("Create", "Recreate") -and $AccessMode -eq "Tailscale" -and [string]::IsNullOrWhiteSpace($TailscaleAuthKey)) {
    Write-Error "Tailscale Auth Key darf nicht leer sein."
    exit 1
}

# SSH Public Key
$SshPublicKey = $null
if ($Action -in @("Create", "Recreate")) {
    $SshPublicKeyPath = Ensure-SshPublicKey -RequestedPath $SshPublicKeyPath
    $SshPublicKey = (Get-Content $SshPublicKeyPath -Raw).Trim()
    Write-Host "SSH Key geladen: $($SshPublicKey.Substring(0, [Math]::Min(40, $SshPublicKey.Length)))..." -ForegroundColor Gray
}

$CloudInit = $null
if ($Action -eq "Delete") {
    Remove-Server -TargetServer $ExistingServer -RemovalAction "DELETE"
    exit 0
}

if ($Action -eq "Recreate") {
    Remove-Server -TargetServer $ExistingServer -RemovalAction "RECREATE"
    Wait-ForServerDeletion -DeletedServerId $ExistingServer.id
}

if ($Action -in @("Create", "Recreate")) {
    $TemplatePath = Join-Path $ScriptDir "cloud-init.yml.tpl"
    $CloudInit = Get-CloudInitContent -TemplatePath $TemplatePath -ResolvedSshPublicKey $SshPublicKey -ResolvedTailscaleAuthKey $TailscaleAuthKey -ResolvedAccessMode $AccessMode
    New-Server -ResolvedCloudInit $CloudInit -ResolvedAccessMode $AccessMode
}

# Secrets aus dem Speicher entfernen
$HetznerApiToken = $null
$TailscaleAuthKey = $null
$CloudInit = $null
[System.GC]::Collect()
