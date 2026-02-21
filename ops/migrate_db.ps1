# Database Migration Script: Hetzner -> Home Server via Local

$ErrorActionPreference = "Stop"

# Configuration
$ProdUser = "deploy"
$ProdHost = "91.98.156.116"
$ProdDB = "Skuld"
# Production container name (Standard stack usually uses this, verify if different)
$ProdContainer = "postgres_setup-db-1" 

$TestUser = "daniel"
$TestHost = "192.168.0.235"
$TestKey = "$HOME/.ssh/Dell_homeserver"
$TestDB = "Skuld" 
# Staging/Test container name (Based on deploy file 'POSTGRES_HOST=postgres', 
# checking docker-compose usually yields project_service_1)
$TestContainer = "skuld_staging_db"



Write-Host "=== Starting Database Migration ==="
Write-Host "FROM: $ProdHost ($ProdDB)"
Write-Host "TO:   $TestHost ($TestDB)"
Write-Host "VIA:  Local Machine"
Write-Host ""

$Activity = "Database Migration"
Write-Progress -Activity $Activity -Status "Starting Pre-flight Checks..." -PercentComplete 0

# 0. Pre-flight Checks
Write-Host "0. Pre-flight Checks..."
Write-Host "   Testing connection to PRODUCTION ($ProdHost)..." -NoNewline
try {
    # Use -o BatchMode=yes to fail fast if key/auth is wrong, -o ConnectTimeout=5 for network issues
    $null = ssh -q -o BatchMode=yes -o ConnectTimeout=5 $ProdUser@$ProdHost "exit" 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green }
    else { throw "Failed" }
} catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Error "Could not connect to Production host via SSH. Check VPN/Network/Keys."
    exit 1
}

Write-Host "   Testing connection to TEST SERVER ($TestHost)..." -NoNewline
try {
    $null = ssh -q -o BatchMode=yes -o ConnectTimeout=5 -i $TestKey $TestUser@$TestHost "exit" 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host " OK" -ForegroundColor Green }
    else { throw "Failed" }
} catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Error "Could not connect to Test host via SSH. Check Network/Keys/Path ($TestKey)."
    exit 1
}
Write-Host ""

# 1. Find and Download Latest Backup
Write-Progress -Activity $Activity -Status "1. Finding Latest Backup..." -PercentComplete 10
Write-Host "1. Finding latest backup on Production..."

# Find the latest .sql.gz file (ignoring path, just getting the filename might be safer if we assume path, or get full path)
# We assume the user's path verify: ~/backups/postgres/
try {
    # Get the latest backup
    $LatestBackup = ssh $ProdUser@$ProdHost "ls -t ~/backups/postgres/skuld_*.sql.gz | head -n 1"
    if (-not $LatestBackup) { throw "No backup found" }
} catch {
    Write-Error "Could not find any .sql.gz backup in ~/backups/postgres/. Check the server."
    exit 1
}
Write-Host "   Found: $LatestBackup"

$LocalDumpFile = "skuld_restore.sql.gz"
Write-Progress -Activity $Activity -Status "Downloading $LatestBackup..." -PercentComplete 20
Write-Host "   Downloading to $LocalDumpFile..."
# Use scp to download
scp "${ProdUser}@${ProdHost}:${LatestBackup}" $LocalDumpFile
if ($LASTEXITCODE -ne 0) { Write-Error "Failed to download backup."; exit 1 }
Write-Host "   Download complete."

# 2. Upload to Test Server
Write-Progress -Activity $Activity -Status "2. Uploading Dump to Test Server..." -PercentComplete 40
Write-Host "2. Uploading Dump to Test Server..."
scp -i $TestKey $LocalDumpFile "${TestUser}@${TestHost}:/tmp/$LocalDumpFile"
if ($LASTEXITCODE -ne 0) { Write-Error "Failed to upload dump to test server."; exit 1 }
Write-Host "   Upload complete."

# 3. Restore on Test Server
Write-Progress -Activity $Activity -Status "3. Restoring on Test Server..." -PercentComplete 70
Write-Host "3. Restoring on Test Server..."
$RestoreCmd = @"
    echo 'Stopping interfering services...'
    docker stop skuld-frontend skuld-backend || true 
    
    echo 'Dropping and Recreating Database...'
    # Use explicit pipe to psql connecting to default 'postgres' db
    echo "DROP DATABASE IF EXISTS \"Skuld\"; CREATE DATABASE \"Skuld\";" | docker exec -i $TestContainer psql -U admin -d postgres
    
    echo 'Restoring Data from GZ...'
    # Use zcat to decompress on the fly and pipe to docker
    zcat /tmp/$LocalDumpFile | docker exec -i $TestContainer psql -U admin -d Skuld
    
    echo 'Cleaning up dump...'
    rm /tmp/$LocalDumpFile

    echo 'Restarting services...'
    docker start skuld-frontend skuld-backend || true
"@

# Fix argument formatting by piping the script content over SSH to bash
# This avoids issues with quotes getting stripped or misinterpreted by SSH argument parsing
$RestoreCmd -replace "`r", "" | ssh -i $TestKey $TestUser@$TestHost "bash -s"
if ($LASTEXITCODE -ne 0) { Write-Error "Failed to restore on test server. Check container name ($TestContainer)."; exit 1 }

Write-Progress -Activity $Activity -Status "Migration Completed!" -PercentComplete 100 -Completed
Write-Host ""
Write-Host "=== Migration Completed Successfully! ==="
Write-Host "You may need to restart the Test Application."

# 4. Cleanup Local Dump
Write-Host "4. Cleaning up local dump file..."
Remove-Item $LocalDumpFile -ErrorAction SilentlyContinue
Write-Host "   Cleanup complete."
