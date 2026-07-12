# SKULD Portable DevOps — Design-Spec

**Datum:** 2026-07-11 (aktualisiert 2026-07-12)
**Branch:** `feature/portable-devops`
**Status:** Entwurf zur Freigabe
**Autor:** Daniel (Interview) + Claude (Design)

---

## 1. Ziel & Motivation

SKULD ist heute faktisch an einen einzigen Hoster gebunden (Hetzner-Cloud-API im `provision-hetzner.ps1`,
hetzner-spezifisches `cloud-init.yml.tpl`, feste IP in `environments.yaml`).

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

**Erste Bewährungsprobe:** Ein bereits laufender Server bei einem *anderen* Anbieter wird als
künftiges Prod aufgesetzt — zunächst als isolierte Testumgebung, dann bei Bewährung Umschaltung
auf Prod. Das aktuelle Prod bleibt dabei zu jedem Zeitpunkt unangetastet.
OS des neuen Servers: **Ubuntu 24.04.4** (getestete LTS, kein OS-Risiko).

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
- **CLI-Ansatz** (`ops/skuld-cli/`, Python + Click): Wrapper über GitHub-Actions-Workflows.
- **Teil-Doku**: `ops/README.md`, `ops/PROVISIONING.md`, `docs/deployment-contract.md`,
  `docs/deployment-operating-model.md`, `docs/developer-setup.md`.

### Verifizierte Probleme (die dieses Projekt behebt)

- **P1 — Zwei divergierende Härtungs-Wahrheiten:** `cloud-init.yml.tpl` (User `holu`+`deploy`,
  fail2ban, `MaxAuthTries 2`) und `provision-server.sh` (nur `deploy`, kein fail2ban, kein
  `MaxAuthTries`) erzeugen *unterschiedlich* gehärtete Server. → Muss zu **einer** Wahrheit werden.
- **P2 — Doku-Widersprüche:** `deployment-contract.md` nennt alte Server (`skuld-1/2`, eine alte IP),
  die nicht mehr aktiv sind bzw. nicht in `environments.yaml` stehen.
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
   (beliebiger Anbieter) └─ Weg A (universell, IMMER möglich):
                              skuld setup  →  interaktiver Wizard auf dem PC
                                           →  SSH-in  →  provision-server.sh
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
- **OS-Guard vorne**: Prüft die OS-Version. Bei nicht getesteter Version
  (> 24.x) **klare Warnung + Abbruch-Option** statt halb-kaputtem Durchlauf.
- **Idempotenz bleibt** (mehrfach ausführbar).
- **Rolle als Env-Var `ROLE`** (`prod`/`test`) steuert Runner-Label und markiert den Server eindeutig.

**Bleibt unverändert:** Docker CE, UFW (22/80/443 + Tailscale/Docker-Subnetze), `daemon.json`
`iptables:false`, Docker-Netzwerke `web` + `postgres_setup_default`, App-Dir `/opt/skuld`,
GitHub-Runner, optional Cloudflare-Tunnel.

### Baustein 2 — Zwei Wege, ein Ergebnis

- **Weg A (universell / bevorzugt):** `skuld setup` Wizard auf dem PC fragt interaktiv durch und
  piped `provision-server.sh` per SSH auf den Host. Funktioniert auf *jedem* Linux mit SSH-Zugang.
- **Weg B (bequem):** `cloud-init.yml.tpl` wird zum dünnen Bootstrap reduziert: es lädt
  `provision-server.sh` und ruft es auf. Für Hoster mit cloud-init/user-data-Support.

**Für den konkreten neuen Server:** Weg A (root-Zugang existiert bereits, kein Neu-Erstellen nötig).

### Baustein 3 — `skuld setup` Wizard (interaktiv, auf dem PC)

**Motto:** „so viel Handarbeit wie möglich abnehmen, einfach, überschaubar."

Der Wizard läuft auf dem PC und fragt alles, was er braucht. Kein Auswendiglernen von Flags.

#### Wizard-Ablauf (6 Phasen)

```
Phase 0 (MANUELL, einmalig — vor dem Wizard, da neuer Server zunächst nur root-Web-UI hat):
  1. ssh-keygen auf dem PC (falls kein Key) — Wizard erklärt das
  2. Public Key via Web-Console des Anbieters in root/authorized_keys
  3. ssh root@<ip> von außen testen → muss klappen
  → ab hier hat der Wizard einen Weg rein.

skuld setup (auf dem PC, interaktiv):
  1. Server:    IP, SSH-User (default: root), welcher SSH-Key (default: ~/.ssh/id_ed25519)
  2. Umgebung:  Name (z.B. prod2, test1), Rolle (prod/test)
  3. Domain:    Web-Domain (z.B. app.<your-domain>.com)
                Auth-Domain: Wizard schlägt auth.<web-domain> vor, Enter oder eigene eingeben
  4. Härtung:   Linux absichern — ruft provision-server.sh, keine weiteren Fragen
                (Docker, UFW, SSH, MaxAuthTries=2, fail2ban, deploy-User, Runner)
  5. DB:        Wie wird die Datenbank befüllt?
                  (a) Leer starten (frisches Schema via Migrations)
                  (b) Aus lokalem pg_dump-File (User gibt Pfad an)
                  (c) Kopie von laufendem Prod/Test-Server (NICHT für diesen Schritt gebaut —
                      User hat dump lokal)
                Wenn (b): Wizard kopiert Dump per scp auf neuen Server und spielt ein.
                SICHERHEIT: Restore immer nur auf neuen/Ziel-Server. Bestätigungs-String.
  6. Fertig:    „Jetzt DNS auf <ip> zeigen lassen (Cloudflare), dann: skuld deploy <name>"
```

#### Wizard-Felder

| Feld | Default | Abgeleitet? |
|---|---|---|
| Umgebungs-Name | — | Nein, frei |
| Server-IP | — | Nein |
| SSH-User | `root` | Ja |
| SSH-Key | `~/.ssh/id_ed25519` | Ja, überschreibbar |
| Rolle | `test` | Ja, überschreibbar |
| Web-Domain | — | Nein |
| Auth-Domain | `auth.<web-domain>` | Ja, Wizard schlägt vor, Enter bestätigt |
| Authelia | `ja` | Ja, überschreibbar |
| DB-Befüllung | leer | Nein |
| Dump-Pfad (wenn b) | — | Nein |

Technische Traefik/Authelia-Details werden NICHT abgefragt, sondern von den obigen Feldern
abgeleitet und ins Runbook geschrieben. Daniel muss Authelia/Traefik nicht verstehen.

### Baustein 4 — Prod/Test physisch getrennt

- **Getrennte Config:** Prod und Test als eigenständige, klar rollenmarkierte Umgebungen in
  `environments.yaml`.
- **Getrennte Runner-Labels:** `skuld-prod` / `skuld-test`. Ein Test-Deploy kann Prod nicht adressieren.
- **Bestehender Guard-Job bleibt** als zweite Sicherung (master → prod; alles andere kann prod nicht).
- **Der neue Server** startet als isolierte Test-Rolle; Umschaltung auf Prod ist ein bewusster,
  dokumentierter Konfig-Schritt.

### Baustein 5 — Das felsenfeste Runbook (Desktop, NICHT GitHub)

Ein einziges, lückenloses Dokument (`SKULD-RUNBOOK.md` auf dem Desktop). Kein Vorwissen
vorausgesetzt, Copy-Paste-fähig, mit „was tun wenn Schritt X fehlschlägt". Inhalt:

1. Phase 0 — Fuß in die Tür (SSH-Key, Web-Console, Test)
2. Phase 1 — Wizard starten: `skuld setup`
3. Phase 2 — Abgesicherter Zugangs-Übergang (deploy-Key testen → root deaktivieren)
4. Deploy & Betrieb
5. Rollback
6. SSH-Key-Verwaltung
7. Secrets (vollständige Liste + Rotations-Hinweis)
8. Katastrophenfall — „Hoster weg" + **ehrlich benannte Backup-Lücke P5**
9. Fehlerbehebung (häufigste Stolpersteine)

---

## 5. Explizit NICHT in Scope

- **Hoster-API-Provisioning (Stufe 2)** für Nicht-Hetzner-Anbieter.
- **Off-Site-Backup-System (P5)** — vertagt; nur im Runbook als Lücke + Nachrüst-Anleitung.
- **Blue-Green / Zero-Downtime-Deploys**, Log-Aggregation, Monitoring-Ausbau.
- **Automatische Secret-Rotation.**
- **Migration/Abschaltung des aktuellen Hetzner-Prod.**
- **DB-Kopie direkt von Server zu Server** (kein Server-zu-Server-Tunnel): User hat Dump lokal.

---

## 6. Sicherheits-Leitplanken (gelten für die Umsetzung)

- **Nichts Sicherheitskritisches ins öffentliche Repo:** keine echten Keys, IPs, Passwörter.
  Das Runbook lebt auf dem Desktop.
- **Kein Anfassen von `master`** ohne ausdrückliche Freigabe. Arbeit auf `feature/portable-devops`.
- **Kein Push** ohne Freigabe. Kein Deploy gegen echtes Prod während der Entwicklung.
- **Aussperr-Schutz** ist im Runbook harte Regel: neuer Zugang nachweislich getestet, bevor alter
  deaktiviert wird; Web-Console als unabhängiger Rückweg.
- **DB-Restore nur auf Ziel-Server** (nie zurück auf Prod), mit Bestätigungs-String.
- **Backup-Lücke wird nicht verschleiert**, sondern klar als Risiko benannt.

---

## 7. Definition of Done

- [ ] `provision-server.sh` ist die einzige Härtungs-Wahrheit (fail2ban + `MaxAuthTries 2` ergänzt),
      hat einen OS-Guard, und läuft auf dem neuen Server sauber durch.
- [ ] `cloud-init.yml.tpl` ist auf einen dünnen Bootstrap reduziert.
- [ ] `skuld setup` Wizard läuft: fragt durch, härtet Server, befüllt DB aus lokalem Dump, schreibt
      `environments.yaml`-Eintrag.
- [ ] Prod/Test sind physisch getrennt; ein Test-Deploy kann Prod technisch nicht erreichen.
- [ ] Doku-Widersprüche (P2) bereinigt.
- [ ] `SKULD-RUNBOOK.md` liegt auf dem Desktop, Backup-Lücke benannt.
- **Live-Test bestanden:** SKULD läuft auf dem neuen Server (Ubuntu 24.04), erreichbar über die
      echte Domain, als isolierte Test-Rolle — ohne das bestehende Prod zu berühren.
- [ ] Alles auf `feature/portable-devops`, nichts auf master, nichts gepusht ohne Freigabe.

---

## 8. Offene Punkte

1. **Backup (P5):** vertagt; im Runbook als Lücke dokumentiert.
2. **`skuld`-CLI-Form:** Erweiterung des Python-`skuld-cli` (Click) — Wizard als neues `setup`-Kommando.
3. **Deploy Key:** liegt als GitHub Secret; Wizard überträgt ihn auf den neuen Server,
   kein neuer GitHub-UI-Schritt nötig.
