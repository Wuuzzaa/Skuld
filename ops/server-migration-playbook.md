# Server Migration Playbook

## Goal

This playbook describes the repeatable process for moving the full production system from one Linux server to another with low risk and easy rollback.

It is intentionally independent from one specific migration.

## Principle

Never move everything at once.

Always migrate in layers:

1. target server base setup
2. reverse proxy
3. database stack
4. data migration
5. application stack
6. DNS cutover

## Required Inputs

Before a migration starts, define these explicitly:

- source server name and IP
- target server name and IP
- active domains that must move
- SSH access for both servers
- GitHub Environment / secret mapping
- rollback target

## Stable Stack Order

### Layer 1: Base Server

- OS updates
- deploy user
- SSH hardening
- firewall
- fail2ban
- Docker
- required external Docker networks

### Layer 2: Reverse Proxy

- deploy Traefik
- verify ports 80 and 443 are reachable
- verify ACME / Let's Encrypt works

### Layer 3: Database

- deploy PostgreSQL stack
- verify DB container health
- verify app network can resolve the DB hostname

### Layer 4: Data

- prefer latest validated backup over ad hoc live dump
- transfer backup to target
- restore on target
- keep pre-restore backup on target

### Layer 5: Application

- deploy app stack
- verify frontend
- verify auth
- verify backend jobs
- verify migrations are idempotent

### Layer 6: DNS Cutover

- switch only the required hostnames
- keep unrelated records untouched
- verify through Cloudflare and directly on the origin

## Rollback Rule

Rollback must always be possible by DNS first.

That means:

- source server remains intact until target is verified
- cutover affects only the required hostnames
- target deployment must not destroy source data

## Mandatory Checks Before DNS Switch

- Traefik healthy
- app container healthy
- backend container healthy
- database reachable from app container
- auth route reachable
- one representative DB-backed page loads
- latest backup exists on both source and target

## Mandatory Checks After DNS Switch

- Cloudflare no longer returns 521
- app domain loads successfully
- auth domain loads successfully
- no migration restart loop
- no Telegram error spam

## Failure Patterns To Expect

### Error: host name cannot be translated

Meaning:

- target DB stack is not running
- or app container is not on the DB network
- or target hostname/container alias differs from expected runtime config

### Error: duplicate table / duplicate column during migrations

Meaning:

- a fresh or partially initialized database is being migrated twice
- migrations must be idempotent enough to tolerate existing objects

### Error: Cloudflare 521

Meaning:

- reverse proxy is not listening on 80/443
- or origin firewall is blocking traffic
- or DNS was switched before Traefik was up

## Recommended Branch Strategy

Keep server-migration work off `master` until the sequence is proven.

Recommended pattern:

1. create a dedicated migration branch
2. keep infrastructure changes isolated there
3. validate on target server
4. merge to master only after the target path is proven

## Recommended Operational Sequence For Future Migrations

1. create migration branch
2. introduce target selection/config abstraction
3. add or update isolated deploy workflows per stack
4. deploy proxy stack on target
5. deploy DB stack on target
6. restore latest backup on target
7. deploy app stack on target
8. validate end-to-end
9. switch DNS
10. keep source live until confidence window is over
