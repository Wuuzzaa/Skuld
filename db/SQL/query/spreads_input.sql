SELECT
    symbol,
    expiration_date,
    contract_type as "option-type",
    strike_price as strike,
    --ask,
    --bid,
    --(ask + bid) / 2 as mid,
    day_close as mid, -- todo nicht mid sondern last price
    greeks_delta as delta,
    implied_volatility as iv,
    greeks_theta as theta,
    close, -- todo datenquelle korrekt für AKTIEN-Schlusskurs?
    earnings_date,
    days_to_expiration,
    days_to_ernings, -- todo typo earnings "a" fehlt
    --spread, -- todo gibt es nicht mehr von yahoo optionen. nicht benötigt, da kein ask und bid bei masssive vorhanden.
    --spread_ptc, -- todo gibt es nicht mehr von yahoo optionen. nicht benötigt, da kein ask und bid bei masssive vorhanden.
    --iv_rank, -- todo gibt es nicht mehr von barchart optionen. muss aus eigener historie kommen.
    --iv_percentile, -- todo gibt es nicht mehr von barchart optionen. muss aus eigener historie kommen.
    open_interest as option_open_interest,
    expected_move -- todo nutzt preis von technicalIndicators. Datenquelle prüfen. Evtl. Umstieg auf yahoo Aktienpreis
FROM
    OptionDataMerged
WHERE
    expiration_date =:expiration_date
    AND contract_type =:option_type;
