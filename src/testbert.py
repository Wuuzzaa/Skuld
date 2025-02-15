import yfinance as yf
dat = yf.Ticker("MSFT")

print(dat.analyst_price_targets)