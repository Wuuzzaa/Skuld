<#
.SYNOPSIS
    Rebuilds the local development database environment (Clean Install).

.DESCRIPTION
    This script guarantees a FRESH local database environment.
    1. Checks/Starts Docker.
    2. Tears down existing containers and volumes (Wipes data!).
    3. Starts new containers.
    4. Restores from Dumpfile (if provided in args or selected in dialog).
    
.PARAMETER DumpFile
    Optional. The full path to the SQL dump file to import.
    If not provided, the script asks via dialog. If canceled, starts empty.

.EXAMPLE
    .\setup_scripts\manage_local_db.ps1
    .\setup_scripts\manage_local_db.ps1 -DumpFile "C:\backups\dump.sql.gz"
#>

param (
    [Parameter(Mandatory=$false)]
    [string]$DumpFile
)

$ErrorActionPreference = "Stop"

# --- Functions ---

function Show-FileOpenDialog {
    Add-Type -AssemblyName System.Windows.Forms
    $FileBrowser = New-Object System.Windows.Forms.OpenFileDialog
    $FileBrowser.Filter = "SQL Files (*.sql;*.gz)|*.sql;*.gz|All Files (*.*)|*.*"
    $FileBrowser.Title = "Select Database Dump File (Cancel for Empty DB)"
    if ($FileBrowser.ShowDialog() -eq "OK") {
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
        # Loop check
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
        Write-Warning "Could not find Docker Desktop at default location ($dockerPath)."
        Write-Warning "Please start Docker manually and re-run this script."
        exit 1
    }
}

# --- Configuration paths ---
$ScripRoot = $PSScriptRoot
$EnvFile = "$ScripRoot\..\.env"
$ComposeFile = "$ScripRoot\..\docker-compose.local-db.yml"
$ServersJsonFile = "$ScripRoot\servers.json"
$ContainerName = "skuld-local-db"

# --- 1. Load or Init .env ---
Write-Host "Checking configuration..." -ForegroundColor Cyan

if (-not (Test-Path $EnvFile)) {
    Write-Warning ".env file not found. Creating one with default values."
    $DefaultEnv = @"
DB_USER=dev
DB_PASS=dev
DB_NAME=skuld_dev
DB_PORT=5432
PGADMIN_EMAIL=admin@admin.com
PGADMIN_PASSWORD=admin
"@
    Set-Content -Path $EnvFile -Value $DefaultEnv
    Write-Host ".env file created at $EnvFile" -ForegroundColor Green
}

# Parse .env
$EnvVars = @{}
Get-Content $EnvFile | Where-Object { $_ -match '^\s*[^#]' -and $_ -like '*=*' } | ForEach-Object {
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

# --- 2. Check Docker ---
if (-not (Test-DockerRunning)) {
    Write-Warning "Docker is not running."
    Start-DockerDesktop
}

# --- 3. Determine Dump File (Interactive) ---
if ([string]::IsNullOrWhiteSpace($DumpFile)) {
    Write-Host "No dump file provided via arguments." -ForegroundColor Gray
    # Ask using GUI or Console
    $DumpFile = Show-FileOpenDialog
    
    if ([string]::IsNullOrWhiteSpace($DumpFile)) {
        Write-Host "No file selected. Proceeding with EMPTY database." -ForegroundColor Yellow
    }
}

# --- 4. Rebuild Environment ---
Write-Host "`n=== STARTING FRESH REBUILD ===" -ForegroundColor Magenta

# Ensure Servers JSON exists (for pgAdmin)
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
Set-Content -Path $ServersJsonFile -Value $serversJsonContent
Write-Host "pgAdmin config updated." -ForegroundColor Gray

Write-Host "TEARING DOWN old containers and volumes..." -ForegroundColor Yellow
# Using -v ensures volumes are removed (Data Wipe)
docker-compose -f $ComposeFile down -v
if ($LASTEXITCODE -ne 0) { Write-Warning "Cleanup had issues, proceeding..." }

Write-Host "STARTING new containers..." -ForegroundColor Cyan
docker-compose -f $ComposeFile up -d

# Wait for DB Ready
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
    if (-not (Test-Path $DumpFile)) {
        Write-Error "File not found: $DumpFile"
    } else {
        $DumpFileName = Split-Path $DumpFile -Leaf
        $ContainerTmpPath = "/tmp/$DumpFileName"
        
        Write-Host "Restoring from $DumpFileName..." -ForegroundColor Yellow
        docker cp "$DumpFile" "$ContainerName`:$ContainerTmpPath"

        # Create 'admin' role to prevent restore errors about missing roles.
        Write-Host "Ensuring role 'admin' exists..." -ForegroundColor Gray
        # We use simple SQL check instead of PL/pgSQL block to avoid shell escaping hell
        $checkRoleCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -tAc ""SELECT 1 FROM pg_roles WHERE rolname='admin'"""
        $roleExists = docker exec $ContainerName bash -c "$checkRoleCmd"
        
        if ($roleExists -ne "1") {
             $createRoleCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c ""CREATE ROLE admin NOLOGIN;"""
             docker exec $ContainerName bash -c "$createRoleCmd"
             Write-Host "Role 'admin' created."
        } else {
             Write-Host "Role 'admin' already exists."
        }

        # --- ENSURE CLEAN TARGET DB ---
        Write-Host "Preparing target database '$DB_NAME_VAL'..." -ForegroundColor Cyan
        
        # 1. Terminate connections
        $killCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c ""SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME_VAL' AND pid <> pg_backend_pid();"""
        docker exec $ContainerName bash -c "$killCmd" | Out-Null
        
        # 2. DROP
        $dropCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c ""DROP DATABASE IF EXISTS \""$DB_NAME_VAL\"";"""
        docker exec $ContainerName bash -c "$dropCmd"
        
        # 3. CREATE
        $createCmd = "export PGPASSWORD=$DB_PASS_VAL; psql -U $DB_USER_VAL -d postgres -c ""CREATE DATABASE \""$DB_NAME_VAL\"";"""
        docker exec $ContainerName bash -c "$createCmd"

        Write-Host "Importing data..." -ForegroundColor Cyan
        # Restore
        if ($DumpFile -match "\.gz$") {
                $restoreCmd = "gunzip -c $ContainerTmpPath | PGPASSWORD=$DB_PASS_VAL psql -U $DB_USER_VAL -d $DB_NAME_VAL"
                docker exec $ContainerName bash -c "$restoreCmd"
        } else {
                $restoreCmd = "PGPASSWORD=$DB_PASS_VAL psql -U $DB_USER_VAL -d $DB_NAME_VAL -f $ContainerTmpPath"
                docker exec $ContainerName bash -c "$restoreCmd"
        }
        
        # Cleanup
        docker exec $ContainerName rm $ContainerTmpPath
        Write-Host "Restore/Import finished." -ForegroundColor Green
    }
}

Write-Host "--------------------------------------------------------"
Write-Host "Local Environment Ready (FRESH BUILD)" -ForegroundColor Green
Write-Host "Postgres: localhost:$DB_PORT_VAL  (User: $DB_USER_VAL / Pass: $DB_PASS_VAL)" 
Write-Host "PgAdmin:  http://localhost:5050   (User: $PG_EMAIL_VAL / Pass from .env)" 
Write-Host "--------------------------------------------------------"
