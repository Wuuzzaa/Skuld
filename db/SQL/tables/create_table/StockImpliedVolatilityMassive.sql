CREATE TABLE
    IF NOT EXISTS "StockImpliedVolatilityMassive" (
        symbol text,
        iv double precision,
        iv_low double precision,
        iv_high double precision,
        iv_rank double precision,
        iv_percentile double precision,
        PRIMARY KEY (symbol)
    );