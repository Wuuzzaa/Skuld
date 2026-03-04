# Skuld Local LLM Log Summarizer

Dieses Setup betreibt ein 100% lokales, gekapseltes LLM (Llama 3.2 3B via Ollama), welches täglich die Skuld Data Collector Logs auf Fehler (ERROR, WARNING, Exception) scannt, diese zusammenfasst und dir den Bericht direkt per Telegram schickt. 

Das Setup ist vom Rest der Skuld-Applikation vollkommen unabhängig.

## Voraussetzungen
Die Zugangsdaten deines Telegram-Bots müssen in der `.env` Datei im Hauptordner (`/Skuld/.env`) hinterlegt sein:
- `TELEGRAM_BOT_TOKEN="Dein-Token"`
- `TELEGRAM_CHAT_ID="Deine-ID"`

## Installation & Start auf dem Server (Hetzner / Homeserver)

1. Wechsle auf diesen Branch:
   ```bash
   git fetch
   git checkout feature/llm-log-summarizer
   git pull origin feature/llm-log-summarizer
   ```

2. Starte die Container über das separate Compose-File **aus dem Hauptordner** der Skuld Applikation (wo deine `.env` liegt):
   ```bash
   docker compose -f docker-compose.llm.yml up -d
   ```

3. Das Setup lädt sich das Modell beim ersten Start herunter und führt sofort eine Analyse der heutigen Logs durch, die du als Telegram-Nachricht erhalten solltest. 

## Wie es funktioniert
- `ollama`: Dieser Container lädt das Llama-3.2-3B Modell herunter und stellt die Generierungs-API zur Verfügung. Keine Daten verlassen deinen Server.
- `log-summarizer`: Dieser Container mountet den `$PWD/logs` Ordner als "read-only". Er startet das Python-Skript `summarize_logs.py` sofort beim Boot und installiert danach einen Cronjob, der das Skript jeden Tag um 21:00 Serverzeit erneut ausführt.

## Abbauen
Um das LLM wieder zu stoppen, führe einfach aus:
```bash
docker compose -f docker-compose.llm.yml down
```
