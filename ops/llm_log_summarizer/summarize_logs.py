import os
import glob
import logging
import requests
import json
from datetime import datetime

# Setup basic logging for the container output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OLLAMA_URL = "http://ollama:11434/api/generate"
MODEL_NAME = "llama3.2:3b"
LOGS_DIR = "/logs/data_collector"

def get_latest_log_file():
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_dir = os.path.join(LOGS_DIR, today_str)
    
    if not os.path.exists(today_dir):
        logger.warning(f"No log directory found for today: {today_dir}")
        return None
        
    log_files = glob.glob(os.path.join(today_dir, "*.log"))
    if not log_files:
        logger.warning(f"No log files found in directory: {today_dir}")
        return None
        
    # Get the most recently modified log file
    latest_file = max(log_files, key=os.path.getmtime)
    logger.info(f"Latest log file found: {latest_file}")
    return latest_file

def extract_errors(file_path):
    errors = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                lower_line = line.lower()
                if 'error' in lower_line or 'warning' in lower_line or 'exception' in lower_line:
                    errors.append(line.strip())
    except Exception as e:
        logger.error(f"Failed to read log file {file_path}: {e}")
        
    return errors

def summarize_with_ollama(errors):
    if not errors:
        return "Keine Fehler oder Warnungen im heutigen Log gefunden! 🎉"
        
    # Limit errors to avoid overflowing context window (take last 50 errors roughly)
    errors_text = "\n".join(errors[-50:])
    
    prompt = f"""Du bist ein technischer Assistent, der Log-Dateien für ein Data-Collector-Skript überwacht.
Bitte fass die folgenden Fehler und Warnungen zusammen und gib eine kurze, prägnante Diagnose in deutscher Sprache. 
Wenn die Fehler unbedeutend sind, sag das.

Hier sind die Fehler:
{errors_text}

Fasse sie in 2-3 Sätzen zusammen:"""

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "Keine gültige Antwort vom LLM erhalten.")
    except Exception as e:
        logger.error(f"Error calling Ollama API: {e}")
        return f"Fehler beim Aufruf des lokalen LLM: {str(e)}"

def send_telegram_message(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables are not set.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🤖 **LLM Log-Analyse**\n\n{message}",
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Successfully sent telegram message.")
    except Exception as e:
        logger.error(f"Failed to send telegram message: {e}")

def main():
    logger.info("Starting log summarization process...")
    
    # 1. Find latest log
    log_file = get_latest_log_file()
    if not log_file:
        logger.info("Exiting: No log file to process.")
        return
        
    # 2. Extract errors
    errors = extract_errors(log_file)
    logger.info(f"Found {len(errors)} error/warning lines in {log_file}")
    
    # Optional: If no errors, we might want to skip sending a daily "all good" message 
    # to avoid spam, unless requested. For now, let's send it so we know it works.
    
    # 3. Summarize with LLM
    summary = summarize_with_ollama(errors)
    logger.info(f"LLM Summary: {summary}")
    
    # 4. Send to Telegram
    send_telegram_message(summary)

if __name__ == "__main__":
    main()
