//+------------------------------------------------------------------+
//|  GoldAI_CostFeed.mq4                                              |
//|  Sends the broker's REAL spread and swap to the Gold AI backend.  |
//|  Read-only: never opens, modifies or closes orders.               |
//|                                                                   |
//|  Setup:                                                           |
//|   1. Tools → Options → Expert Advisors → "Allow WebRequest for    |
//|      listed URL" → add  http://127.0.0.1:8001                     |
//|   2. Attach to ANY chart, set FeedToken = BROKER_FEED_TOKEN       |
//|      from gold_ai/.env, Symbols = broker names (e.g. GOLD=XAUUSD) |
//|   3. Keep "AutoTrading" ON (EAs only run when it is enabled).     |
//+------------------------------------------------------------------+
#property strict
#property copyright "Gold AI"
#property description "Per-minute spread / swap feed for broker cost calibration (no trading)."

input string BackendURL = "http://127.0.0.1:8001/api/v1/broker/quotes";
input string FeedToken  = "";
input string Symbols    = "XAUUSD";   // comma-separated; BROKERNAME=NORMALISED, e.g. "GOLD=XAUUSD,XAGUSD"
input int    SampleMs   = 1000;       // spread sampling interval
input int    MaxPending = 300;        // minutes kept in memory while the backend is unreachable

struct Acc
{
   string   bsym;      // broker symbol
   string   sym;       // normalised symbol sent to the backend
   datetime minute;    // UTC minute being accumulated
   double   smin, smax, ssum;
   int      n;
   double   bid, ask;
};

Acc    acc[];
string pending[];

string Clean(string s) { StringReplace(s, "\"", "'"); StringReplace(s, "\\", "/"); return s; }
string D(double v, int d = 5) { return DoubleToString(v, d); }

int OnInit()
{
   if (StringLen(FeedToken) < 16) { Print("GoldAI_CostFeed: set FeedToken (BROKER_FEED_TOKEN from .env)"); return INIT_PARAMETERS_INCORRECT; }
   string parts[];
   int k = StringSplit(Symbols, ',', parts);
   ArrayResize(acc, 0);
   for (int i = 0; i < k; i++)
   {
      string p = parts[i]; StringTrimLeft(p); StringTrimRight(p);
      if (p == "") continue;
      string bs = p, ns = p;
      int eq = StringFind(p, "=");
      if (eq > 0) { bs = StringSubstr(p, 0, eq); ns = StringSubstr(p, eq + 1); }
      if (!SymbolSelect(bs, true)) { Print("GoldAI_CostFeed: unknown symbol ", bs); continue; }
      int j = ArraySize(acc); ArrayResize(acc, j + 1);
      acc[j].bsym = bs; acc[j].sym = ns; acc[j].minute = 0; acc[j].n = 0;
   }
   if (ArraySize(acc) == 0) return INIT_PARAMETERS_INCORRECT;
   EventSetMillisecondTimer(MathMax(SampleMs, 200));
   Print("GoldAI_CostFeed started: ", ArraySize(acc), " symbol(s) → ", BackendURL);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); }

string QuoteJson(const Acc &a)
{
   string s = a.bsym;
   double point = MarketInfo(s, MODE_POINT);
   long   r3    = SymbolInfoInteger(s, SYMBOL_SWAP_ROLLOVER3DAYS);
   return StringFormat(
      "{\"broker\":\"%s\",\"server\":\"%s\",\"is_demo\":%s,\"symbol\":\"%s\",\"broker_symbol\":\"%s\",\"ts\":%I64d,"
      "\"bid\":%s,\"ask\":%s,\"spread_min\":%s,\"spread_avg\":%s,\"spread_max\":%s,\"ticks\":%d,"
      "\"point\":%s,\"digits\":%d,\"contract_size\":%s,\"swap_long\":%s,\"swap_short\":%s,\"swap_type\":%d,"
      "\"swap_3day\":%d,\"stop_level\":%s}",
      Clean(AccountCompany()), Clean(AccountServer()), IsDemo() ? "true" : "false", Clean(a.sym), Clean(s), (long)a.minute,
      D(a.bid), D(a.ask), D(a.smin), D(a.ssum / a.n), D(a.smax), a.n,
      D(point, 8), (int)MarketInfo(s, MODE_DIGITS), D(MarketInfo(s, MODE_LOTSIZE), 2),
      D(MarketInfo(s, MODE_SWAPLONG), 4), D(MarketInfo(s, MODE_SWAPSHORT), 4), (int)MarketInfo(s, MODE_SWAPTYPE),
      (int)r3, D(MarketInfo(s, MODE_STOPLEVEL) * point));
}

void Push(string q)
{
   int n = ArraySize(pending);
   if (n >= MaxPending) { for (int i = 1; i < n; i++) pending[i - 1] = pending[i]; n--; ArrayResize(pending, n); }
   ArrayResize(pending, n + 1); pending[n] = q;
}

void Flush()
{
   int n = ArraySize(pending);
   if (n == 0) return;
   string body = "{\"quotes\":[";
   for (int i = 0; i < n; i++) body += (i ? "," : "") + pending[i];
   body += "]}";
   char data[], result[]; string rh;
   int len = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, len - 1);   // drop the terminating \0
   string headers = "Content-Type: application/json\r\nX-Feed-Token: " + FeedToken + "\r\n";
   ResetLastError();
   int code = WebRequest("POST", BackendURL, headers, 5000, data, result, rh);
   if (code == 200) { ArrayResize(pending, 0); return; }
   int err = GetLastError();
   if (code == -1 && err == 4060)
      Print("GoldAI_CostFeed: add the backend URL in Tools → Options → Expert Advisors → Allow WebRequest");
   else
      Print("GoldAI_CostFeed: send failed, HTTP ", code, " err ", err, " — kept ", n, " minute(s) for retry");
}

void OnTimer()
{
   datetime now = TimeGMT();
   datetime minute = now - now % 60;
   for (int i = 0; i < ArraySize(acc); i++)
   {
      double bid = MarketInfo(acc[i].bsym, MODE_BID), ask = MarketInfo(acc[i].bsym, MODE_ASK);
      if (bid <= 0 || ask <= 0 || ask < bid) continue;
      if (acc[i].minute != minute)
      {
         if (acc[i].minute != 0 && acc[i].n > 0) Push(QuoteJson(acc[i]));
         acc[i].minute = minute; acc[i].smin = DBL_MAX; acc[i].smax = 0; acc[i].ssum = 0; acc[i].n = 0;
      }
      double s = ask - bid;
      acc[i].smin = MathMin(acc[i].smin, s); acc[i].smax = MathMax(acc[i].smax, s);
      acc[i].ssum += s; acc[i].n++; acc[i].bid = bid; acc[i].ask = ask;
   }
   static datetime lastFlush = 0;
   if (minute != lastFlush && ArraySize(pending) > 0) { lastFlush = minute; Flush(); }
}
