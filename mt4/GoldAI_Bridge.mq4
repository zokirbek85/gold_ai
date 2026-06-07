//+------------------------------------------------------------------+
//|  GoldAI_Bridge.mq4                                               |
//|  ZeroMQ bridge EA for Gold AI Trading Intelligence Platform      |
//|                                                                  |
//|  SETUP:                                                          |
//|    1. Copy libzmq.dll to MQL4\Libraries\                         |
//|    2. Copy ZeroMQ.mqh  to MQL4\Include\ZeroMQ\                   |
//|    3. Compile this EA in MetaEditor (F7)                         |
//|    4. Attach to a XAUUSD M1 chart                                |
//|    5. Enable "Allow DLL imports" in EA settings                  |
//|                                                                  |
//|  See MT4_CONNECTION_GUIDE.md for full instructions               |
//+------------------------------------------------------------------+
#property strict
#property description "Gold AI ZeroMQ Data Bridge"
#include <ZeroMQ\ZeroMQ.mqh>

input int    CMD_PORT        = 32768;
input int    DATA_PORT       = 32769;
input string SYMBOLS         = "XAUUSD,EURUSD";
input int    TICK_INTERVAL_MS = 500;

Context ctx;
Socket  cmdSocket(ctx,  ZMQ_REP);
Socket  dataSocket(ctx, ZMQ_PUB);

string symbolList[];
uint   lastTickMs = 0;

//+------------------------------------------------------------------+
int OnInit() {
    cmdSocket.bind(StringFormat("tcp://*:%d",  CMD_PORT));
    dataSocket.bind(StringFormat("tcp://*:%d", DATA_PORT));
    StringSplit(SYMBOLS, ',', symbolList);
    Print("GoldAI Bridge started | CMD:", CMD_PORT, " | DATA:", DATA_PORT,
          " | Symbols:", SYMBOLS);
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
    cmdSocket.unbind(StringFormat("tcp://*:%d",  CMD_PORT));
    dataSocket.unbind(StringFormat("tcp://*:%d", DATA_PORT));
    Print("GoldAI Bridge stopped");
}

//+------------------------------------------------------------------+
void OnTick() {
    HandleCommands();
    if (GetTickCount() - lastTickMs >= (uint)TICK_INTERVAL_MS) {
        PublishTicks();
        lastTickMs = GetTickCount();
    }
}

//+------------------------------------------------------------------+
void HandleCommands() {
    ZmqMsg request;
    if (!cmdSocket.recv(request, ZMQ_DONTWAIT)) return;

    string msg    = request.getData();
    string action = ExtractJsonString(msg, "action");
    string response;

    if (action == "PING") {
        response = "{\"status\":\"OK\",\"data\":\"pong\"}";

    } else if (action == "GET_ACCOUNT") {
        response = StringFormat(
            "{\"status\":\"OK\",\"data\":{\"balance\":%.2f,\"equity\":%.2f,"
            "\"margin\":%.2f,\"free_margin\":%.2f,\"currency\":\"%s\"}}",
            AccountBalance(), AccountEquity(), AccountMargin(),
            AccountFreeMargin(), AccountCurrency()
        );

    } else if (action == "GET_TICKS") {
        string sym = ExtractJsonString(msg, "symbol");
        int    cnt = (int)ExtractJsonInt(msg, "count");
        if (cnt <= 0) cnt = 100;
        response = GetTicksJson(sym, cnt);

    } else if (action == "GET_CANDLES") {
        string sym = ExtractJsonString(msg, "symbol");
        int    tf  = (int)ExtractJsonInt(msg, "timeframe");
        int    cnt = (int)ExtractJsonInt(msg, "count");
        if (cnt <= 0) cnt = 100;
        if (tf  <= 0) tf  = 60;
        response = GetCandlesJson(sym, tf, cnt);

    } else {
        response = "{\"status\":\"ERROR\",\"message\":\"Unknown action: " + action + "\"}";
    }

    ZmqMsg reply(response);
    cmdSocket.send(reply);
}

//+------------------------------------------------------------------+
void PublishTicks() {
    for (int i = 0; i < ArraySize(symbolList); i++) {
        string sym = symbolList[i];
        StringTrimLeft(sym);
        StringTrimRight(sym);
        if (StringLen(sym) == 0) continue;

        double bid = MarketInfo(sym, MODE_BID);
        double ask = MarketInfo(sym, MODE_ASK);
        if (bid <= 0) continue;

        string payload = StringFormat(
            "{\"type\":\"tick\",\"symbol\":\"%s\","
            "\"bid\":%.5f,\"ask\":%.5f,\"last\":%.5f,"
            "\"spread\":%.5f,\"time\":%d,\"volume\":0}",
            sym, bid, ask, bid, ask - bid, (int)TimeCurrent()
        );
        ZmqMsg msg(payload);
        dataSocket.send(msg);
    }
}

//+------------------------------------------------------------------+
string GetCandlesJson(string symbol, int tf, int count) {
    string arr = "[";
    for (int i = count - 1; i >= 0; i--) {
        double o = iOpen(symbol,  tf, i);
        double h = iHigh(symbol,  tf, i);
        double l = iLow(symbol,   tf, i);
        double c = iClose(symbol, tf, i);
        long   v = iVolume(symbol, tf, i);
        datetime t = iTime(symbol, tf, i);

        if (i < count - 1) arr += ",";
        arr += StringFormat(
            "{\"time\":%d,\"open\":%.5f,\"high\":%.5f,"
            "\"low\":%.5f,\"close\":%.5f,\"tick_volume\":%d}",
            (int)t, o, h, l, c, (int)v
        );
    }
    return "{\"status\":\"OK\",\"data\":" + arr + "]}";
}

//+------------------------------------------------------------------+
string GetTicksJson(string symbol, int count) {
    string arr = "[";
    for (int i = count - 1; i >= 0; i--) {
        if (i < count - 1) arr += ",";
        arr += StringFormat(
            "{\"time\":%d,\"last\":%.5f,\"volume\":0}",
            (int)iTime(symbol, PERIOD_M1, i),
            iClose(symbol, PERIOD_M1, i)
        );
    }
    return "{\"status\":\"OK\",\"data\":" + arr + "]}";
}

//+------------------------------------------------------------------+
//  Minimal JSON field extractors (no external JSON library needed)  |
//+------------------------------------------------------------------+
string ExtractJsonString(string json, string key) {
    string search = "\"" + key + "\":\"";
    int pos = StringFind(json, search);
    if (pos < 0) return "";
    pos += StringLen(search);
    int end = StringFind(json, "\"", pos);
    if (end < 0) return "";
    return StringSubstr(json, pos, end - pos);
}

long ExtractJsonInt(string json, string key) {
    string search = "\"" + key + "\":";
    int pos = StringFind(json, search);
    if (pos < 0) return 0;
    pos += StringLen(search);
    int end = pos;
    while (end < StringLen(json)) {
        ushort ch = StringGetCharacter(json, end);
        if (ch == ',' || ch == '}' || ch == ' ') break;
        end++;
    }
    return StringToInteger(StringSubstr(json, pos, end - pos));
}
//+------------------------------------------------------------------+
