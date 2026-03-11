<#
.SYNOPSIS
    Rebuilds the local development database environment (Clean Install).

.DESCRIPTION
    This script guarantees a FRESH local database environment.
    1. Checks/Starts Docker.
    2. Tears down existing containers and volumes (Wipes data!).
    3. Starts new containers.
    4. Restores from Dumpfile (local path, or automatic download from Hetzner).
    
.PARAMETER DumpFile
    Optional. The full path to the SQL dump file to import.
    If not provided, the script asks: "Download from Server" or "Select File".
#>

param (
    [Parameter(Mandatory=$false)]
    [string]$DumpFile
)

$ErrorActionPreference = "Stop"

# --- Functions ---

function Show-FileOpenDialog {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $FileBrowser = New-Object System.Windows.Forms.OpenFileDialog
    $FileBrowser.Filter = "SQL Files (*.sql;*.gz)|*.sql;*.gz|All Files (*.*)|*.*"
    $FileBrowser.Title = "Select Database Dump File (Cancel for Empty DB)"

    # Create dummy form to force dialog to foreground
    $Form = New-Object System.Windows.Forms.Form
    $Form.TopMost = $true
    $Form.StartPosition = "Manual"
    $Form.ShowInTaskbar = $false
    $Form.Opacity = 0
    $Form.Location = New-Object System.Drawing.Point(-20000, -20000)
    
    $Form.Show()
    [void]$Form.Focus()

    $result = $FileBrowser.ShowDialog($Form)
    
    $Form.Close()
    $Form.Dispose()

    if ($result -eq "OK") {
        return $FileBrowser.FileName
    }
    return $null
}

function Test-DockerRunning {
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $info = docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { return $true }
    } catch {
        return $false
    }
    return $false
}

function Start-DockerDesktop {
    Write-Host "Attempting to start Docker Desktop..." -ForegroundColor Yellow
    $dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerPath) {
        Start-Process -FilePath $dockerPath
        Write-Host "Docker Desktop started. Waiting for engine to initialize..." -ForegroundColor Yellow
        for ($i = 0; $i -lt 60; $i++) {
            Write-Host "." -NoNewline
            Start-Sleep -Seconds 2
            if (Test-DockerRunning) {
                Write-Host "`nDocker is now running!" -ForegroundColor Green
                return $true
            }
        }
        Write-Error "Timeout waiting for Docker to start."
    } else {
        Write-Error "Docker Desktop not found at default location. Please start manually."
    }
}

function Get-RemoteDumpFile {
    param (
        $RemoteHost,
        $RemoteUser,
        $RemotePath,
        $SshKey
    )

    Write-Host "`n--- Remote Download Configuration ---" -ForegroundColor Cyan
    
    # Prompt for Host
    $rHost = Read-Host "Remote Host IP (Default: $RemoteHost)"
    if ([string]::IsNullOrWhiteSpace($rHost)) { $rHost = $RemoteHost }

    # Prompt for User
    $rUser = Read-Host "Remote User (Default: $RemoteUser)"
    if ([string]::IsNullOrWhiteSpace($rUser)) { $rUser = $RemoteUser }

    # Prompt for Path
    $rPath = Read-Host "Remote Backup Folder (Default: $RemotePath)"
    if ([string]::IsNullOrWhiteSpace($rPath)) { $rPath = $RemotePath }

    # Prompt for SSH Key
    $keyInput = Read-Host "Path to private SSH key (Leave empty if using auto-agent or default: $SshKey)"
    if (-not [string]::IsNullOrWhiteSpace($keyInput)) { $SshKey = $keyInput }

    # Build commands
    $sshCmd = "ssh"
    $scpCmd = "scp"
    
    if (-not [string]::IsNullOrWhiteSpace($SshKey)) {
        if (-not (Test-Path $SshKey)) {
            Write-Error "SSH Key not found: $SshKey"
        }
        # Escape path for command line
        $sshCmd = "ssh -i ""$SshKey"""
        $scpCmd = "scp -i ""$SshKey"""
    }

    # --- Connectivity Check ---
    Write-Host "Verifying SSH connection to $rUser@$rHost..." -ForegroundColor Cyan
    $testCmd = "$sshCmd -o BatchMode=yes -o StrictHostKeyChecking=no ${rUser}@${rHost} echo 'SSH_CONNECTION_OK'"
    $testResult = Invoke-Expression $testCmd 2>&1
    
    if ("$testResult" -ne "SSH_CONNECTION_OK") {
        Write-Error "SSH Connection FAILED!`nDetails: $testResult`nHint: Check your VPN, IP, User, or SSH Key permissions."
    }
    Write-Host "SSH Connection established." -ForegroundColor Green

    Write-Host "Checking $rHost for newest backup in $rPath..." -ForegroundColor Yellow
    
    # Removed 2>/dev/null so we see if directory exists
    $findCmd = "$sshCmd -o StrictHostKeyChecking=no ${rUser}@${rHost} ""ls -1t $rPath/*.sql* | head -n 1"""
    
    try {
        $latestFile = Invoke-Expression $findCmd
    } catch {
        Write-Error "Command failed execution: $_"
    }

    if ([string]::IsNullOrWhiteSpace($latestFile) -or $latestFile -like "*No such file*") {
        Write-Error "No .sql/.sql.gz files found in $rPath on $rHost (or path does not exist). Output: $latestFile"
    }

    
    # Handle cases where ls returns full path or just filename
    $fileName = Split-Path $latestFile -Leaf
    
    Write-Host "Found newest backup: $fileName" -ForegroundColor Green
    
    $localDownloadPath = Join-Path $env:USERPROFILE "Downloads"
    $localFile = Join-Path $localDownloadPath $fileName

    if (Test-Path $localFile) {
        $overwrite = Read-Host "File already exists locally ($localFile). Download again? [Y/N]"
        if ($overwrite -match "^[nN]") {
             return $localFile
        }
    }

    Write-Host "Downloading $latestFile to $localFile ..." -ForegroundColor Cyan
    # Construct SCP command. Note the colon after host
    # Using quotes around paths to handle spaces
    $downloadCmd = "$scpCmd -o StrictHostKeyChecking=no ${rUser}@${rHost}:""$latestFile"" ""$localFile"""
    
    Invoke-Expression $downloadCmd

    if (Test-Path $localFile) {
        Write-Host "Download complete." -ForegroundColor Green
        return $localFile
    } else {
        Write-Error "Download failed."
    }
}

# --- Configuration paths ---
$ScriptPath = $PSScriptRoot
if (-not $ScriptPath) {
    if ($MyInvocation.MyCommand.Path) {
        $ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
    } else {
        $ScriptPath = Get-Location
    }
}

$EnvFile = Join-Path $ScriptPath "..\.env"
$ComposeFile = Join-Path $ScriptPath "..\docker-compose.local-db.yml"
$ServersJsonFile = Join-Path $ScriptPath "servers.json"

Write-Host "Script Root: $ScriptPath" -ForegroundColor Gray
Write-Host "Env File: $EnvFile" -ForegroundColor Gray

$ContainerName = "skuld-local-db"

# --- 1. Load or Init .env ---
Write-Host "Checking configuration..." -ForegroundColor Cyan

if (-not (Test-Path -Path $EnvFile)) {
    Write-Warning ".env file not found. Creating one with default values."
    $DefaultEnv = @"
DB_USER=dev
DB_PASS=dev
DB_NAME=skuld_dev
DB_PORT=5432
PGADMIN_EMAIL=admin@admin.com
PGADMIN_PASSWORD=admin
PGADMIN_PORT=5051
# Remote Backup Config
REMOTE_DB_HOST=91.98.156.116
REMOTE_DB_USER=deploy
REMOTE_DB_PATH=/home/deploy/backups/postgres
SSH_KEY_PATH=
"@
    Set-Content -Path $EnvFile -Value $DefaultEnv
    Write-Host ".env file created at $EnvFile" -ForegroundColor Green
}

# Parse .env
$EnvVars = @{}
Get-Content -Path $EnvFile | Where-Object { $_ -match '^\s*[^#]' -and $_ -like '*=*' } | ForEach-Object {
    $parts = $_.Split('=', 2)
    $key = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    if ($value -match '\s+#') {
        $value = $value -split '\s+#', 2 | Select-Object -First 1
        $value = $value.Trim()
    }
    $EnvVars[$key] = $value
}

$DB_USER_VAL = if ($EnvVars.ContainsKey("DB_USER")) { $EnvVars["DB_USER"] } else { "dev" }
$DB_PASS_VAL = if ($EnvVars.ContainsKey("DB_PASS")) { $EnvVars["DB_PASS"] } else { "dev" } 
$DB_NAME_VAL = if ($EnvVars.ContainsKey("DB_NAME")) { $EnvVars["DB_NAME"] } else { "skuld_dev" }
$DB_PORT_VAL = if ($EnvVars.ContainsKey("DB_PORT")) { $EnvVars["DB_PORT"] } else { 5432 }
$PG_EMAIL_VAL = if ($EnvVars.ContainsKey("PGADMIN_EMAIL")) { $EnvVars["PGADMIN_EMAIL"] } else { "admin@admin.com" }
$PG_PORT_VAL = if ($EnvVars.ContainsKey("PGADMIN_PORT")) { $EnvVars["PGADMIN_PORT"] } else { 5051 }

# Remote defaults
$REMOTE_HOST_VAL = if ($EnvVars.ContainsKey("REMOTE_DB_HOST")) { $EnvVars["REMOTE_DB_HOST"] } else { "91.98.156.116" }
$REMOTE_USER_VAL = if ($EnvVars.ContainsKey("REMOTE_DB_USER")) { $EnvVars["REMOTE_DB_USER"] } else { "deploy" }
$REMOTE_PATH_VAL = if ($EnvVars.ContainsKey("REMOTE_DB_PATH")) { $EnvVars["REMOTE_DB_PATH"] } else { "/home/deploy/backups/postgres" }
$SSH_KEY_VAL     = if ($EnvVars.ContainsKey("SSH_KEY_PATH"))     { $EnvVars["SSH_KEY_PATH"] }     else { "" }

# --- 2. Check Docker ---
if (-not (Test-DockerRunning)) {
    Write-Warning "Docker is not running."
    Start-DockerDesktop
}

# --- 3. Determine Dump File ---
$method = ""
if ([string]::IsNullOrWhiteSpace($DumpFile)) {
    Write-Host "No dump file provided via arguments." -ForegroundColor Gray
    Write-Host "1) Select local file"
    Write-Host "2) Download latest from Remote Server ($REMOTE_HOST_VAL)"
    Write-Host "3) Start with EMPTY database (Cancel/Skip)"
    
    $method = Read-Host "Choose option [1/2/3]"
    
    if ($method -eq "2") {
        $DumpFile = Get-RemoteDumpFile -RemoteHost $REMOTE_HOST_VAL -RemoteUser $REMOTE_USER_VAL -RemotePath $REMOTE_PATH_VAL -SshKey $SSH_KEY_VAL
    } elseif ($method -eq "3") {
        Write-Host "Proceeding with empty DB."
        $DumpFile = ""
    } else {
        $DumpFile = Show-FileOpenDialog
    }
}

if ([string]::IsNullOrWhiteSpace($DumpFile) -and $method -ne "3") {
     Write-Host "No file selected. Proceeding with EMPTY database." -ForegroundColor Yellow
}

# --- 4. Rebuild Environment ---
Write-Host "`n=== STARTING FRESH REBUILD ===" -ForegroundColor Magenta

$serversJsonContent = @{
    "Servers" = @{
        "1" = @{
            "Name" = "Skuld Local ($DB_NAME_VAL)";
            "Group" = "Servers";
            "Host" = "skuld-local-db";
            "Port" = 5432;
            "MaintenanceDB" = $DB_NAME_VAL;
            "Username" = $DB_USER_VAL;
            "SSLMode" = "prefer";
            "PassFile" = "/tmp/pgpass" 
        }
    }
} | ConvertTo-Json -Depth 3

if (-not [string]::IsNullOrWhiteSpace($ServersJsonFile)) {
    Set-Content -Path $ServersJsonFile -Value $serversJsonContent
    Write-Host "pgAdmin config updated at $ServersJsonFile" -ForegroundColor Gray
} else {
    Write-Warning "Could not determine path for servers.json. Skipping pgAdmin config."
}

Write-Host "TEARING DOWN old containers and volumes..." -ForegroundColor Yellow
docker-compose -f $ComposeFile down -v
if ($LASTEXITCODE -ne 0) { Write-Warning "Cleanup had issues, proceeding..." }

Write-Host "STARTING new containers..." -ForegroundColor Cyan
docker-compose -f $ComposeFile up -d

Write-Host "Waiting for connection to Postgres..." -ForegroundColor Cyan
$maxRetries = 30
$retryCount = 0
$canConnect = $false
while (-not $canConnect -and $retryCount -lt $maxRetries) {
    try {
        docker exec $ContainerName bash -c "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c '\q'" 2>$null
        if ($LASTEXITCODE -eq 0) { $canConnect = $true }
    } catch { Start-Sleep -Seconds 1 }
    $retryCount++
    if (-not $canConnect) { Start-Sleep -Seconds 1; Write-Host "." -NoNewline }
}
Write-Host ""

if (-not $canConnect) {
    Write-Error "Could not connect to database container after waiting."
}

# --- 5. Restoration Process ---
if (-not [string]::IsNullOrWhiteSpace($DumpFile)) {
    $DumpFile = $DumpFile -replace '"', ''
    
    if (-not (Test-Path $DumpFile)) {
        Write-Error "File not found: $DumpFile"
    } else {
        $DumpFileName = Split-Path $DumpFile -Leaf
        $ContainerTmpPath = "/tmp/$DumpFileName"
        
        Write-Host "Restoring from $DumpFileName..." -ForegroundColor Yellow
        docker cp "$DumpFile" "$ContainerName`:$ContainerTmpPath"

        Write-Host "Ensuring role 'admin' exists..." -ForegroundColor Gray
        $checkRoleCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -tAc ""SELECT 1 FROM pg_roles WHERE rolname='admin'"""
        $roleExists = docker exec $ContainerName bash -c "$checkRoleCmd"
        
        if ($roleExists -ne "1") {
             $createRoleCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c ""CREATE ROLE admin NOLOGIN;"""
             docker exec $ContainerName bash -c "$createRoleCmd"
             Write-Host "Role 'admin' created."
        } else {
             Write-Host "Role 'admin' already exists."
        }

        Write-Host "Preparing target database '$DB_NAME_VAL'..." -ForegroundColor Cyan
        
        $killCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c ""SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME_VAL' AND pid <> pg_backend_pid();"""
        docker exec $ContainerName bash -c "$killCmd" | Out-Null
        
        $dropCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c ""DROP DATABASE IF EXISTS \""$DB_NAME_VAL\"";"""
        docker exec $ContainerName bash -c "$dropCmd"
        
        $createCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c ""CREATE DATABASE \""$DB_NAME_VAL\"";"""
        docker exec $ContainerName bash -c "$createCmd"

        Write-Host "Importing data..." -ForegroundColor Cyan
        if ($DumpFile -match "\.gz$") {
                $restoreCmd = "gunzip -c $ContainerTmpPath | PGPASSWORD=$DB_PASS_VAL psql -U $DB_USER_VAL -d $DB_NAME_VAL"
                docker exec $ContainerName bash -c "$restoreCmd"
        } else {
                $restoreCmd = "PGPASSWORD=$DB_PASS_VAL psql -U $DB_USER_VAL -d $DB_NAME_VAL -f $ContainerTmpPath"
                docker exec $ContainerName bash -c "$restoreCmd"
        }
        
        docker exec $ContainerName rm $ContainerTmpPath
        Write-Host "Restore/Import finished." -ForegroundColor Green
    }
}

Write-Host "--------------------------------------------------------"
Write-Host "Local Environment Ready (FRESH BUILD)" -ForegroundColor Green
Write-Host "Postgres: localhost:$DB_PORT_VAL  (User: $DB_USER_VAL / Pass: $DB_PASS_VAL)" 
Write-Host "PgAdmin:  http://localhost:$PG_PORT_VAL   (User: $PG_EMAIL_VAL / Pass from .env)" 
Write-Host "--------------------------------------------------------"
