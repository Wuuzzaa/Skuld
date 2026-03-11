# Deployment Architecture

## Purpose

This file documents how production deployment is structured and what each stack is responsible for.

## Core Principle

Production is split into separate Docker stacks. They are deployed independently.

That means:

- pushing app code does not rebuild PostgreSQL
- pushing Traefik changes does not rebuild the app
- pushing PostgreSQL changes does not rebuild the app
- monitoring is isolated as its own stack

## Active Target Selection

The active production target is controlled in [ops/deploy-target.env](ops/deploy-target.env).

Important field:

```env
DEPLOY_TARGET=skuld-1
```

Possible values:

- `skuld-1` = Falkenstein
- `skuld-2` = Helsinki

All production workflows read this value first and then select the matching GitHub Environment.

## Production Stacks

### 1. App Stack

Path:

- [docker-compose.yml](docker-compose.yml)

Deploy workflow:

- [.github/workflows/deploy.yml](.github/workflows/deploy.yml)

Containers:

- `skuld-frontend`
- `skuld-backend`
- `authelia`

Networks used:

- `web`
- `postgres_setup_default`

Responsibility:

- serves Streamlit frontend
- runs backend jobs and migrations
- uses Authelia for auth

Important:

- this stack expects PostgreSQL to already exist as `postgres_setup-db-1`
- this stack does not expose ports 80/443 itself

### 2. Traefik Stack

Path:

- [traefik/docker-compose.yml](traefik/docker-compose.yml)

Deploy workflow:

- [.github/workflows/deploy-traefik.yml](.github/workflows/deploy-traefik.yml)

Container:

- `traefik`

Network used:

- `web`

Responsibility:

- listens on ports 80 and 443
- terminates TLS
- routes `app.skuld-options.com` to the app
- routes `auth.skuld-options.com` to Authelia

### 3. PostgreSQL Stack

Path:

- [postgres_setup/docker-compose.yml](postgres_setup/docker-compose.yml)

Deploy workflow:

- [.github/workflows/deploy-postgres.yml](.github/workflows/deploy-postgres.yml)

Containers:

- `postgres_setup-db-1`
- `postgres_setup-pgadmin-1`

Network used:

- `postgres_setup_default`

Responsibility:

- hosts the production database
- exposes pgAdmin only on localhost

### 4. Monitoring Stack

Path:

- [monitoring/hetzner/docker-compose.yml](monitoring/hetzner/docker-compose.yml)

Deploy workflow:

- [.github/workflows/deploy-monitoring-hetzner.yml](.github/workflows/deploy-monitoring-hetzner.yml)

Responsibility:

- WireGuard
- node exporter

## Trigger Separation

### App Deploy

- triggered by app code changes
- ignores `traefik/**`
- ignores `postgres_setup/**`
- ignores `monitoring/**`

### Traefik Deploy

- triggered only by `traefik/**`
- or manually through its workflow

### PostgreSQL Deploy

- triggered only by `postgres_setup/**`
- or manually through its workflow

### Database Migration

- manual workflow only
- uses existing backup from source server
- copies backup to target
- restores into target PostgreSQL container

Workflow:

- [.github/workflows/migrate-database.yml](.github/workflows/migrate-database.yml)

## Required Order On A Fresh Server

For a brand new target server, the order must be:

1. server bootstrap
2. Traefik stack deploy
3. PostgreSQL stack deploy
4. database migration from source to target
5. app stack deploy
6. DNS switch for `app` and `auth`

## Common Failure Mode

If the app stack starts before PostgreSQL exists, you will see errors like:

```text
could not translate host name "postgres_setup-db-1" to address
```

Meaning:

- container name cannot be resolved on `postgres_setup_default`
- usually because the PostgreSQL stack has not been deployed yet

## Current Production Migration Plan

To move from `skuld-1` to `skuld-2` safely:

1. keep DNS on `skuld-1`
2. deploy Traefik to `skuld-2`
3. deploy PostgreSQL to `skuld-2`
4. migrate DB backup from `skuld-1` to `skuld-2`
5. deploy app to `skuld-2`
6. test app and auth on `skuld-2`
7. switch Cloudflare `app` and `auth` A records to `204.168.128.55`
8. rollback by pointing DNS back to `91.98.156.116` if needed