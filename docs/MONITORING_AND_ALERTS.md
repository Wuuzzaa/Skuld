# Monitoring, RAM Logging & Telegram Alerts Setup

This guide documents how to implement the RAM monitoring and Telegram alert system used in SKULD. This setup allows for tracking memory usage during data collection and sending notifications for success, failure, or Out-Of-Memory (OOM) crashes.

## 1. Telegram Alert Script

Create a script to handle sending messages via the Telegram Bot API.

**File:** `src/send_alert.py`

```python
import requests
import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def send_telegram_message(title, message):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        logging.error("Telegram configuration missing.")
        return

    full_message = f"🚨 *{title}*\n\n{message}"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": full_message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logging.info(f"Telegram alert sent to chat ID {chat_id}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Telegram message: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 2:
        send_telegram_message(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        send_telegram_message("SKULD Alert", sys.argv[1])
```

## 2. Memory Monitoring Utilities

Implement utilities to check RSS memory usage and a background thread to log it periodically.

**File:** `src/util.py`

```python
import os
import threading
import time

def log_memory_usage(prefix=""):
    """Logs current memory usage and returns it in MB"""
    memory_mb = 0
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        print(f"{prefix} Current RSS Memory: {memory_mb:.2f} MB")
        return memory_mb
    except ImportError:
        # Fallback for Linux/Docker if psutil is missing
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        memory_mb = usage.ru_maxrss / 1024 
        print(f"{prefix} Max RSS Memory: {memory_mb:.2f} MB")
        return memory_mb
    except Exception as e:
        print(f"{prefix} Error checking memory: {e}")
        return None

class MemoryMonitor(threading.Thread):
    """
    Background thread to monitor and log memory usage periodically.
    Useful for debugging OOM crashes where the process dies before logging.
    """
    def __init__(self, interval=2.0):
        super().__init__()
        self.interval = interval
        self.stop_event = threading.Event()
        self.daemon = True

    def run(self):
        print(f"[Monitor] Starting memory monitor (interval={self.interval}s)...")
        while not self.stop_event.is_set():
            log_memory_usage("[Monitor] ")
            self.stop_event.wait(self.interval)

    def stop(self):
        self.stop_event.set()
```

## 3. Integration in Main Application

Start the memory monitor at the beginning of your script and log memory usage around tasks.

**File:** `main.py`

```python
from src.util import log_memory_usage, MemoryMonitor
# ... other imports

def main():
    # Start background memory monitor
    monitor = MemoryMonitor(interval=5.0)
    monitor.start()

    # ... your code ...
    
    # Example of logging specific task memory
    start_mem = log_memory_usage(f"[MEM] Start Task: ")
    # do_something()
    end_mem = log_memory_usage(f"[MEM] End Task: ")
    
    if start_mem and end_mem:
        print(f"Task consumed: {end_mem - start_mem:.2f} MB")
```

## 4. Shell Wrapper for OOM Detection

Create a shell script to run the python application. This script catches the exit code `137` (SIGKILL/OOM) and sends an alert.

**File:** `run_data_collection.sh`

```bash
#!/bin/bash
LOGFILE="/var/log/cron.log"

# Run data collection
cd /app/Skuld
/usr/local/bin/python main.py >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    # Success
    /usr/local/bin/python src/send_alert.py "SKULD Info: Success" "Data collection completed successfully." >> "$LOGFILE" 2>&1
elif [ $EXIT_CODE -eq 137 ]; then
    # OOM Killer detected
    echo "$(date): Data collection failed with OUT OF MEMORY (Exit Code 137)" >> "$LOGFILE"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Out of Memory" "The process was killed (Exit Code 137). Check logs." >> "$LOGFILE" 2>&1
else
    # Other errors
    echo "$(date): Failed with exit code $EXIT_CODE" >> "$LOGFILE"
fi
```

## 5. Docker & Deployment Configuration

### docker-compose.yml
Pass the secrets as environment variables.

```yaml
services:
  app:
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
```

### .github/workflows/deploy.yml
Inject the GitHub Secrets into the `.env` file on the server during deployment.

```yaml
      - name: Build and deploy
        run: |
          ssh ... << 'ENDSSH'
            cd /opt/skuld
            
            # Create .env file with secrets
            echo "TELEGRAM_BOT_TOKEN=${{ secrets.TELEGRAM_BOT_TOKEN }}" > .env
            echo "TELEGRAM_CHAT_ID=${{ secrets.TELEGRAM_CHAT_ID }}" >> .env
            
            sudo docker compose up -d
          ENDSSH
```

## 6. GitHub Secrets
Add these secrets to your repository settings:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
