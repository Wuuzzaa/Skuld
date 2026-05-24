#!/bin/bash
#
# Mac/Linux Script to Manage Local DB (Clean Rebuild & Restore)
# Matches functionality of manage_local_db.ps1
#

set -e

# --- Configuration ---
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ENV_FILE="$DIR/../.env"
COMPOSE_FILE="$DIR/../docker-compose.local-db.yml"
SERVERS_JSON="$DIR/servers.json"
CONTAINER_NAME="skuld-local-db"
DUMP_FILE="$1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Helper Functions ---

get_remote_dump_file() {
    local default_host="$1"
    local default_user="$2"
    local default_path="$3"
    local default_key="$4"

    echo -e "\n${CYAN}--- Remote Download Configuration ---${NC}" >&2
    
    read -p "Remote Host IP (Default: $default_host): " r_host
    r_host=${r_host:-$default_host}

    read -p "Remote User (Default: $default_user): " r_user
    r_user=${r_user:-$default_user}

    read -p "Remote Backup Folder (Default: $default_path): " r_path
    r_path=${r_path:-$default_path}

    read -p "Path to private SSH key (Leave empty for agent/default: $default_key): " r_key
    r_key=${r_key:-$default_key}

    # Expand tilde (~) manually if present (shell read does not expand it)
    case "$r_key" in 
        "~"*) r_key="${HOME}${r_key#"~"}" ;;
    esac

    SSH_CMD="ssh"
    SCP_CMD="scp"

    if [ -n "$r_key" ]; then
        if [ ! -f "$r_key" ]; then
            echo -e "${RED}SSH Key file not found: $r_key${NC}" >&2
            echo "Current User Home: $HOME" >&2
            exit 1
        fi
        SSH_CMD="ssh -i \"$r_key\""
        SCP_CMD="scp -i \"$r_key\""
    fi

    echo -e "${YELLOW}Verifying SSH connection to $r_user@$r_host...${NC}" >&2
    if ! eval $SSH_CMD -o BatchMode=yes -o StrictHostKeyChecking=no ${r_user}@${r_host} echo 'SSH_CONNECTION_OK' > /dev/null 2>&1; then
         echo -e "${RED}SSH Connection FAILED!${NC}" >&2
         echo "Check VPN, IP, User, or Key Permissions." >&2
         exit 1
    else
         echo -e "${GREEN}SSH Connection established.${NC}" >&2
    fi

    echo -e "${YELLOW}Checking $r_host for newest backup in $r_path...${NC}" >&2
    
    # ls -1t sorts by modification time (newest first). head -n 1 takes the top one.
    LATEST_FILE_REMOTE=$(eval $SSH_CMD -o StrictHostKeyChecking=no ${r_user}@${r_host} "ls -1t $r_path/*.sql* 2>/dev/null | head -n 1")

    if [ -z "$LATEST_FILE_REMOTE" ]; then
        echo -e "${RED}No .sql/.sql.gz files found in $r_path on $r_host${NC}" >&2
        exit 1
    fi

    FILENAME=$(basename "$LATEST_FILE_REMOTE")
    echo -e "${GREEN}Found newest backup: $FILENAME${NC}" >&2

    DOWNLOAD_DIR="$HOME/Downloads"
    LOCAL_FILE="$DOWNLOAD_DIR/$FILENAME"

    if [ -f "$LOCAL_FILE" ]; then
        # Prompting inside a captured function is tricky because stdout is captured.
        # We must read from /dev/tty explicitly if we are inside a capture block.
        # But for simplicity, we'll just check if it exists and use it, or ask user via stderr prompt.
        
        # Better: Assume yes if it exists to avoid UI glitches in capture mode, 
        # or print to stderr "Using existing file".
        echo -e "${YELLOW}File already exists locally ($LOCAL_FILE). Using it.${NC}" >&2
        echo "$LOCAL_FILE"
        return
    fi

    echo -e "${CYAN}Downloading to $LOCAL_FILE ...${NC}" >&2
    eval $SCP_CMD -o StrictHostKeyChecking=no "${r_user}@${r_host}:\"$LATEST_FILE_REMOTE\"" "\"$LOCAL_FILE\"" >&2

    if [ -f "$LOCAL_FILE" ]; then
        echo -e "${GREEN}Download complete.${NC}" >&2
        echo "$LOCAL_FILE"
    else
        echo -e "${RED}Download failed.${NC}" >&2
        exit 1
    fi
}

# --- 1. Load or Init .env ---
echo -e "${CYAN}Checking configuration...${NC}"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}.env file not found. Creating default.${NC}"
    cat <<EOT >> "$ENV_FILE"
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
EOT
    echo -e "${GREEN}.env file created at $ENV_FILE${NC}"
fi

# Read .env variables (handling potential quote issues simply)
# We trust the .env is simple KEY=VALUE
# We strip \r (CR) to handle files edited on Windows
set -a
if [ -f "$ENV_FILE" ]; then
    # Use temp file to strip carriage returns (more portable than process substitution)
    ENV_TEMP=$(mktemp)
    
    # 1. Strip CR
    # 2. Fix spaces around assignment (KEY = Val -> KEY=Val)
    # 3. Filter only lines that look like assignments or comments (avoids 'variable: command not found')
    tr -d '\r' < "$ENV_FILE" | sed 's/ *= */=/' | grep -E '^\s*#|^\s*[a-zA-Z_][a-zA-Z0-9_]*=' > "$ENV_TEMP"

    # source the temp file
    source "$ENV_TEMP"
    rm "$ENV_TEMP"
fi
set +a

# Defaults
DB_USER=${DB_USER:-dev}
DB_PASS=${DB_PASS:-dev}
DB_NAME=${DB_NAME:-skuld_dev}
DB_PORT=${DB_PORT:-5432}
PGADMIN_EMAIL=${PGADMIN_EMAIL:-admin@admin.com}
PGADMIN_PASSWORD=${PGADMIN_PASSWORD:-admin}
PGADMIN_PORT=${PGADMIN_PORT:-5051}

REMOTE_HOST_VAL=${REMOTE_DB_HOST:-"91.98.156.116"}
REMOTE_USER_VAL=${REMOTE_DB_USER:-"deploy"}
REMOTE_PATH_VAL=${REMOTE_DB_PATH:-"/home/deploy/backups/postgres"}
SSH_KEY_VAL=${SSH_KEY_PATH:-""}


# --- 2. Check Docker ---
if ! docker info > /dev/null 2>&1; then
    echo -e "${YELLOW}Docker is not running or not accessible. Trying to start...${NC}"
    open -a Docker || echo "Cannot start Docker automatically on this OS."
    
    echo "Waiting for Docker..."
    for i in {1..60}; do
        if docker info > /dev/null 2>&1; then
            echo -e "${GREEN}Docker is running!${NC}"
            break
        fi
        sleep 2
        echo -n "."
    done
    
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}Timeout waiting for Docker.${NC}"
        exit 1
    fi
fi

# --- 3. Determine Dump File ---
METHOD=""
if [ -z "$DUMP_FILE" ]; then
    echo "No dump file provided via arguments."
    echo "1) Select local file path"
    echo "2) Download latest from Remote Server ($REMOTE_HOST_VAL)"
    echo "3) Start with EMPTY database (Cancel/Skip)"
    
    read -p "Choose option [1/2/3]: " METHOD
    
    if [ "$METHOD" == "2" ]; then
        DUMP_FILE=$(get_remote_dump_file "$REMOTE_HOST_VAL" "$REMOTE_USER_VAL" "$REMOTE_PATH_VAL" "$SSH_KEY_VAL")
    elif [ "$METHOD" == "3" ]; then
        echo "Proceeding with empty DB."
        DUMP_FILE=""
    else
        read -p "Enter full path to local .sql/.gz file: " DUMP_FILE
        # Remove quotes if user added them
        DUMP_FILE=$(echo "$DUMP_FILE" | tr -d '"' | tr -d "'")
    fi
fi

# --- 4. Rebuild Environment ---
echo -e "\n${CYAN}=== STARTING FRESH REBUILD ===${NC}"

# Update servers.json
cat <<EOT > "$SERVERS_JSON"
{
    "Servers":  {
                        "1":  {
                                  "Username":  "$DB_USER",
                                  "MaintenanceDB":  "$DB_NAME",
                                  "Group":  "Servers",
                                  "SSLMode":  "prefer",
                                  "Name":  "Skuld Local ($DB_NAME)",
                                  "Host":  "skuld-local-db",
                                  "Port":  5432,
                                  "PassFile":  "/tmp/pgpass"
                              }
                }
}
EOT

echo -e "${YELLOW}TEARING DOWN old containers and volumes...${NC}"
docker-compose -f "$COMPOSE_FILE" down -v || true

echo -e "${CYAN}STARTING new containers...${NC}"
if ! docker-compose -f "$COMPOSE_FILE" up -d; then
    echo -e "${RED}Failed to start containers!${NC}"
    echo "Common reasons:"
    echo "1. Ports 5432 or 5050 are already in use by another service."
    echo "2. Docker is not running."
    exit 1
fi

echo -e "${CYAN}Waiting for connection to Postgres...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0
CAN_CONNECT=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker exec $CONTAINER_NAME bash -c "export PGPASSWORD=$DB_PASS; psql -U $DB_USER -d postgres -c '\q'" >/dev/null 2>&1; then
        CAN_CONNECT=true
        break
    fi
    sleep 1
    echo -n "."
    RETRY_COUNT=$((RETRY_COUNT+1))
done
echo ""

if [ "$CAN_CONNECT" = false ]; then
    echo -e "${RED}Could not connect to database container after waiting.${NC}"
    exit 1
fi

# --- 5. Restoration Process ---
if [ -n "$DUMP_FILE" ]; then
    if [ ! -f "$DUMP_FILE" ]; then
        echo -e "${RED}File not found: $DUMP_FILE${NC}"
    else
        DUMP_FILENAME=$(basename "$DUMP_FILE")
        CONTAINER_TMP_PATH="/tmp/$DUMP_FILENAME"
        
        echo -e "${YELLOW}Restoring from $DUMP_FILENAME...${NC}"
        docker cp "$DUMP_FILE" "$CONTAINER_NAME:$CONTAINER_TMP_PATH"
        
        echo -e "${CYAN}Ensuring role 'admin' exists...${NC}"
        ROLE_EXISTS=$(docker exec $CONTAINER_NAME bash -c "export PGPASSWORD=$DB_PASS; psql -U $DB_USER -d postgres -tAc \"SELECT 1 FROM pg_roles WHERE rolname='admin'\"")
        
        if [ "$ROLE_EXISTS" != "1" ]; then
            docker exec $CONTAINER_NAME bash -c "export PGPASSWORD=$DB_PASS; psql -U $DB_USER -d postgres -c \"CREATE ROLE admin NOLOGIN;\""
            echo "Role 'admin' created."
        else
            echo "Role 'admin' already exists."
        fi

        echo -e "${CYAN}Preparing target database '$DB_NAME'...${NC}"
        
        # Kill connections
        docker exec $CONTAINER_NAME bash -c "export PGPASSWORD=$DB_PASS; psql -U $DB_USER -d postgres -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();\"" > /dev/null
        
        # Drop and Create
        docker exec $CONTAINER_NAME bash -c "export PGPASSWORD=$DB_PASS; psql -U $DB_USER -d postgres -c \"DROP DATABASE IF EXISTS \\\"$DB_NAME\\\";\""
        docker exec $CONTAINER_NAME bash -c "export PGPASSWORD=$DB_PASS; psql -U $DB_USER -d postgres -c \"CREATE DATABASE \\\"$DB_NAME\\\";\""
        
        echo -e "${CYAN}Importing data...${NC}"
        if [[ "$DUMP_FILE" == *.gz ]]; then
            docker exec $CONTAINER_NAME bash -c "gunzip -c $CONTAINER_TMP_PATH | PGPASSWORD=$DB_PASS psql -U $DB_USER -d $DB_NAME"
        else
            docker exec $CONTAINER_NAME bash -c "PGPASSWORD=$DB_PASS psql -U $DB_USER -d $DB_NAME -f $CONTAINER_TMP_PATH"
        fi
        
        docker exec $CONTAINER_NAME rm "$CONTAINER_TMP_PATH"
        echo -e "${GREEN}Restore/Import finished.${NC}"
    fi
fi

echo -e "--------------------------------------------------------"
echo -e "${GREEN}Local Environment Ready (FRESH BUILD)${NC}"
echo -e "Postgres: localhost:$DB_PORT  (User: $DB_USER / Pass: $DB_PASS)" 
echo -e "PgAdmin:  http://localhost:$PGADMIN_PORT   (User: $PGADMIN_EMAIL / Pass from .env)" 
echo -e "--------------------------------------------------------"
