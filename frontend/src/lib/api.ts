import axios from 'axios';

// In production: Traefik routes /api to skuld-api container (same domain)
// In dev: Next.js rewrites /api to localhost:8000
const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('skuld_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('skuld_token');
      localStorage.removeItem('skuld_user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;

// Auth
export async function login(username: string, password: string) {
  const { data } = await api.post('/auth/login', { username, password });
  return data;
}

export async function getMe() {
  const { data } = await api.get('/auth/me');
  return data;
}

// Spreads
export async function getExpirations() {
  const { data } = await api.get('/spreads/expirations');
  return data;
}

export async function getSpreads(params: Record<string, any>) {
  const { data } = await api.get('/spreads/', { params });
  return data;
}

export async function backtestSpread(body: {
  symbol: string;
  sell_option_osi: string;
  buy_option_osi: string;
  sell_strike: number;
  buy_strike: number;
  sell_last_option_price: number;
  buy_last_option_price: number;
  expiration_date: string;
  entry_date: string;
  compare_date: string;
  override?: Record<string, number> | null;
}) {
  const { data } = await api.post('/spreads/backtest', body);
  return data;
}

// Analyst Prices
export async function getAnalystPrices() {
  const { data } = await api.get('/analyst-prices/');
  return data;
}

// Iron Condors
export async function getIronCondors(params: Record<string, any>) {
  const { data } = await api.get('/iron-condors/', { params });
  return data;
}

// Married Puts
export async function getMarriedPuts(params: Record<string, any>) {
  const { data } = await api.get('/married-puts/', { params });
  return data;
}

export async function backtestMarriedPut(body: {
  symbol: string;
  live_stock_price: number;
  premium_option_price: number;
  number_of_stocks: number;
  option_osi?: string | null;
  strike_price: number;
  expiration_date: string;
  entry_date: string;
  compare_date: string;
}) {
  const { data } = await api.post('/married-puts/backtest', body);
  return data;
}

// Position Insurance
export async function getPositionInsurance(params: Record<string, any>) {
  const { data } = await api.get('/position-insurance/', { params });
  return data;
}

// Sector Rotation
export async function getSectorRotation(params: Record<string, any>) {
  const { data } = await api.get('/sector-rotation/', { params });
  return data;
}

// Expected Value
export async function simulateExpectedValue(body: any) {
  const { data } = await api.post('/expected-value/simulate', body);
  return data;
}

// Symbols
export async function listSymbols() {
  const { data } = await api.get('/symbols/');
  return data;
}

export async function getSymbolDetails(symbol: string) {
  const { data } = await api.get(`/symbols/${symbol}`);
  return data;
}

// Universe
export async function getUniverse() {
  const { data } = await api.get('/universe/');
  return data;
}

// Data Logs
export async function getDataLogs() {
  const { data } = await api.get('/data-logs/');
  return data;
}

// Multifactor Swingtrading
export async function getMultifactorSwingtrading(params: Record<string, any>) {
  const { data } = await api.get('/multifactor-swingtrading/', { params });
  return data;
}

// RSL Momentum Rotation
export async function getRslMomentum(params: Record<string, any>) {
  // Filter out null/undefined values so they don't get sent as "null" strings
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([_, v]) => v != null)
  );
  const { data } = await api.get('/rsl-momentum/', { params: cleanParams });
  return data;
}

export async function backtestRslMomentum(body: {
  start_date: string;
  end_date: string;
  start_budget?: number;
  flat_fee?: number;
  pct_fee?: number;
  top_n?: number;
  max_per_sector?: number;
  exit_percentile?: number;
  trading_frequency?: string;
  fractional_shares?: boolean;
  risk_free_rate?: number;
  tax_rate?: number;
}) {
  const { data } = await api.post('/rsl-momentum/backtest', body);
  return data;
}

// Watchlist
export async function getWatchlist() {
  const { data } = await api.get('/watchlist/');
  return data;
}

export async function addWatchlistItem(item: { symbol: string; person?: string; price_level_1?: number; price_level_2?: number; price_level_3?: number; notes?: string }) {
  const { data } = await api.post('/watchlist/', item);
  return data;
}

export async function updateWatchlistItem(id: number, item: Record<string, any>) {
  const { data } = await api.put(`/watchlist/${id}`, item);
  return data;
}

export async function deleteWatchlistItem(id: number) {
  const { data } = await api.delete(`/watchlist/${id}`);
  return data;
}

export async function refreshWatchlistPrices() {
  const { data } = await api.post('/watchlist/refresh-prices');
  return data;
}

// Covered Calls
export async function getCoveredCalls(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([_, v]) => v != null)
  );
  const { data } = await api.get('/covered-calls/', { params: cleanParams });
  return data;
}

// Covered Call Scanner (ITM, PowerOptions MorningUpdate style)
export async function getCoveredCallScanner(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([_, v]) => v != null)
  );
  const { data } = await api.get('/covered-call-scanner/', { params: cleanParams });
  return data;
}

// Dividend Screener (Zahltagstrategie)
export async function getDividendScreener(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([_, v]) => v != null && v !== '' && v !== 0)
  );
  const { data } = await api.get('/dividend-screener/', { params: cleanParams });
  return data;
}

export async function getDividendScreenerSectors() {
  const { data } = await api.get('/dividend-screener/sectors');
  return data;
}

// Earnings Put Scanner
export async function getEarningsPutCandidates(params: { days_ahead?: number }) {
  const { data } = await api.get('/earnings-put-scanner/', { params });
  return data;
}

export async function getEarningsPutOptions(params: { symbol: string; min_oi?: number }) {
  const { data } = await api.get('/earnings-put-scanner/puts', { params });
  return data;
}

// Dividend Portfolio Builder
export async function buildDividendPortfolio(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([_, v]) => v != null)
  );
  const { data } = await api.get('/dividend-portfolio/', { params: cleanParams });
  return data;
}

// Roll & Screen — Put Screener (Tab 1)
export async function getPutScreener(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([_, v]) => v != null)
  );
  const { data } = await api.get('/roll-and-screen/screener', { params: cleanParams });
  return data;
}

export async function getPutScreenerBreakdown(row: Record<string, any>, pe_max = 40) {
  const { data } = await api.post('/roll-and-screen/screener/breakdown', { row, pe_max });
  return data;
}

export async function getScreenerIvHistory(symbol: string) {
  const { data } = await api.get('/roll-and-screen/screener/iv-history', { params: { symbol } });
  return data;
}

export async function getScreenerSymbolPuts(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(Object.entries(params).filter(([_, v]) => v != null));
  const { data } = await api.get('/roll-and-screen/screener/symbol-puts', { params: cleanParams });
  return data;
}

export async function rankPutsAi(body: {
  puts: Record<string, any>[];
  max_candidates?: number;
  provider?: string;
  web_search?: boolean;
}) {
  const { data } = await api.post('/roll-and-screen/screener/ai-rank', body);
  return data;
}

// Roll & Screen — Put Roller (Tab 2)
export async function getRollerPuts(params: { symbol: string; entry_date: string; dte_min?: number; dte_max?: number }) {
  const { data } = await api.get('/roll-and-screen/roller/puts', { params });
  return data;
}

export async function getRollerPrice(params: { symbol: string; option_osi: string }) {
  const { data } = await api.get('/roll-and-screen/roller/price', { params });
  return data;
}

export async function getRollerCandidates(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(Object.entries(params).filter(([_, v]) => v != null));
  const { data } = await api.get('/roll-and-screen/roller/candidates', { params: cleanParams });
  return data;
}

// Roll & Screen — Spread Roller (Tab 3)
export async function getSpreadTypes() {
  const { data } = await api.get('/roll-and-screen/spread-roller/types');
  return data;
}

export async function getSpreadRollerOpen(params: { symbol: string; entry_date: string; expiration_date: string }) {
  const { data } = await api.get('/roll-and-screen/spread-roller/open', { params });
  return data;
}

export async function getSpreadRollerCandidates(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(Object.entries(params).filter(([_, v]) => v != null));
  const { data } = await api.get('/roll-and-screen/spread-roller/candidates', { params: cleanParams });
  return data;
}

// Roll & Screen — Put Browser (Tab 4)
export async function getBrowserPuts(params: Record<string, any>) {
  const cleanParams = Object.fromEntries(Object.entries(params).filter(([_, v]) => v != null));
  const { data } = await api.get('/roll-and-screen/browser/puts', { params: cleanParams });
  return data;
}

// Delta Portfolio — read-only market-data lookups (positions live in the browser)
export async function getOptionDelta(params: {
  symbol: string;
  strike: number;
  expiry: string;
  contract_type: 'call' | 'put';
}): Promise<{ delta: number | null }> {
  const { data } = await api.get('/delta-portfolio/option-delta', { params });
  return data;
}

export async function getStockPrices(symbols: string[]): Promise<Record<string, number | null>> {
  if (!symbols.length) return {};
  const { data } = await api.get('/delta-portfolio/stock-price', {
    params: { symbols: symbols.join(',') },
  });
  return data;
}

export async function getSectors(symbols: string[]): Promise<Record<string, string>> {
  if (!symbols.length) return {};
  const { data } = await api.get('/delta-portfolio/sectors', {
    params: { symbols: symbols.join(',') },
  });
  return data;
}

export async function getHedgeCandidates(symbol: string, stock_price: number) {
  const { data } = await api.get('/delta-portfolio/hedge-candidates', {
    params: { symbol, stock_price },
  });
  return data;
}
