import axios from "axios";

// Always use a relative base URL so requests go through the Next.js rewrite
// proxy (/api/* → backend). This avoids CORS entirely — the proxy runs
// server-side and forwards to the backend container.
export const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      const refresh = typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
      if (refresh) {
        try {
          const { data } = await axios.post("/api/v1/auth/refresh", { refresh_token: refresh });
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          err.config.headers.Authorization = `Bearer ${data.access_token}`;
          return api.request(err.config);
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(err);
  }
);

export const authApi = {
  login: (email: string, password: string) =>
    api.post("/auth/login", { email, password }),
  register: (email: string, password: string) =>
    api.post("/auth/register", { email, password }),
};

export const marketApi = {
  getCandles: (symbol: string, timeframe: string, limit = 200) =>
    api.get("/market-data/candles", { params: { symbol, timeframe, limit } }),
  getCandlesByRange: (symbol: string, range: string) =>
    api.get("/market-data/candles", { params: { symbol, range } }),
  getTicks: (symbol: string, limit = 20) =>
    api.get("/market-data/ticks", { params: { symbol, limit } }),
  getPrice: (symbol: string) =>
    api.get("/market-data/price", { params: { symbol } }),
};

export const indicatorApi = {
  getSnapshot: (symbol: string, timeframe: string, range?: string) =>
    api.get("/indicators/snapshot", { params: { symbol, timeframe, ...(range && { range }) } }),
  getLatest: (symbol: string, timeframe: string, limit = 50, range?: string) =>
    api.get("/indicators/latest", { params: { symbol, timeframe, limit, ...(range && { range }) } }),
};

export const patternApi = {
  getAll: (symbol: string, timeframe: string) =>
    api.get("/patterns/all", { params: { symbol, timeframe } }),
  getCandlestick: (symbol: string, timeframe: string) =>
    api.get("/patterns/candlestick", { params: { symbol, timeframe } }),
  getChart: (symbol: string, timeframe: string) =>
    api.get("/patterns/chart", { params: { symbol, timeframe } }),
};

export const smcApi = {
  analyze: (symbol: string, timeframe: string, range?: string) =>
    api.get("/smc/analyze", { params: { symbol, timeframe, ...(range && { range }) } }),
  score: (symbol: string, timeframe: string, range?: string) =>
    api.get("/smc/score", { params: { symbol, timeframe, ...(range && { range }) } }),
};

export const signalApi = {
  generate: (symbol: string, timeframe: string, account_balance = 10000) =>
    api.post("/signals/generate", { symbol, timeframe, account_balance }),
  list: (symbol?: string, timeframe?: string, limit = 50) =>
    api.get("/signals", { params: { symbol, timeframe, limit } }),
  get: (id: number) => api.get(`/signals/${id}`),
};

export const newsApi = {
  list: (limit = 50) => api.get("/news", { params: { limit } }),
  sentiment: (hours = 24) => api.get("/news/sentiment", { params: { hours } }),
};

export const econApi = {
  list: (limit = 50) => api.get("/economic-calendar", { params: { limit } }),
  aggregateScore: (hours = 48) =>
    api.get("/economic-calendar/aggregate-score", { params: { hours } }),
};

export const mlApi = {
  predict: (symbol: string, timeframe: string, range?: string) =>
    api.post("/ml/predict", { symbol, timeframe, ...(range && { range }) }),
  train: (symbol: string, timeframe: string, range?: string) =>
    api.post("/ml/train", { symbol, timeframe, ...(range && { range }) }),
};

export const forecastApi = {
  get: (symbol: string, timeframe: string) =>
    api.get("/forecast", { params: { symbol, timeframe } }),
};

export const aiApi = {
  analyzeSignal: (signal_id: number) =>
    api.post("/ai/analyze-signal", { signal_id }),
  dailyBias: (candle_summary = "", news_summary = "", econ_summary = "") =>
    api.post("/ai/daily-bias", { candle_summary, news_summary, econ_summary }),
};

export const backtestApi = {
  run: (symbol: string, timeframe: string, window = 100) =>
    api.post("/backtesting/run", { symbol, timeframe, window }),
  list: () => api.get("/backtesting"),
};

export const adminApi = {
  stats: () => api.get("/admin/stats"),
  users: () => api.get("/admin/users"),
  logs: (level?: string) => api.get("/admin/logs", { params: { level } }),
};
