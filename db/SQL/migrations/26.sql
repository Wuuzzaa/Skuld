CREATE TABLE IF NOT EXISTS "StockAssetProfilesYahoo"
(
    symbol TEXT PRIMARY KEY,
    name TEXT,
    industry TEXT,
    sector TEXT,
    country TEXT,
    long_business_summary TEXT
);
CREATE TABLE IF NOT EXISTS "StockSymbolsMassive"
(
    symbol TEXT NOT NULL,
    exchange_mic TEXT,
    has_options BOOLEAN,
    PRIMARY KEY (symbol)
);

ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "ReceiptsfromGovernmentGrants" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "DividendsPaidDirect" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "DividendsReceivedDirect" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "Summary_openInterest" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "Summary_ytdReturn" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "KeyStats_lastCapGain" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "KeyStats_morningStarRiskRating" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "KeyStats_morningStarOverallRating" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "KeyStats_annualReportExpenseRatio" double precision;
ALTER TABLE "FundamentalDataYahoo" ADD COLUMN "KeyStats_annualHoldingsTurnover" double precision;