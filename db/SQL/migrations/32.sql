ALTER TABLE public."OptionDataMassive"
    DROP CONSTRAINT "OptionDataMassive_pkey",
    ALTER COLUMN symbol SET NOT NULL,
    ADD CONSTRAINT "OptionDataMassive_pkey" PRIMARY KEY (option_osi, symbol);