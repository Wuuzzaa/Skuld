CREATE TABLE IF NOT EXISTS "StockSymbolsMassive"
(
    symbol TEXT NOT NULL,
    exchange_mic TEXT,
    has_options BOOLEAN,
    PRIMARY KEY (symbol)
)