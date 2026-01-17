# Skuld

https://app.skuld-options.com/

## Local Development Setup

This project uses Docker to manage the local PostgreSQL database and `streamlit` for the frontend.

### Prerequisites

*   **Docker Desktop** (must be installed and running)
*   **Python 3.10+**
*   **Git**

### Database Management (One-Click Setup)

We provide helper scripts to automatically manage the local database lifecycle. These scripts will:
1.  Check if Docker is running (and start it if needed).
2.  **Wipe existing data** to ensure a clean state.
3.  Start the containers (`db` and `pgadmin`).
4.  Optionally **download the latest production backup** via SSH and restore it.

#### Windows (PowerShell)
```powershell
.\setup_scripts\manage_local_db.ps1
```

#### Mac / Linux (Bash)
```bash
chmod +x ./setup_scripts/manage_local_db.sh
./setup_scripts/manage_local_db.sh
```

---

### Remote Database Import & SSH Configuration

The scripts support downloading the latest database dump directly from the production server.

#### Process
When running the script, choose **Option 2: Download latest from Remote Server**.
The script will prompt for:
1.  **Remote Host** (Default: stored in `.env` as `REMOTE_DB_HOST`)
2.  **Remote User** (Default: stored in `.env` as `REMOTE_DB_USER`)
3.  **Remote Path** (Default: stored in `.env` as `REMOTE_DB_PATH`)
4.  **SSH Key Path**

#### Handling SSH Keys

To connect to the server securely, you need your SSH Private Key. The script supports two methods:

**Method A: SSH Agent (Recommended)**
If you have your key added to your local SSH agent (or it is the default `~/.ssh/id_rsa`), simply **press Enter** when prompted for the key path.

**Method B: Specific Key File**
If you have multiple keys or keep them in a specific location, provide the **absolute path** when prompted.

*   **Windows Example:** `C:\Users\Name\.ssh\hetzner_ed25519`
*   **Mac/Linux Example:** `/Users/name/.ssh/hetzner_ed25519`

#### Permanent Configuration (.env)
You can save your defaults in the `.env` file to skip typing them every time (except the key path, which typically defaults to empty for security/agent usage, but can be set if desired).

```dotenv
# .env
REMOTE_DB_HOST=91.98.156.116
REMOTE_DB_USER=deploy
REMOTE_DB_PATH=/home/deploy/backups/postgres
SSH_KEY_PATH=C:\Users\MyName\.ssh\my_key  # Optional: Set default key path
```
