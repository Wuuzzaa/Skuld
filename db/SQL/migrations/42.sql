-- Precomputed pairwise correlations (filled by the correlation_precompute job).
-- Stores one row per ordered (base_symbol, peer_symbol) pair per (lookback, method),
-- so the API can serve "symbol vs all" instantly instead of computing live.
CREATE TABLE IF NOT EXISTS public."CorrelationPrecomputed"
(
    base_symbol   text COLLATE pg_catalog."default" NOT NULL,
    peer_symbol   text COLLATE pg_catalog."default" NOT NULL,
    lookback_days integer NOT NULL,
    method        text COLLATE pg_catalog."default" NOT NULL,
    correlation   double precision,
    computed_at   timestamp without time zone DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT "CorrelationPrecomputed_pkey"
        PRIMARY KEY (base_symbol, peer_symbol, lookback_days, method)
);

CREATE INDEX IF NOT EXISTS idx_correlation_precomputed_base
    ON public."CorrelationPrecomputed" (base_symbol, lookback_days, method);
