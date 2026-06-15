# SKULD Monitoring – Konzept (Uptime Kuma + Authelia SSO)

Status: **Konzept**, Stand 2026-06-15. Ergänzt [`../README.md`](README.md) und das DevOps-Audit.

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

## Umsetzung – Schritte

Aufwand: **~3-4 h end-to-end**, keine DB-Änderung, kein Secret-Rotate-Bedarf.

### 1. Compose-Service ergänzen (~30 min)

In `docker-compose.yml`:

```yaml
  uptime-kuma:
    image: louislam/uptime-kuma:1
    container_name: uptime-kuma
    volumes:
      - ./uptime-kuma-data:/app/data
    networks:
      - web
      - postgres_setup_default        # für DB-Probe
    restart: unless-stopped

    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 256M
        reservations:
          cpus: '0.05'
          memory: 64M

    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.kuma.rule=Host(`monitoring.${BASE_DOMAIN:-skuld-options.com}`)"
      - "traefik.http.routers.kuma.entrypoints=${TRAEFIK_ENTRYPOINT}"
      - "${TRAEFIK_CERTRESOLVER_LABEL_KUMA}"
      - "traefik.http.routers.kuma.middlewares=authelia"
      - "traefik.http.services.kuma.loadbalancer.server.port=3001"

    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3001"]
      interval: 60s
```

In `.env.example` neu:
```
TRAEFIK_CERTRESOLVER_LABEL_KUMA=traefik.http.routers.kuma.tls.certresolver=letsencrypt
```
(Staging-Override in `docker-compose.testing.yml` analog zu skuld-frontend.)

### 2. DNS A-Record (5 min)

`monitoring.skuld-options.com → 91.98.156.116` beim Registrar setzen. Let's-Encrypt-Cert holt sich Traefik beim ersten Request automatisch.

### 3. Erstinstallation (~20 min)

```bash
ssh deploy@91.98.156.116
cd /opt/skuld
docker compose up -d uptime-kuma
# einmal Browser auf https://monitoring.skuld-options.com → Authelia-Login → Kuma-Setup-Wizard
# Dummy-Admin anlegen (Passwort egal, Authelia schützt davor),
# 2FA in Kuma AUS (Authelia macht das),
# Telegram-Notification anbinden mit existierendem TELEGRAM_BOT_TOKEN
```

### 4. Monitore anlegen (~1 h)

Liste aus Tabelle oben durchklicken. Kuma erlaubt JSON-Export → in `ops/uptime-kuma-monitors.json` versionieren.

### 5. Streamlit-Sidebar-Link (~10 min)

In `app.py` (oder wo die Sidebar zentral lebt):

```python
with st.sidebar:
    st.markdown(
        "[🩺 System Status](https://monitoring.skuld-options.com)",
        help="Live-Health aller SKULD-Services. Login wird automatisch übergeben.",
    )
```

Kein neuer Style, kein neuer State, kein neuer Auth-Code.

### 6. Backup (~10 min)

`./uptime-kuma-data/` enthält die SQLite mit Konfig + History. Ergänzen in `ops/backup_db.py` (oder als zweites Cron-Snippet):
```bash
0 3 * * *  tar czf /home/deploy/backups/kuma/kuma-$(date +\%F).tar.gz /opt/skuld/uptime-kuma-data
```
Retention: 7 Tage (kleine Files, ~5 MB).

### 7. README-Eintrag + Memo

`ops/README.md` Block "Monitoring" mit Link auf dieses Dokument.
Memory-Eintrag aktualisieren.

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
