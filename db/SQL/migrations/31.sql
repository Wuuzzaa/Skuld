DELETE FROM "StockSymbolsMassive";
ALTER TABLE "StockSymbolsMassive" ADD COLUMN IF NOT EXISTS "type" TEXT;