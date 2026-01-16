#!/bin/bash
#
# Mac/Linux Script to Manage Local DB (Rebuild & Restore)
#
# Usage:
#   ./manage_local_db.sh [path_to_dump_file]
#

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

echo -e "${CYAN}Checking configuration...${NC}"

# --- 1. Load or Init .env ---
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}.env file not found. Creating default.${NC}"
    cat <<EOT >> "$ENV_FILE"
DB_USER=dev
DB_PASS=dev
DB_NAME=skuld_dev
DB_PORT=5432
PGADMIN_EMAIL=admin@admin.com
PGADMIN_PASSWORD=admin
EOT
fi

# Read .env variables (ignoring comments)
export $(grep -v '^#' "$ENV_FILE" | xargs)

# Set defaults if missing
DB_USER=${DB_USER:-dev}
DB_PASS=${DB_PASS:-dev}
DB_NAME=${DB_NAME:-skuld_dev}
DB_PORT=${DB_PORT:-5432}
PGADMIN_EMAIL=${PGADMIN_EMAIL:-admin@admin.com}

# --- 2. Check Docker ---
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker is not running!${NC}"
    echo "Please start Docker Desktop/Daemon and try again."
    exit 1
fi

# --- 3. Determine Dump File ---
if [ -z "$DUMP_FILE" ]; then
    echo -e "${YELLOW}No args provided.${NC}"
    echo "Please provide path to dump file as argument:"
    echo "./manage_local_db.sh /path/to/dump.sql.gz"
    echo ""
    read -p "Or enter path now (Enter to skip restore, start empty): " INPUT_PATH
    DUMP_FILE=$INPUT_PATH
fi

# --- 4. Rebuild Environment ---
echo -e "\n${CYAN}=== STARTING FRESH REBUILD ===${NC}"

# Generate servers.json for pgAdmin
cat <<EOT > "$SERVERS_JSON"
{
    "Servers": {
        "1": {
            "Name": "Skuld Local ($DB_NAME)",
            "Group": "Servers",
            "Host": "skuld-local-db",
            "Port": 5432,
            "MaintenanceDB": "$DB_NAME",
            "Username": "$DB_USER",
            "SSLMode": "prefer",
            "PassFile": "/tmp/pgpass"
        }
    }
}
EOT

echo -e "${YELLOW}TEARING DOWN old containers and volumes...${NC}"
docker-compose -f "$COMPOSE_FILE" down -v

echo -e "${CYAN}STARTING new containers...${NC}"
docker-compose -f "$COMPOSE_FILE" up -d

# Wait for DB
echo -n "Waiting for Postgres..."
MAX_RETRIES=30
COUNT=0
CONNECTED=false

while [ $COUNT -lt $MAX_RETRIES ]; do
    if docker exec $CONTAINER_NAME bash -c "export PGPASSWORD=$DB_PASS; psql -U $DB_USER -d postgres -c '\q'" > /dev/null 2>&1; then
        CONNECTED=true
        break
    fi
    echo -n "."
    sleep 1
    COUNT=$((COUNT+1))
done
echo ""

if [ "$CONNECTED" = false ]; then
    echo -e "${RED}Timeout waiting for DB container.${NC}"
    exit 1
fi

# --- 5. Restoration Process ---
if [ ! -z "$DUMP_FILE" ]; then
    if [ ! -f "$DUMP_FILE" ]; then
        echo -e "${RED}File not found: $DUMP_FILE${NC}"
    else
        FULL_DUMP_PATH=$(realpath "$DUMP_FILE") # Ensure valid paths for docker cp
        DUMP_FILENAME=$(basename "$FULL_DUMP_PATH")
        CONTAINER_TMP_PATH="/tmp/$DUMP_FILENAME"

        echo -e "${YELLOW}Restoring from $DUMP_FILENAME...${NC}"
        docker cp "$FULL_DUMP_PATH" "$CONTAINER_NAME:$CONTAINER_TMP_PATH"

        # Create Role Admin if needed
        # docker exec $CONTAINER_NAME bash -c "export PGPASSWORD=$DB_PASS; psql -U $DB_USER -d postgres -c \"DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'admin') THEN CREATE ROLE admin; END IF; END \$\$;\""

        echo -e "${CYAN}Importing data...${NC}"
        
        if [[ "$DUMP_FILE" == *.gz ]]; then
            docker exec $CONTAINER_NAME bash -c "gunzip -c $CONTAINER_TMP_PATH | PGPASSWORD=$DB_PASS psql -U $DB_USER -d $DB_NAME"
        else
            docker exec $CONTAINER_NAME bash -c "PGPASSWORD=$DB_PASS psql -U $DB_USER -d $DB_NAME -f $CONTAINER_TMP_PATH"
        fi

        # Cleanup
        docker exec $CONTAINER_NAME rm $CONTAINER_TMP_PATH
        echo -e "${GREEN}Restore/Import finished.${NC}"
    fi
else
    echo -e "${YELLOW}Empty DB created (No dump file provided).${NC}"
fi

echo -e "--------------------------------------------------------"
echo -e "${GREEN}Local Environment Ready (FRESH BUILD)${NC}"
echo -e "Postgres: localhost:$DB_PORT (User: $DB_USER / Pass: $DB_PASS)"
echo -e "PgAdmin:  http://localhost:5050   (User: $PGADMIN_EMAIL / Pass from .env)"
echo -e "--------------------------------------------------------"
