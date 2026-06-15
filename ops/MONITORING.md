# SKULD Monitoring – Uptime Kuma + Authelia SSO

Status: **Implementiert** auf Branch `feat/monitoring-kuma`. Stand 2026-06-15.

## Was im Repo liegt

| Datei | Zweck |
|---|---|
| `health/server.py` | Stdlib HTTP-Sidecar mit `/version`, `/health`, `/health/cron`. Reuses `skuld-app-image`, kein neuer Build. |
| `health/test_server.py` | 9 Unit-Tests (DB/Disk/Cron-Checks + HTTP-Routing). |
| `docker-compose.yml` (`skuld-health`) | Container für das Sidecar, Port 8800 intern, kein Traefik-Expose. |
| `docker-compose.yml` (`uptime-kuma`) | Kuma hinter Traefik mit `authelia` ForwardAuth-Middleware. |
| `app.py` (Sidebar-Block) | Markdown-Link "🩺 System Status" → `MONITORING_URL`. |
| `ops/backup-kuma.sh` | tar.gz-Snapshot von `uptime-kuma-data/` mit 7-Tage-Retention. |
| `.gitignore` | `uptime-kuma-data/` excluded. |

## Ziel

Eine eigene Monitoring-Oberfläche unter `monitoring.skuld-options.com`, die

1. Uptime/Health der SKULD-Services (Frontend, API, DB, Cron, externe Provider) live anzeigt,
2. von der **bestehenden Authelia-Session** abgesichert wird (kein zweiter Login),
3. aus der Streamlit-Sidebar per Link erreichbar ist – wer im Streamlit eingeloggt ist, kommt mit einem Klick rein.

Nice-to-have später: Push-Alerts in den vorhandenen Telegram-Bot, Statuspage public.

## Warum Uptime Kuma (und nicht Grafana/Prometheus)

| Anforderung | Kuma | Prom/Grafana |
|---|---|---|
| Setup-Zeit | < 30 min | 1-2 Tage |
| Eigenes Auth nötig? | Ja, abschaltbar via ForwardAuth | Ja |
| Push-Targets out-of-the-box (Telegram, Mail, Webhook) | ✅ 90+ | nur über AlertManager |
| HTTP/Keyword/JSON-Checks per Klick | ✅ | YAML-Gefummel |
| Ressourcen | ~80 MB RAM | 500 MB+ |
| Reicht für SKULD-Scope (≈10 Endpoints, 1 Server)? | ✅ | Overkill |

→ **Kuma jetzt, Prometheus später** wenn wir wirklich Metriken-Dashboards bauen wollen (Punkt 10 im Audit-Memo: Container-Logs Loki+Grafana). Das frisst sich nicht.

## SSO-Mechanik (das eigentliche Bonbon)

Wir nutzen die Authelia-Infrastruktur die **schon läuft**:

```
authelia/configuration.yml:
  session:
    domain: 'skuld-options.com'        ← Cookie gilt für ALLE Subdomains
  access_control.rules:
    - domain: '*.skuld-options.com'    ← jede Subdomain ist abgedeckt
      policy: 'one_factor'
```

Das bedeutet: sobald wir den neuen Service mit der `authelia` ForwardAuth-Middleware in Traefik registrieren, gilt:

- User logged sich auf `skuld-options.com` (Streamlit) ein → bekommt `authelia_session` Cookie auf `.skuld-options.com`.
- Klickt auf Sidebar-Link → Browser sendet dasselbe Cookie an `monitoring.skuld-options.com`.
- Traefik fragt Authelia → 200 OK → Kuma wird durchgereicht.
- **Kein separater Kuma-Login.** Kumas eigene Auth schalten wir ab (`UPTIME_KUMA_DISABLE_FRAME_SAMEORIGIN=0` + bei Erstinstall einen Dummy-User anlegen, dessen Login wir nie wieder brauchen, oder Reverse-Proxy-Mode wenn Kuma den anbietet).

Die "Login-Daten weitergeben"-Idee aus der ursprünglichen Frage ist sogar besser gelöst als geplant: wir geben **nichts** weiter, sondern die Session ist bereits gültig, weil Cookies an Subdomains vererben.

## Architektur

```
                ┌────────────────────────────────────┐
                │ Browser (User logged in @ Streamlit) │
                └───────────┬──────────────┬──────────┘
                            │              │
              skuld-options.com   monitoring.skuld-options.com
                            │              │
                            ▼              ▼
                    ┌──────────────────────────────┐
                    │         Traefik              │
                    │  router: skuld → authelia →  │
                    │  router: kuma  → authelia →  │
                    └────┬───────────────┬─────────┘
                         │               │
                    ┌─────────┐    ┌────────────┐
                    │ Streamlit│    │ Uptime Kuma│
                    └─────────┘    └────────────┘
                                          │ probes
                                          ▼
                ┌─────────────────────────────────────┐
                │ skuld-frontend  http://skuld-frontend:8501/_stcore/health
                │ skuld-backend   ./logs/last_cron.txt heartbeat
                │ postgres        TCP 5432 + select 1
                │ pgadmin / authelia / traefik /api/rawdata
                │ massive.com     external HTTPS
                │ openexchange    external HTTPS
                │ telegram bot    sendMessage echo
                └─────────────────────────────────────┘
```

## Was wir konkret monitoren

| Check | Typ | Intervall | Alert |
|---|---|---|---|
| Streamlit `/_stcore/health` | HTTP 200 | 60s | Telegram |
| FastAPI `/api/version` (siehe Audit #14) | HTTP + Keyword | 60s | Telegram |
| FastAPI `/api/health` (Audit #11 deeper health) | HTTP + JSON-Path `db_ok=true` | 60s | Telegram |
| Postgres TCP `db:5432` | TCP | 60s | Telegram |
| Cron-Heartbeat (letztes `nightly_historization` Logfile mtime < 26h) | HTTP gegen `/api/cron/last` | 30 min | Telegram |
| Authelia `/api/health` | HTTP | 5 min | Telegram |
| Traefik `/ping` | HTTP | 5 min | Telegram |
| massive.com API (key-pinged) | HTTP + Keyword | 10 min | Telegram |
| openexchangerates.org | HTTP | 30 min | – |
| SSL-Zertifikat skuld-options.com | TLS expiry | 1×/Tag | Warn 14 Tage |
| Disk-free (über `/api/health.disk_free_pct`) | HTTP + Number | 10 min | Telegram bei < 15 % |

Status-Page öffentlich? **Nein**, hinter Authelia. Falls später public erwünscht: Kuma kann eine `/status/foo` Seite ausstellen, die wir per zweitem Traefik-Router OHNE Middleware durchschalten.

## Deploy auf Prod

DNS ist gesetzt (`monitoring.skuld-options.com → 91.98.156.116`). Es bleibt:

### 1. PR mergen
Branch `feat/monitoring-kuma` → master. `deploy.yml` deployed automatisch.

### 2. (Einmalig) `.env` auf Server ergänzen

```bash
ssh deploy@91.98.156.116
cd /opt/skuld
# Default reicht — diese Zeilen sind nur nötig wenn man overriden will:
# echo 'MONITORING_DOMAIN=monitoring.skuld-options.com' >> .env
# echo 'TRAEFIK_CERTRESOLVER_LABEL_KUMA=traefik.http.routers.kuma.tls.certresolver=letsencrypt' >> .env
# echo 'MONITORING_URL=https://monitoring.skuld-options.com' >> .env
```

Die Defaults im `docker-compose.yml` decken den Prod-Fall ab. Staging (testing.yml) müsste analog zu skuld-frontend `MONITORING_MIDDLEWARES=` (leer) setzen.

### 3. `TRAEFIK_CERTRESOLVER_LABEL_KUMA` setzen

Im Prod-`.env` auf dem Server – analog zu `TRAEFIK_CERTRESOLVER_LABEL_SKULD`. Ohne diese Zeile bleibt Kuma per HTTP erreichbar (Traefik holt kein Cert). Beispiel:

```
TRAEFIK_CERTRESOLVER_LABEL_KUMA=traefik.http.routers.kuma.tls.certresolver=letsencrypt
```

### 4. Erstinstallation

```bash
docker compose up -d skuld-health uptime-kuma
# Browser: https://monitoring.skuld-options.com
# → Authelia-Login (oder bereits gültige Session) → Kuma Setup-Wizard
# Dummy-Admin anlegen (Authelia schützt davor, Passwort egal)
# 2FA in Kuma AUS, Telegram-Notification mit existierendem TELEGRAM_BOT_TOKEN
```

### 5. Monitore anlegen

| Probe | URL/Target | Intervall |
|---|---|---|
| Streamlit Frontend | `http://skuld-frontend:8501/_stcore/health` | 60s |
| Health-Sidecar `/version` | `http://skuld-health:8800/version` | 60s |
| Health-Sidecar `/health` | `http://skuld-health:8800/health` (200/503) | 60s |
| Health-Sidecar `/health/cron` | `http://skuld-health:8800/health/cron` | 30 min |
| Postgres TCP | `db:5432` | 60s |
| Authelia | `http://authelia:9091/api/health` | 5 min |
| Traefik | `http://traefik:8080/ping` | 5 min |
| massive.com (extern) | `https://api.unusualwhales.com/...` | 10 min |
| SSL-Cert | `https://skuld-options.com` (cert expiry) | 1×/Tag |

Nach dem Anlegen: in Kuma "Settings → Backup → Export" ziehen, in `ops/uptime-kuma-monitors.json` versionieren.

### 6. Cron für Backup

```bash
crontab -e
# einfügen:
30 3 * * * /opt/skuld/ops/backup-kuma.sh >> /home/deploy/backups/kuma.log 2>&1
```

## Was es NICHT ersetzt

- **Logs zentralisieren** (Audit #10) – Kuma macht Probes, keine Log-Aggregation. Loki/Promtail bleibt offen.
- **Backup-Verifizierung** (Audit-Followup) – Kuma weiß nicht ob `pg_dump` restorebar ist. Smoke-Restore Job bleibt offen.
- **Performance-Metrics** (Latenz-P95, DB-QPS) – Prometheus-Thema.

## Risiken / Edge Cases

- **Erstes Setup ohne Auth-Schutz**: Kuma bietet beim allerersten Request einen offenen Setup-Wizard. Solange wir den Service hinter Authelia von Anfang an exposen, ist das harmlos. Trotzdem: nach Setup `disableSetup: true` in Kuma-Settings prüfen.
- **Cookie-Domain-Mismatch im Staging**: Wenn wir auf `skuld-test.example.com` deployen, gilt das Authelia-Cookie nicht für `monitoring.skuld-test.example.com` – da müssten wir Authelia-Domain anpassen. Für Prod (alles unter `*.skuld-options.com`) kein Thema.
- **Kuma als single point of monitoring**: wenn der Server selbst stirbt, sieht Kuma das nicht. Externer Watchdog (UptimeRobot Free, BetterStack Free Tier) für die ROOT-Health auf den Server zusätzlich – 5 min, kostenlos.

## Offen / Entscheidungspunkte

- [ ] DNS-Record-Anlage – User-Action
- [ ] Push-Channel: nur Telegram oder auch Mail/Discord?
- [ ] Status-Page später public ja/nein?
- [ ] Externer Watchdog (UptimeRobot) zusätzlich ja/nein?

## Querbezüge

- DevOps-Audit 2026-06-14 – diese Datei deckt den Bereich "Observability lite" ab
- DevOps-Session 2026-06-15 – Punkt #11 (deeper health) ist Voraussetzung für die JSON-Path-Probes
- `authelia/configuration.yml` – `session.domain` und `access_control.rules` sind die Knöpfe an denen das hängt
- `docker-compose.yml` – Vorbild für Labels: skuld-frontend Block, identisches Muster
