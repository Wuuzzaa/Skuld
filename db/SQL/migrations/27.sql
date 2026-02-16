DROP TABLE IF EXISTS "DividendDataYahoo";
CREATE TABLE IF NOT EXISTS "DividendDataYahoo"
(
    symbol text,
    years_of_growth smallint,
    classification text,
    PRIMARY KEY (symbol)
);