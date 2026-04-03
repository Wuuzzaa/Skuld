graph TB
    %% 1. Source & CI Layer
    subgraph VCS [Source Control & CI Layer]
        direction LR
        GH[GitHub Repository] --> CI[CI Pipeline]
        CI --> Reg[Container Registry]
    end

    %% 2. Control & Secrets
    subgraph Control [Deployment & Secrets]
        K[Kamal Control Host]
        S[Secret Manager]
    end

    %% 3. Development Environment
    subgraph Dev_Env [Development Environment]
        direction TB
        subgraph Dev_Edge [Edge]
            D_T[Traefik]
        end
        subgraph Dev_App [App Host]
            D_Web[app-web]
            D_Work[app-worker]
        end
        subgraph Dev_Data [Data Host]
            D_PG[(PostgreSQL)]
            D_Red[(Redis)]
        end
        D_T --> D_Web
        D_Web --> D_PG & D_Red
    end

    %% 4. Production Environment
    subgraph Prod_Env [Production Environment]
        direction TB
        subgraph P_Edge [Edge Layer]
            T1[Traefik Host 1]
            T2[Traefik Host 2]
        end
        subgraph P_App [App Layer]
            W1[Prod App 1: web/worker]
            W2[Prod App 2: web/worker]
        end
        subgraph P_Data [Data Layer]
            PG_P[(PostgreSQL Primary)]
            PG_R[(PostgreSQL Replica)]
        end
        T1 & T2 --> W1 & W2
        W1 & W2 --> PG_P
        PG_P -.->|replication| PG_R
    end

    %% 5. Shared Operations (Monitoring & Admin)
    subgraph Ops [Shared Operations Layer]
        M[Monitoring: Prometheus/Grafana]
        B[Backup Runner]
        VPN[VPN / Tailscale Admin]
    end

    %% Globale Verbindungen (Flows)
    Reg -.-> K
    S -.-> K
    K -- "kamal deploy" --> Dev_Env
    K -- "kamal deploy" --> Prod_Env
    
    Ops -.->|monitoring / backup| Dev_Env
    Ops -.->|monitoring / backup| Prod_Env

    %% Styling für die Übersicht
    style VCS fill:#f5f5f5,stroke:#666
    style Control fill:#fff2cc,stroke:#d6b656
    style Dev_Env fill:#e1d5e7,stroke:#9673a6
    style Prod_Env fill:#d5e8d4,stroke:#82b366
    style Ops fill:#f8cecc,stroke:#b85450
