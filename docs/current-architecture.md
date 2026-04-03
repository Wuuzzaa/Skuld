# Current Architecture

Dieses Diagramm beschreibt den aktuellen Ist-Zustand der Skuld-Landschaft auf Basis der Compose-Dateien und Deploy-Workflows im Repository.

```mermaid
flowchart LR
    Users[Users]
    Devs[Developers]
    GH[GitHub Repository]
    GHA[GitHub Actions]

    Users --> DNS[Public Domains]
    Devs --> GH
    GH --> GHA

    subgraph PROD[Hetzner Production - SKULD-2 / Helsinki]
        direction TB

        subgraph PROD_APP[/opt/skuld app stack/]
            direction TB
            TRAEFIK[Traefik]
            AUTHELIA[Authelia]
            FRONTEND[skuld-frontend\nStreamlit UI]
            BACKEND[skuld-backend\nJobs / Scraper / Cron]
        end

        subgraph PROD_DB[/opt/postgres_setup db stack/]
            direction TB
            PG[(postgres_setup-db-1\nPostgreSQL)]
            PGADMIN[postgres_setup-pgadmin-1\npgAdmin]
        end

        subgraph PROD_MON[monitoring stack on host]
            direction TB
            WG[monitoring-wireguard-server]
            NODEX[monitoring-node-exporter]
        end

        TRAEFIK --> AUTHELIA
        TRAEFIK --> FRONTEND
        FRONTEND --> PG
        BACKEND --> PG
        PGADMIN --> PG
        NODEX --> WG
    end

    subgraph DEV[Hetzner Dev - Skuld-dev / Falkenstein]
        direction TB
        DEVAPP[/opt/skuld via deploy-dev.yml/]
        DEVDB[(External PostgreSQL target\nvia POSTGRES_HOST)]
        DEVAPP --> DEVDB
    end

    subgraph STAGE[Home Server Staging / Testsystem]
        direction TB

        subgraph STAGE_STACK[docker-compose.yml + docker-compose.testing.yml]
            direction TB
            STRAEFIK[traefik_staging]
            SAUTHELIA[authelia]
            SFRONTEND[skuld-frontend]
            SBACKEND[skuld-backend]
            SPG[(skuld_staging_db\nPostgreSQL)]
            SPGA[skuld_staging_pgadmin]
        end

        STRAEFIK --> SAUTHELIA
        STRAEFIK --> SFRONTEND
        SFRONTEND --> SPG
        SBACKEND --> SPG
        SPGA --> SPG
    end

    subgraph MONITORING[Separate Monitoring Compose]
        direction TB
        MHETZNER[monitoring/hetzner]
        MHOME[monitoring/home]
    end

    DNS --> TRAEFIK
    DNS --> STRAEFIK

    GHA -->|push master| PROD_APP
    GHA -->|workflow_dispatch deploy-dev.yml| DEVAPP
    GHA -->|push testsystem| STAGE_STACK
    GHA -->|monitoring workflows| MHETZNER
    GHA -->|monitoring workflows| MHOME

    BACKEND -. manual jobs / restore-helsinki-db / trigger-jobs .-> PG
    GHA -. db restore and remote jobs .-> PROD_DB
```

## Notes

- Produktion trennt App-Stack und DB-Stack logisch in zwei Compose-Projekte auf demselben Host.
- Die Produktions-App verbindet sich nicht mit einem lokalen DB-Service aus `docker-compose.yml`, sondern mit dem externen Container `postgres_setup-db-1` ueber das externe Netzwerk `postgres_setup_default`.
- Das Testsystem ist deutlich selbststaendiger und enthaelt einen eigenen PostgreSQL-Container im Staging-Compose-Override.
- Der Dev-Deploy auf `Skuld-dev` wird ueber `.github/workflows/deploy-dev.yml` ausgerollt und nutzt einen extern konfigurierten PostgreSQL-Endpunkt per Environment-Variablen.
- Monitoring laeuft separat und ist nicht Teil des normalen Produktions-App-Deployments.
- Der juengste Produktionsvorfall betraf den separaten Produktions-DB-Container `postgres_setup-db-1` und dessen Shared-Memory-Konfiguration, nicht den App-Stack selbst.