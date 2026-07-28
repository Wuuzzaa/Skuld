CREATE TABLE IF NOT EXISTS public."StockSP500ConstituentsHistorical"
(
    symbol text COLLATE pg_catalog."default",
    date_added date,
    date_removed date
)