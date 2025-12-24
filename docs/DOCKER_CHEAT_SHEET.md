# Wichtige Docker Befehle für SKULD

Hier ist eine Übersicht der wichtigsten Docker-Befehle, die für das Setup (`skuld-streamlit-vpn-test`) relevant sind.

## 🚀 Starten & Aktualisieren

**Container bauen und im Hintergrund starten:**
```bash
docker-compose up -d --build
```
> **Hinweis:** Nutze dies immer, wenn du Änderungen am Code (`src/`, `main.py` etc.) oder am `Dockerfile` gemacht hast.

## 📜 Logs & Monitoring

**Live-Logs aller Services anzeigen:**
```bash
docker-compose logs -f
```

**Logs nur für den Skuld-Container:**
```bash
docker logs -f skuld-streamlit-vpn-test
```
> Beenden mit `STRG + C`.

## 🛠 Debugging & Zugriff

**In den laufenden Container einloggen (Shell):**
```bash
docker exec -it skuld-streamlit-vpn-test /bin/bash
```
> Hier kannst du dann z.B. `python main.py` manuell ausführen oder SSH testen.

**Laufende Container anzeigen:**
```bash
docker ps
```

## 🛑 Stoppen

**Container stoppen und entfernen:**
```bash
docker-compose down
```

## 🧹 Aufräumen (Disk Space)

**Alles ungenutzte löschen (Vorsicht!):**
```bash
docker system prune -a
```
> Löscht gestoppte Container, nicht genutzte Netzwerke und **alle** Images, die nicht gerade von einem laufenden Container verwendet werden. Hilft oft bei "No space left on device".

**Nur den Build-Cache löschen:**
```bash
docker builder prune
```
