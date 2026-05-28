UPDATE "OptionDataMassiveHistoryDaily" AS target
SET symbol = source.symbol
FROM "OptionDataMassiveMasterData" AS source
WHERE target.option_osi = source.option_osi
  AND target.symbol IS NULL;
UPDATE "OptionDataMassiveHistoryWeekly" AS target
SET symbol = source.symbol
FROM "OptionDataMassiveMasterData" AS source
WHERE target.option_osi = source.option_osi
  AND target.symbol IS NULL;
UPDATE "OptionDataMassiveHistoryMonthly" AS target
SET symbol = source.symbol
FROM "OptionDataMassiveMasterData" AS source
WHERE target.option_osi = source.option_osi
  AND target.symbol IS NULL;
ALTER TABLE public."OptionDataMassiveHistoryDaily"
    DROP CONSTRAINT "OptionDataMassiveHistoryDaily_pkey",
    ALTER COLUMN symbol SET NOT NULL,
    ADD CONSTRAINT "OptionDataMassiveHistoryDaily_pkey" PRIMARY KEY (snapshot_date, option_osi, symbol);
ALTER TABLE public."OptionDataMassiveHistoryWeekly"
    DROP CONSTRAINT "OptionDataMassiveHistoryWeekly_pkey1",
    ALTER COLUMN symbol SET NOT NULL,
    ADD CONSTRAINT "OptionDataMassiveHistoryWeekly_pkey" PRIMARY KEY (isoyear, week, option_osi, symbol);
ALTER TABLE public."OptionDataMassiveHistoryMonthly"
    DROP CONSTRAINT "OptionDataMassiveHistoryMonthly_pkey",
    ALTER COLUMN symbol SET NOT NULL,
    ADD CONSTRAINT "OptionDataMassiveHistoryMonthly_pkey" PRIMARY KEY (year, month, option_osi, symbol);
ALTER TABLE public."OptionDataMassiveMasterData"
    DROP CONSTRAINT "OptionDataMassiveMasterData_pkey",
    ALTER COLUMN symbol SET NOT NULL,
    ADD CONSTRAINT "OptionDataMassiveMasterData_pkey" PRIMARY KEY (option_osi, symbol);