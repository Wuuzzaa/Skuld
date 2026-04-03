# Target Architecture

Dieses Diagramm beschreibt eine moegliche Zielarchitektur fuer Skuld mit staerkerer Logikkapselung, sauberem API-Schnitt, klar getrennten Deployments und weniger impliziter Betriebslogik.

```mermaid
flowchart LR
    Users[Users]
    Admins[Admins and Operators]
    Devs[Developers]
    GH[GitHub Repository]
    CI[CI Pipeline]
    REG[Container Registry]
    KAMAL[Kamal Deployment Control]
    SECRETS[Secret Manager]

    Users --> EDGE
    Admins --> ADMINUI
    Devs --> GH
    GH --> CI
    CI --> REG
    Admins --> KAMAL
    KAMAL --> REG
    KAMAL --> SECRETS

    subgraph EDGE_ZONE["Public Edge Zone"]
        direction TB
        EDGE[Ingress and API Gateway]
        AUTH[Authentication and User Management]
    end

    subgraph APP_ZONE["Application Zone"]
        direction TB

        subgraph FRONTEND_STACK["Frontend Layer"]
            direction TB
            WEB["Web Frontend<br/>SPA or SSR App"]
            ADMINUI["Admin Frontend<br/>Operations and User UI"]
        end

        subgraph API_STACK["Backend API Layer"]
            direction TB
            API["Python REST API<br/>FastAPI or Django API"]
            BFF["API Composition Layer<br/>Validation and Authorization"]
        end

        subgraph DOMAIN_STACK["Domain Logic Layer"]
            direction TB
            OPTIONS["Options Service"]
            PRICING["Pricing and Analytics Service"]
            MARKETDATA["Market Data Service"]
            USERCFG["User and Portfolio Service"]
            REPORTING["Reporting and Export Service"]
        end

        subgraph JOB_STACK["Async and Batch Layer"]
            direction TB
            WORKER["Worker Service"]
            SCHEDULER["Scheduler Service"]
            IMPORTER["Data Import Pipelines"]
        end
    end

    subgraph DATA_ZONE["Private Data Zone"]
        direction TB
        POSTGRES[("PostgreSQL Primary")]
        REDIS[("Redis")]
        OBJ[("Object Storage<br/>Backups, exports, artifacts")]
        DW[("Optional Analytics Store<br/>Materialized views or ClickHouse")]
    end

    subgraph OPS_ZONE["Operations Zone"]
        direction TB
        MON["Monitoring and Alerting"]
        LOGS["Central Logs"]
        AUDIT["Audit and Admin Events"]
        BACKUPS["Backup and Restore Jobs"]
    end

    EDGE --> AUTH
    EDGE --> WEB
    EDGE --> ADMINUI
    EDGE --> API

    WEB --> API
    ADMINUI --> API
    API --> BFF
    BFF --> OPTIONS
    BFF --> PRICING
    BFF --> MARKETDATA
    BFF --> USERCFG
    BFF --> REPORTING

    OPTIONS --> POSTGRES
    PRICING --> POSTGRES
    MARKETDATA --> POSTGRES
    USERCFG --> POSTGRES
    REPORTING --> POSTGRES

    API --> REDIS
    WORKER --> REDIS
    SCHEDULER --> REDIS

    WORKER --> POSTGRES
    SCHEDULER --> POSTGRES
    IMPORTER --> POSTGRES
    IMPORTER --> OBJ
    REPORTING --> OBJ
    PRICING -. optional heavy analytics .-> DW
    MARKETDATA -. optional heavy analytics .-> DW

    MON --> API
    MON --> WORKER
    MON --> POSTGRES
    LOGS --> API
    LOGS --> WORKER
    AUDIT --> POSTGRES
    BACKUPS --> POSTGRES
    BACKUPS --> OBJ

    KAMAL --> EDGE
    KAMAL --> WEB
    KAMAL --> ADMINUI
    KAMAL --> API
    KAMAL --> WORKER
    KAMAL --> SCHEDULER
    KAMAL --> IMPORTER
```

## Notes

- Das Frontend wird zu einer eigenstaendigen Web-Anwendung statt direkt an fachlicher Python-UI-Logik zu haengen.
- Das Python-Backend wird als REST-API mit klaren Endpunkten, Auth, Validierung und Rollenmodell gekapselt.
- Fachlogik wird in eigene Services oder Module getrennt, statt in Seiten, Skripten und Deploy-Flows verteilt zu sein.
- Batch- und Import-Logik wird in Worker- und Scheduler-Prozesse verschoben und nicht mehr implizit ueber das Web-Frontend ausgelost.
- Deployment wird zentral ueber Kamal oder ein aehnlich explizites Target-Modell gesteuert, statt ueber viele versteckte Sonder-Workflows.
- Secrets und Laufzeitkonfiguration werden aus dem Repo herausgezogen und zentral verwaltet.
- Backups, Restore, Reporting und Export laufen ueber klar benannte Ops-Komponenten statt ueber ad-hoc Skripte im App-Stack.
- Fuer Userverwaltung ist ein eigener Auth-Baustein vorgesehen, entweder ueber einen externen IdP oder einen dedizierten Auth-Service.
- Schwere Analytics-Operationen koennen spaeter von der transaktionalen Hauptdatenbank getrennt werden.
- Die Zielarchitektur reduziert implizite Kopier- und Deploy-Pfade und macht klar, welche Komponente welche Verantwortung traegt.