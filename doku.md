graph TB
    %% Definition der externen Layer
    subgraph VCS [Source & CI Layer]
        GH[GitHub Repo] --> CI[CI Pipeline]
        CI --> Reg[Container Registry]
    end

    subgraph Control [Deployment Control]
        K[Kamal Control]
        S[Secret Manager]
    end

    %% Environments als logische Gruppierung
    subgraph Dev_Env [Development Environment]
        direction TB
        subgraph Dev_Host [Dev App Host]
            D_Web[app-web]
            D_Redis[Redis]
        end
        subgraph Dev_DB [Dev Data Host]
            D_PG[(PostgreSQL)]
        end
    end

    subgraph Prod_Env [Production Environment]
        direction TB
        subgraph P_Edge [Prod Edge Hosts]
            T1[Traefik 1]
            T2[Traefik 2]
        end
        subgraph P_App1 [Prod App Host 1]
            W1[app-web]
            WR1[app-worker]
        end
        subgraph P_App2 [Prod App Host 2]
            W2[app-web]
            WR2[app-worker]
        end
        subgraph P_Data [Prod Data Layer]
            PG_P[(PostgreSQL Primary)]
            PG_R[(PostgreSQL Replica)]
        end
    end

    %% Verbindungen (Flows)
    Reg -.-> K
    K -- deploys to --> Dev_Env
    K -- deploys to --> Prod_Env
    S -- provides secrets --> K

    T1 --> W1
    T2 --> W2
    W1 & W2 --> PG_P
    PG_P -.-> PG_R
