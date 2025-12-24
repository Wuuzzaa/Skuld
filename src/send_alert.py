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
        logging.error("Telegram configuration missing. Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.")
        return

    # Format the message
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
        title = sys.argv[1]
        message = sys.argv[2]
        send_telegram_message(title, message)
    elif len(sys.argv) > 1:
        # Handle case where only one argument is passed
        send_telegram_message("SKULD Alert", sys.argv[1])
    else:
        print("Usage: python send_alert.py <title> <message>")
