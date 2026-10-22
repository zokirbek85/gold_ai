import os, sys, csv, time, httpx
from datetime import datetime, timedelta
k=os.environ["TWELVEDATA_API_KEY"]; os.makedirs("m1",exist_ok=True)
for ev in csv.DictReader(open("events.csv")):
    out=f"m1/{ev['kind']}_{ev['date']}.csv"
    if os.path.exists(out): continue
    t=datetime.strptime(ev["release_utc"],"%Y-%m-%d %H:%M")
    p={"symbol":"XAU/USD","interval":"1min","start_date":(t-timedelta(minutes=120)).strftime("%Y-%m-%d %H:%M:%S"),
       "end_date":(t+timedelta(minutes=240)).strftime("%Y-%m-%d %H:%M:%S"),"timezone":"UTC","apikey":k,"order":"asc","outputsize":5000}
    for attempt in range(3):
        d=httpx.get("https://api.twelvedata.com/time_series",params=p,timeout=60).json()
        if d.get("status")=="ok": break
        print("retry",out,d.get("code"),str(d.get("message"))[:80],flush=True); time.sleep(65)
    v=d.get("values",[])
    with open(out,"w",newline="") as fh:
        w=csv.writer(fh); w.writerow(["timestamp","open","high","low","close"])
        for r in v: w.writerow([r["datetime"],r["open"],r["high"],r["low"],r["close"]])
    print(out,len(v),flush=True); time.sleep(8)
print("DONE")
