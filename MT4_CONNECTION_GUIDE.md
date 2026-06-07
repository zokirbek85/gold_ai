# MT4 Connection Guide — Gold AI Platform

MT4 does not have an official Python API. Gold AI connects to MT4 using a
**ZeroMQ bridge**: a small Expert Advisor (EA) installed inside MT4 that
forwards ticks and candles to the Python backend over two ZeroMQ sockets.

---

## Architecture

```
┌──────────────────────────┐        ZeroMQ TCP        ┌──────────────────────┐
│   MetaTrader 4 (Windows) │◄──────────────────────►  │  Gold AI Backend     │
│                          │                           │  (Python / Docker)   │
│  ┌────────────────────┐  │  Port 32768 (CMD)         │                      │
│  │  ZeroMQ Bridge EA  │◄─┼── Commands (GET_CANDLES)  │  mt4_connector.py    │
│  │   (MQL4 Expert)    │  │                           │                      │
│  │                    │─►┼── Responses (JSON)        │  scheduler.py        │
│  │                    │  │  Port 32769 (DATA)        │                      │
│  │                    │─►┼── Live ticks/candles PUB  │                      │
│  └────────────────────┘  │                           │                      │
└─────────��────────────────┘                           └──────────────────��───┘
```

Two ZeroMQ sockets:

| Socket | Direction | Default Port | Purpose |
|--------|-----------|-------------|---------|
| CMD    | REQ ↔ REP | 32768 | Python sends commands, EA replies with data |
| DATA   | PUB → SUB | 32769 | EA streams live ticks and candles |

---

## Step 1 — Install ZeroMQ in MetaTrader 4

1. Download the **ZeroMQ for MQL4** library:
   - Official release: https://github.com/dingmaotu/mql-zmq/releases
   - Download `ZeroMQ-4.x.x-mt4.zip`

2. Unzip and copy the files:
   ```
   libzmq.dll      →  MT4_Data_Folder\MQL4\Libraries\
   ZeroMQ.mqh      →  MT4_Data_Folder\MQL4\Include\
   ```
   To find your MT4 data folder: **File → Open Data Folder** inside MT4.

3. Restart MetaTrader 4.

---

## Step 2 — Install the Bridge EA

Create a new Expert Advisor in MT4 (**Tools → MetaEditor → New → Expert Advisor**),
name it `GoldAI_Bridge`, and paste this code:

```mql4
//+------------------------------------------------------------------+
//|  GoldAI_Bridge.mq4  — ZeroMQ bridge for Gold AI platform        |
//+------------------------------------------------------------------+
#property strict
#include <ZeroMQ/ZeroMQ.mqh>

input int    CMD_PORT  = 32768;   // Command socket port
input int    DATA_PORT = 32769;   // Data publish port
input string SYMBOLS   = "XAUUSD,EURUSD,GBPUSD";
input int    TICK_INTERVAL_MS = 500;  // Publish tick every N ms

Context ctx;
Socket  cmdSocket(ctx, ZMQ_REP);
Socket  dataSocket(ctx, ZMQ_PUB);

string symbolList[];
datetime lastTickTime = 0;

int OnInit() {
    // Bind command socket (EA listens for commands from Python)
    cmdSocket.bind(StringFormat("tcp://*:%d", CMD_PORT));
    // Bind data socket (EA publishes live data)
    dataSocket.bind(StringFormat("tcp://*:%d", DATA_PORT));

    // Parse symbol list
    StringSplit(SYMBOLS, ',', symbolList);

    Print("GoldAI Bridge started — CMD:", CMD_PORT, " DATA:", DATA_PORT);
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {
    cmdSocket.unbind(StringFormat("tcp://*:%d", CMD_PORT));
    dataSocket.unbind(StringFormat("tcp://*:%d", DATA_PORT));
    Print("GoldAI Bridge stopped");
}

void OnTick() {
    // Handle incoming commands
    HandleCommands();

    // Publish live tick if interval elapsed
    if (GetTickCount() - lastTickTime >= TICK_INTERVAL_MS) {
        PublishTicks();
        lastTickTime = GetTickCount();
    }
}

void HandleCommands() {
    ZmqMsg request;
    if (!cmdSocket.recv(request, ZMQ_DONTWAIT)) return;

    string msg = request.getData();
    // Parse simple JSON manually (key:"action")
    string action = ExtractJsonString(msg, "action");

    string response = "";

    if (action == "PING") {
        response = "{\"status\":\"OK\",\"data\":\"pong\"}";

    } else if (action == "GET_ACCOUNT") {
        response = StringFormat(
            "{\"status\":\"OK\",\"data\":{\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f}}",
            AccountBalance(), AccountEquity(), AccountMargin(), AccountFreeMargin()
        );

    } else if (action == "GET_TICKS") {
        string symbol = ExtractJsonString(msg, "symbol");
        int count     = (int)ExtractJsonInt(msg, "count");
        if (count <= 0) count = 100;
        response = GetTicksJson(symbol, count);

    } else if (action == "GET_CANDLES") {
        string symbol   = ExtractJsonString(msg, "symbol");
        int    timeframe = (int)ExtractJsonInt(msg, "timeframe");
        int    count    = (int)ExtractJsonInt(msg, "count");
        if (count <= 0)    count = 100;
        if (timeframe <= 0) timeframe = 60;
        response = GetCandlesJson(symbol, timeframe, count);

    } else {
        response = "{\"status\":\"ERROR\",\"message\":\"Unknown action\"}";
    }

    ZmqMsg reply(response);
    cmdSocket.send(reply);
}

void PublishTicks() {
    for (int i = 0; i < ArraySize(symbolList); i++) {
        string sym = symbolList[i];
        StringTrimLeft(sym); StringTrimRight(sym);
        double bid = MarketInfo(sym, MODE_BID);
        double ask = MarketInfo(sym, MODE_ASK);
        if (bid <= 0) continue;

        string tick = StringFormat(
            "{\"type\":\"tick\",\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,"
            "\"last\":%.5f,\"time\":%d,\"volume\":0}",
            sym, bid, ask, bid, (int)TimeCurrent()
        );
        ZmqMsg msg(tick);
        dataSocket.send(msg);
    }
}

string GetCandlesJson(string symbol, int tf, int count) {
    string arr = "[";
    for (int i = count - 1; i >= 0; i--) {
        datetime t = iTime(symbol, tf, i);
        double o   = iOpen(symbol, tf, i);
        double h   = iHigh(symbol, tf, i);
        double l   = iLow(symbol, tf, i);
        double c   = iClose(symbol, tf, i);
        long   v   = iVolume(symbol, tf, i);

        if (i < count - 1) arr += ",";
        arr += StringFormat(
            "{\"time\":%d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"tick_volume\":%d}",
            (int)t, o, h, l, c, (int)v
        );
    }
    arr += "]";
    return "{\"status\":\"OK\",\"data\":" + arr + "}";
}

string GetTicksJson(string symbol, int count) {
    // Return last N bid prices as tick-like objects
    string arr = "[";
    for (int i = count - 1; i >= 0; i--) {
        if (i < count - 1) arr += ",";
        arr += StringFormat(
            "{\"time\":%d,\"last\":%.5f,\"volume\":0}",
            (int)iTime(symbol, PERIOD_M1, i),
            iClose(symbol, PERIOD_M1, i)
        );
    }
    arr += "]";
    return "{\"status\":\"OK\",\"data\":" + arr + "}";
}

// ---- Minimal JSON helpers ----
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
    while (end < StringLen(json) && StringGetCharacter(json, end) != ',' &&
           StringGetCharacter(json, end) != '}') end++;
    return StringToInteger(StringSubstr(json, pos, end - pos));
}
```

4. Compile the EA (**F7** in MetaEditor) — it must compile with **0 errors**.

---

## Step 3 — Attach the EA to a Chart

1. Open a **XAUUSD M1 chart** in MT4.
2. Drag **GoldAI_Bridge** from the Navigator onto the chart.
3. In the EA settings dialog:
   - Set **CMD_PORT = 32768** (must match `MT4_CMD_PORT` in `.env`)
   - Set **DATA_PORT = 32769** (must match `MT4_DATA_PORT` in `.env`)
   - Set **SYMBOLS = XAUUSD,EURUSD** (comma-separated, no spaces)
   - Enable **"Allow DLL imports"** and **"Allow live trading"**
4. Click **OK**. You should see a smiley face (☺) in the top-right of the chart and `GoldAI Bridge started` in the Experts log.

---

## Step 4 — Configure Gold AI Backend

Edit your `.env` file:

```env
MT4_HOST=localhost          # Use Windows machine IP if MT4 is on a different machine
MT4_CMD_PORT=32768
MT4_DATA_PORT=32769
MT4_SYMBOLS=XAUUSD,EURUSD
MT4_TIMEFRAMES=1,5,15,60,240
MT4_INGEST_INTERVAL_SECONDS=60
```

Install the Python ZeroMQ library:

```bash
pip install pyzmq
```

---

## Step 5 — Test the Connection

```bash
python - <<'EOF'
import zmq, json
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.setsockopt(zmq.RCVTIMEO, 3000)
sock.connect("tcp://localhost:32768")
sock.send_string(json.dumps({"action": "PING"}))
print(sock.recv_string())   # Should print: {"status":"OK","data":"pong"}
sock.send_string(json.dumps({"action": "GET_CANDLES", "symbol": "XAUUSD", "timeframe": 60, "count": 5}))
print(sock.recv_string())   # Should print candle JSON
EOF
```

Expected output:
```
{"status":"OK","data":"pong"}
{"status":"OK","data":[{"time":...,"open":...,"high":...}]}
```

---

## Cross-Machine Setup (MT4 on Windows, Backend on Linux/Mac)

If MT4 and the backend run on different machines:

1. **On the Windows machine** — allow ports 32768 and 32769 through the firewall:
   ```
   Windows Defender Firewall → Inbound Rules → New Rule → Port → TCP 32768,32769
   ```

2. **In `.env`** — set `MT4_HOST` to the Windows machine's local IP:
   ```env
   MT4_HOST=192.168.1.50
   ```

3. The EA binds to `0.0.0.0` so it accepts connections from any IP automatically.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `pyzmq not installed` | Library missing | `pip install pyzmq` |
| `MT4 ping failed` | EA not running | Attach EA to chart, check smiley face |
| `MT4 ping failed` | Wrong port | Confirm `CMD_PORT` matches `.env` `MT4_CMD_PORT` |
| `libzmq.dll not found` | DLL missing from Libraries | Copy `libzmq.dll` to `MQL4\Libraries\` |
| EA shows angry face (✗) | DLL imports disabled | Enable "Allow DLL imports" in EA settings |
| Data socket no ticks | Wrong symbol name | Check `SYMBOLS` setting — must match MT4 broker exact name (e.g. `XAUUSDm`) |
| Backend on Docker, MT4 on host | Docker networking | Set `MT4_HOST=host.docker.internal` in `.env` |

---

## Supported Timeframes

| Value in `.env` | MT4 Period Constant | Label |
|----------------|---------------------|-------|
| 1 | PERIOD_M1 | 1 Minute |
| 5 | PERIOD_M5 | 5 Minutes |
| 15 | PERIOD_M15 | 15 Minutes |
| 30 | PERIOD_M30 | 30 Minutes |
| 60 | PERIOD_H1 | 1 Hour |
| 240 | PERIOD_H4 | 4 Hours |
| 1440 | PERIOD_D1 | Daily |

---

## EA Source Files

The full EA source is embedded in this guide above. You can also find it at:

```
/gold_ai/mt4/GoldAI_Bridge.mq4      ← EA source
/gold_ai/mt4/GoldAI_Bridge.ex4      ← compiled binary (build after copy)
```

These are created automatically when you compile in MetaEditor.
