//+------------------------------------------------------------------+
//|  GoldAI_CostFeed.mq5  (MetaTrader 5 version of the MT4 EA)        |
//|  Sends the broker's REAL spread and swap to the Gold AI backend.  |
//|  Read-only: never opens, modifies or closes positions.            |
//|                                                                   |
//|  Setup: Tools → Options → Expert Advisors → Allow WebRequest for  |
//|  http://127.0.0.1:8001 ; attach to any chart; FeedToken =         |
//|  BROKER_FEED_TOKEN from gold_ai/.env; Symbols e.g. "GOLD=XAUUSD". |
//+------------------------------------------------------------------+
#property copyright "Gold AI"
#property description "Per-minute spread / swap feed for broker cost calibration (no trading)."

input string BackendURL = "http://127.0.0.1:8001/api/v1/broker/quotes";
input string FeedToken  = "";
input string Symbols    = "XAUUSD";
input int    SampleMs   = 1000;
input int    MaxPending = 300;

struct Acc
{
   string   bsym;
   string   sym;
   datetime minute;
   double   smin, smax, ssum;
   int      n;
   double   bid, ask;
};

Acc    acc[];
string pending[];

string Clean(string s) { StringReplace(s, "\"", "'"); StringReplace(s, "\\", "/"); return s; }
string D(double v, int d = 5) { return DoubleToString(v, d); }

// map MT5 swap modes onto the MT4 codes the backend understands
int SwapType(string s)
{
   long m = SymbolInfoInteger(s, SYMBOL_SWAP_MODE);
   if (m == SYMBOL_SWAP_MODE_POINTS) return 0;
   if (m == SYMBOL_SWAP_MODE_CURRENCY_SYMBOL) return 1;
   if (m == SYMBOL_SWAP_MODE_INTEREST_CURRENT || m == SYMBOL_SWAP_MODE_INTEREST_OPEN) return 2;
   if (m == SYMBOL_SWAP_MODE_CURRENCY_MARGIN || m == SYMBOL_SWAP_MODE_CURRENCY_DEPOSIT) return 3;
   return -1;   // disabled / reopen modes → backend reports swap as unknown
}

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
   Print("GoldAI_CostFeed started: ", ArraySize(acc), " symbol(s) -> ", BackendURL);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); }

string QuoteJson(const Acc &a)
{
   string s = a.bsym;
   double point = SymbolInfoDouble(s, SYMBOL_POINT);
   bool demo = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO;
   return StringFormat(
      "{\"broker\":\"%s\",\"server\":\"%s\",\"is_demo\":%s,\"symbol\":\"%s\",\"broker_symbol\":\"%s\",\"ts\":%I64d,"
      "\"bid\":%s,\"ask\":%s,\"spread_min\":%s,\"spread_avg\":%s,\"spread_max\":%s,\"ticks\":%d,"
      "\"point\":%s,\"digits\":%d,\"contract_size\":%s,\"swap_long\":%s,\"swap_short\":%s,\"swap_type\":%d,"
      "\"swap_3day\":%d,\"stop_level\":%s}",
      Clean(AccountInfoString(ACCOUNT_COMPANY)), Clean(AccountInfoString(ACCOUNT_SERVER)), demo ? "true" : "false",
      Clean(a.sym), Clean(s), (long)a.minute,
      D(a.bid), D(a.ask), D(a.smin), D(a.ssum / a.n), D(a.smax), a.n,
      D(point, 8), (int)SymbolInfoInteger(s, SYMBOL_DIGITS), D(SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE), 2),
      D(SymbolInfoDouble(s, SYMBOL_SWAP_LONG), 4), D(SymbolInfoDouble(s, SYMBOL_SWAP_SHORT), 4), SwapType(s),
      (int)SymbolInfoInteger(s, SYMBOL_SWAP_ROLLOVER3DAYS), D(SymbolInfoInteger(s, SYMBOL_TRADE_STOPS_LEVEL) * point));
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
   ArrayResize(data, len - 1);
   string headers = "Content-Type: application/json\r\nX-Feed-Token: " + FeedToken + "\r\n";
   ResetLastError();
   int code = WebRequest("POST", BackendURL, headers, 5000, data, result, rh);
   if (code == 200) { ArrayResize(pending, 0); return; }
   int err = GetLastError();
   if (code == -1 && err == 4014)
      Print("GoldAI_CostFeed: add the backend URL in Tools -> Options -> Expert Advisors -> Allow WebRequest");
   else
      Print("GoldAI_CostFeed: send failed, HTTP ", code, " err ", err, " - kept ", n, " minute(s) for retry");
}

void OnTimer()
{
   datetime now = TimeGMT();
   datetime minute = now - now % 60;
   for (int i = 0; i < ArraySize(acc); i++)
   {
      double bid = SymbolInfoDouble(acc[i].bsym, SYMBOL_BID), ask = SymbolInfoDouble(acc[i].bsym, SYMBOL_ASK);
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
