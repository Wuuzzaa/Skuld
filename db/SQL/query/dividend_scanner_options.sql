SELECT 
	strike_price, 
	expiration_date, 
	greeks_delta, 
	implied_volatility,
	open_interest,
	day_volume,
	day_last_updated
FROM "OptionData"
WHERE symbol = :symbol 
  AND contract_type = 'put'
  AND expiration_date BETWEEN CURRENT_DATE + INTERVAL '30 days' AND CURRENT_DATE + INTERVAL '60 days'
  AND greeks_delta BETWEEN -0.40 AND -0.20
ORDER BY ABS(greeks_delta + 0.30) ASC
LIMIT 5