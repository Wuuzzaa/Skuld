# SKULD Portable DevOps — Design-Spec

**Datum:** 2026-07-11
**Branch:** `feature/portable-devops`
**Status:** Entwurf zur Freigabe
**Autor:** Daniel (Interview) + Claude (Design)

---

## 1. Ziel & Motivation

SKULD ist heute faktisch an Hetzner gebunden (Hetzner-Cloud-API im `provision-hetzner.ps1`,
hetzner-spezifisches `cloud-init.yml.tpl`, feste IP `91.98.156.116` in `environments.yaml`).

**Kernziel:** SKULD **hoster-unabhängig** machen — auf *jedem* Linux-Host (beliebiger Anbieter,
Root-Server, Bare-Metal) in wenigen Minuten reproduzierbar aufsetzbar, mit **minimalem manuellem
Aufwand**. Auslöser-Szenario: „Ich muss kurzfristig komplett von Hetzner weg."

**Drei feste Anforderungen des Users:**
1. **Hoster-unabhängig, Stufe 1** („bring your own Linux box"): Der Server wird beim Anbieter
   *manuell* bestellt; *alles ab „ich habe IP + Zugang"* ist ein einziger, hoster-neutraler Ablauf.
   Die Server-*Beschaffung* per API (Stufe 2) ist **nicht** Teil dieses Projekts.
2. **Prod und Test physisch getrennt** — keine Vermischung, ein Test-Deploy darf Prod technisch
   nicht erreichen können.
3. **Felsenfestes Runbook** — so lückenlos dokumentiert, dass ein kompletter Neuling (oder der
   User selbst unter Stress) es fehlerfrei befolgen kann. Das Runbook enthält sicherheitsrelevante
   Abläufe und liegt daher **auf dem Desktop, NICHT im öffentlichen GitHub-Repo**.

**Erste Bewährungsprobe:** Ein bereits laufender Server bei einem *anderen* Anbieter (nicht Hetzner)
wird als künftiges Prod aufgesetzt — zunächst als isolierte Testumgebung, dann bei Bewährung
Umschaltung auf Prod. Das aktuelle Hetzner-Prod bleibt dabei zu jedem Zeitpunkt unangetastet.

---

## 2. Ist-Zustand (verifiziert 2026-07-11)

Das Setup ist bereits zu ~85 % solide. Vorhanden und funktionierend:

- **Deploy-Pipeline** (`.github/workflows/deploy.yml`): push auf `master` → auto-Deploy nach
  `production`; `workflow_dispatch` erlaubt manuelles Deploy nach `production` oder `home`.
  Guard-Job blockiert Nicht-master-Refs für `production`.
- **Universelles Provisioning-Skript** (`ops/provision-server.sh`): bereits „SKULD Universal Server
  Provisioning", idempotent, für „any blank Ubuntu 22.04/24.04", per SSH-pipe ausführbar.
  10 Module: System-Update, deploy-User, SSH-Hardening, UFW, Docker, daemon.json (`iptables:false`),
  Docker-Netzwerke, App-Dir, GitHub-Runner, optional Cloudflare-Tunnel.
- **Hetzner-Bequemlichkeits-Layer**: `ops/provision-hetzner.ps1` (erstellt Server via Hetzner-API)
  + `ops/cloud-init.yml.tpl` (härtet beim Boot).
- **Environment-Config** (`ops/environments.yaml`): `production` (Hetzner) + `home` (Homeserver,
  self-hosted Runner, `docker-compose.testing.yml`, DB-Container `skuld_staging_db`).
- **CLI-Ansatz** (`ops/skuld-cli/`, Python): Wrapper über GitHub-Actions-Workflows.
- **Teil-Doku**: `ops/README.md`, `ops/PROVISIONING.md`, `docs/deployment-contract.md`,
  `docs/deployment-operating-model.md`, `docs/developer-setup.md`.

### Verifizierte Probleme (die dieses Projekt behebt)

- **P1 — Zwei divergierende Härtungs-Wahrheiten:** `cloud-init.yml.tpl` (User `holu`+`deploy`,
  fail2ban, `MaxAuthTries 2`) und `provision-server.sh` (nur `deploy`, kein fail2ban, kein
  `MaxAuthTries`) erzeugen *unterschiedlich* gehärtete Server. → Muss zu **einer** Wahrheit werden.
- **P2 — Doku-Widersprüche:** `deployment-contract.md` nennt alte Server (`skuld-1/2`, Helsinki
  `204.168.128.55`), die nicht mehr aktiv sind bzw. nicht in `environments.yaml` stehen.
  `ops/setup-home-server.sh` ist deprecated, wird aber noch referenziert.
- **P3 — Prod/Test-Trennung unvollständig & unklar dokumentiert:** `home` ist mal „Staging", mal
  „Backup-Test". Rolle muss eindeutig sein.
- **P4 — Hoster-Beschaffung nur für Hetzner:** Auf Nicht-Hetzner-Hostern gibt es keinen
  dokumentierten, minimalen Weg.
- **P5 — Kein Off-Site-Backup:** Das einzige Backup liegt bei Hetzner (Server-Backup + ein
  Selbst-Backup *auf demselben Server*). Der Homeserver taugt nicht als Ziel (er IST das Testsystem).
  → **Bewusste Entscheidung des Users: Backup wird JETZT NICHT gebaut**, aber im Runbook als
  klar benannte offene Lücke + empfohlener Nachrüst-Weg dokumentiert.

---

## 3. Zielarchitektur

```
                        ┌─ Weg B (bequem, wenn Hoster cloud-init kann):
   Neuer Linux-Host ────┤     cloud-init  →  ruft NUR  provision-server.sh  auf
   (beliebiger Anbieter) └─ Weg A (universell, Fallback, IMMER möglich):
                              skuld provision <ip>  →  SSH-in  →  provision-server.sh
                                                   │
                                                   ▼
                          ┌─────────────────────────────────────────┐
                          │  EINE Härtungs-Wahrheit                  │
                          │  ops/provision-server.sh (idempotent)    │
                          │  Docker · UFW · SSH-Hardening · fail2ban │
                          │  deploy-User+Keys · Runner · Netzwerke   │
                          └─────────────────────────────────────────┘
                                                   │
                     identischer Server, egal über welchen Weg erzeugt
```

**Prinzip:** Es gibt genau **eine** Definition eines „SKULD-Servers" (`provision-server.sh`).
cloud-init wird zu einem dünnen Bootstrap, der dieses Skript beim Boot herunterlädt und ausführt —
statt die Härtung selbst zu duplizieren. Damit kann es keine divergierenden Server-Klassen mehr geben.

---

## 4. Bausteine

### Baustein 1 — Eine Härtungs-Wahrheit (`ops/provision-server.sh`, angeglichen)

**Was:** Das bestehende Skript wird zur *einzigen* Härtungs-Definition erhoben und angeglichen:

- **Übernahme aus cloud-init** (schließt P1): fail2ban (sshd-Jail) und SSH `MaxAuthTries 2`
  werden ergänzt, sodass SSH-in-provisionierte Server identisch zu cloud-init-Servern sind.
- **OS-Guard vorne** (für Ubuntu 26.04): Prüft die OS-Version. Bei nicht getesteter Version
  (z. B. 26.04) **klare Warnung + Abbruch-Option** statt halb-kaputtem Durchlauf. Docker-Repo-Zeile
  (`$(lsb_release -cs)`) wird so gebaut, dass sie bei neuen Codenames sauber fehlschlägt mit
  verständlicher Meldung, nicht stumm.
- **Idempotenz bleibt** (mehrfach ausführbar).
- **Rolle als Parameter:** `--role prod|test` (bzw. Env-Var) steuert Runner-Label und markiert den
  Server eindeutig.

**Bleibt unverändert:** Docker CE, UFW (22/80/443 + Tailscale/Docker-Subnetze), `daemon.json`
`iptables:false`, Docker-Netzwerke `web` + `postgres_setup_default`, App-Dir `/opt/skuld`,
GitHub-Runner, optional Cloudflare-Tunnel.

### Baustein 2 — Zwei Wege, ein Ergebnis

- **Weg A (universell / Fallback):** `skuld provision <ip> --role …` → SSH als root/sudo-User →
  pipet `provision-server.sh` auf den Host. Funktioniert auf *jedem* Linux mit SSH-Zugang.
- **Weg B (bequem):** `cloud-init.yml.tpl` wird zum dünnen Bootstrap reduziert: es lädt
  `provision-server.sh` (per `curl` aus dem Repo bzw. per `write_files` eingebettet) und ruft es auf.
  Für Hoster mit cloud-init/user-data-Support.

**Für den konkreten neuen Server:** Weg A (root-Zugang existiert bereits, kein Neu-Erstellen nötig).

### Baustein 3 — `skuld` Verwaltungs-Skript („alles per Skript")

Ein einziger Einstiegspunkt vom PC des Users. Baut auf dem vorhandenen `ops/skuld-cli/` auf
(erweitert es oder ergänzt einen schlanken Bash-Wrapper — die konkrete Form legt der Umsetzungsplan
fest). Kommandos:

| Kommando | Wirkung |
|---|---|
| `skuld provision <ip> --role prod\|test` | Server hochziehen (Weg A: SSH-in → provision-server.sh) |
| `skuld key add <name> <pubkey>` | SSH-Public-Key auf allen Servern der Rolle hinterlegen (idempotent) |
| `skuld key remove <name>` | Key entfernen |
| `skuld key list` | Autorisierte Keys je Server anzeigen |
| `skuld deploy prod\|test` | Deploy anstoßen (ruft bestehende GitHub-Actions-Workflows) |
| `skuld rollback prod` | Auf vorherige lauffähige Version zurück |
| `skuld status` | Was läuft wo (Server erreichbar? Container up? Version?) |

**SSH-Key-Verwaltung zentral:** Eine gepflegte Liste autorisierter Entwickler-Keys (heute teils
hardcodiert in `provision-server.conf`, teils via `add-developer-key.sh`) wird **eine** Quelle.
`skuld key …` wirkt konsistent über alle Server einer Rolle. Genauer Speicherort (Config-Datei vs.
`provision-server.conf`-Ablösung) → Umsetzungsplan.

### Baustein 4 — Prod/Test physisch getrennt

Umsetzung von Anforderung 2. **Physische Trennung** (nicht nur logisch):

- **Getrennte Config:** Prod und Test werden als eigenständige, klar rollenmarkierte Umgebungen
  geführt (Aufteilung/Kennzeichnung von `environments.yaml` — Detail im Umsetzungsplan; die
  bestehende `home`/`production`-Struktur bleibt Grundlage).
- **Getrennte Runner-Labels & Secrets-Trennung:** Ein Test-Deploy nutzt Test-Runner/Test-Ziel und
  kann Prod technisch nicht adressieren.
- **Bestehender Guard-Job bleibt** als zweite Sicherung (master → prod; alles andere kann prod nicht).
- **Der neue Server** startet als isolierte Test-Rolle; Umschaltung auf Prod-Rolle ist ein
  bewusster, dokumentierter Konfig-Schritt — niemals ein Seiteneffekt.

### Baustein 5 — Das felsenfeste Runbook (Desktop, NICHT GitHub)

Ein einziges, lückenloses Dokument (`SKULD-RUNBOOK.md` auf dem Desktop). Kein Vorwissen
vorausgesetzt, Copy-Paste-fähig, mit „was tun wenn Schritt X fehlschlägt". Inhalt:

1. **Phase 0 — Fuß in die Tür (manuell, einmalig, über die Web-Console des Anbieters):**
   SSH-Key auf dem PC erzeugen (falls keiner da), Public Key via Web-Console in root
   `authorized_keys`, `ssh root@<ip>` von außen testen. Erst danach kann das Skript ran.
2. **Phase 1 — Provisionieren:** `skuld provision <ip> --role test`.
3. **Phase 2 — Abgesicherter Zugangs-Übergang:** deploy-Key-Login testen → **erst dann** root-SSH +
   Passwort-Login deaktivieren. Web-Console des Anbieters bleibt als Notfall-Rückweg (funktioniert
   unabhängig von SSH → kein Aussperren möglich).
4. **Deploy & Betrieb:** `skuld deploy`, `skuld status`, Logs, Health.
5. **Rollback:** Schritt-für-Schritt.
6. **SSH-Key-Verwaltung:** Entwickler hinzufügen/entfernen, überall konsistent.
7. **Secrets:** vollständige Liste aller benötigten GitHub-Secrets + wofür, + Rotations-Hinweis.
8. **Katastrophenfall — „Hoster komplett weg → auf neuem Host neu aufbauen":** von null,
   inkl. Datenwiederherstellung. **Hier wird die Backup-Lücke (P5) ehrlich benannt:** aktuell kein
   Off-Site-Backup → Wiederherstellung nur aus dem, was der (verlorene) Hoster noch hat; empfohlener
   Nachrüst-Weg (verschlüsselter täglicher `pg_dump` in unabhängigen Object-Storage) wird beschrieben,
   aber nicht in diesem Projekt gebaut.
9. **Fehlerbehebung:** die häufigsten Stolpersteine (OS 26.04, Docker+UFW, Runner-Registrierung,
   Cert/Domain) mit konkreten Prüf- und Fix-Befehlen.

---

## 5. Explizit NICHT in Scope

- **Hoster-API-Provisioning (Stufe 2)** für Nicht-Hetzner-Anbieter (Server *erstellen* per API).
- **Off-Site-Backup-System** (P5) — auf ausdrücklichen Wunsch des Users vertagt; nur im Runbook
  als Lücke + Nachrüst-Anleitung dokumentiert.
- **Blue-Green / Zero-Downtime-Deploys**, Log-Aggregation, Monitoring-Ausbau.
- **Automatische Secret-Rotation** (nur manueller Rotations-Hinweis im Runbook).
- **Migration/Abschaltung des aktuellen Hetzner-Prod** — bleibt unangetastet; der neue Server wird
  parallel aufgebaut und getestet.

---

## 6. Sicherheits-Leitplanken (gelten für die Umsetzung)

- **Nichts Sicherheitskritisches ins öffentliche Repo:** keine echten Keys, IPs von Prod-Secrets,
  Passwörter, Recovery-Details. Das Runbook lebt auf dem Desktop.
- **Kein Anfassen von `master`** ohne ausdrückliche Freigabe. Arbeit auf `feature/portable-devops`.
- **Kein Push** ohne Freigabe. Kein Deploy gegen echtes Prod während der Entwicklung.
- **Aussperr-Schutz** ist im Runbook harte Regel: neuer Zugang nachweislich getestet, bevor alter
  deaktiviert wird; Web-Console als unabhängiger Rückweg.
- **Backup-Lücke wird nicht verschleiert**, sondern klar als Risiko benannt.

---

## 7. Definition of Done

- [ ] `provision-server.sh` ist die einzige Härtungs-Wahrheit (fail2ban + `MaxAuthTries 2` ergänzt),
      hat einen OS-Guard, und läuft auf dem neuen Server sauber durch (oder bricht klar ab).
- [ ] `cloud-init.yml.tpl` ist auf einen dünnen Bootstrap reduziert, der `provision-server.sh` aufruft.
- [ ] `skuld`-CLI kann: provision, key add/remove/list, deploy, rollback, status.
- [ ] Prod/Test sind physisch getrennt; ein Test-Deploy kann Prod technisch nicht erreichen.
- [ ] Doku-Widersprüche (P2) bereinigt: keine toten Server-Referenzen, keine deprecated-Verweise.
- [ ] `SKULD-RUNBOOK.md` liegt auf dem Desktop, deckt Phase 0–2, Deploy, Rollback, Keys, Secrets,
      Katastrophenfall und Fehlerbehebung lückenlos ab; Backup-Lücke benannt.
- [ ] **Live-Test bestanden:** SKULD läuft auf dem neuen Fremd-Server (Ubuntu 26.04), erreichbar
      über die echte Domain, als isolierte Test-Rolle — ohne das Hetzner-Prod zu berühren.
- [ ] Alles auf `feature/portable-devops`, nichts auf master, nichts gepusht ohne Freigabe.

---

## 8. Offene Punkte (bewusst offen gelassen)

1. **Backup (P5):** vertagt; im Runbook als Lücke dokumentiert. Nachrüsten ist ein eigenes Mini-Projekt.
2. **Ubuntu 26.04:** nicht getestete OS-Version; der Live-Test deckt auf, ob Docker-Repo/Pakete passen.
   Falls es doch 24.04 ist, entfällt das Risiko.
3. **`skuld`-CLI-Form:** Erweiterung des Python-`skuld-cli` vs. schlanker Bash-Wrapper — Entscheidung
   im Umsetzungsplan, nach Blick in den bestehenden CLI-Code.
4. **Genauer Speicherort der zentralen Key-Liste** — im Umsetzungsplan.
