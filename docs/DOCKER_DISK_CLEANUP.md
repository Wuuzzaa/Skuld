# 📘 Learning: Docker Disk Space Management & Troubleshooting

**Szenario:** Deployment schlägt fehl (`rsync error: No space left on device`) oder der Server reagiert träge, weil die Festplatte voll ist.

---

## 1. 🔍 Analyse: Wo ist der Speicherplatz hin?

Bevor du blind löschst, finde heraus, was den Platz verbraucht.

### Schritt 1.1: Gesamtspeicher prüfen
Verschaffe dir einen Überblick über die Partitionen.
```bash
df -h
```
*   Achte auf die Spalte `Use%` bei `/` (Root). Wenn hier 90-100% steht, ist die Platte voll.

### Schritt 1.2: Die größten Verzeichnisse finden
Finde heraus, welcher Ordner der Übeltäter ist.
```bash
sudo du -h /var | sort -rh | head -n 10
```
*   **Ergebnis-Interpretation:**
    *   `/var/lib/docker`: Docker Images, Container & Volumes (meistens das Problem).
    *   `/var/log`: System-Logs (können bei Fehlern explodieren).

---

## 2. 🐳 Ursache: Docker (Der häufigste Grund)

Docker behält standardmäßig **alles**: alte Images nach Updates, gestoppte Container, Build-Caches und nicht genutzte Volumes.

### Schritt 2.1: Docker aufräumen (Die "Atombombe")
Dieser Befehl löscht alles, was nicht *aktiv* von einem *laufenden* Container verwendet wird.
**⚠️ Achtung:** Löscht auch Volumes, die nicht gemountet sind!

```bash
sudo docker system prune -af --volumes
```
*   `-a`: Löscht alle ungenutzten Images (nicht nur "dangling").
*   `-f`: Force (keine Rückfrage).
*   `--volumes`: Löscht auch ungenutzte Volumes.

### Schritt 2.2: Docker Logs leeren (ohne Container-Neustart)
Manchmal schreibt ein Container (z.B. Streamlit im Loop) Gigabytes an Logs.
```bash
sudo sh -c 'truncate -s 0 /var/lib/docker/containers/*/*-json.log'
```

---

## 3. 📜 Ursache: System Logs

Wenn eine App crasht und neustartet (Crash-Loop), können Logs wie `syslog` oder `journal` riesig werden.

### Schritt 3.1: Journald aufräumen
```bash
# Behalte nur die Logs der letzten Sekunde (löscht alles Alte)
sudo journalctl --vacuum-time=1s

# Oder: Begrenze auf eine feste Größe
sudo journalctl --vacuum-size=100M
```

---

## 4. 🛠️ Prävention & Automatisierung

Damit das nicht wieder passiert, baue Sicherheitsnetze ein.

### Schritt 4.1: GitHub Actions (Deployment)
Füge vor dem `rsync` oder Build-Schritt einen Cleanup-Befehl ein, um Platz für das neue Deployment zu schaffen.

```yaml
- name: Pre-cleanup on server
  run: |
    ssh user@host "sudo docker system prune -af --volumes || true"
```

### Schritt 4.2: Docker Logging begrenzen (`docker-compose.yml`)
Verhindere, dass Container-Logs unendlich wachsen. Füge dies zu jedem Service hinzu:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### Schritt 4.3: Cronjob (Optional)
Ein täglicher Cronjob auf dem Server, der aufräumt:
```bash
# crontab -e
0 4 * * * docker system prune -af --volumes > /dev/null 2>&1
```
*(Löscht jeden Tag um 04:00 Uhr alles Unnötige)*

---

## ⚡ Schnell-Checkliste für den Notfall

Wenn nichts mehr geht, kopiere diesen Block und führe ihn auf dem Server aus:

```bash
# 1. Docker komplett aufräumen
sudo docker system prune -af --volumes

# 2. Docker Logs leeren
sudo sh -c 'truncate -s 0 /var/lib/docker/containers/*/*-json.log'

# 3. System Logs leeren
sudo journalctl --vacuum-time=1s

# 4. Apt Cache leeren
sudo apt-get clean

# 5. Ergebnis prüfen
df -h
```
