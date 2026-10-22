import os, sys, time, httpx, csv
key=os.environ["TWELVEDATA_API_KEY"]; interval=sys.argv[1]; pages=int(sys.argv[2]); out=sys.argv[3]
rows={}; end=None
for p in range(pages):
    params={"symbol":"XAU/USD","interval":interval,"outputsize":5000,"apikey":key,"format":"JSON","timezone":"UTC","order":"desc"}
    if end: params["end_date"]=end
    d=httpx.get("https://api.twelvedata.com/time_series",params=params,timeout=60).json()
    if d.get("status")=="error": print("err",d.get("code"),d.get("message")[:120]); break
    vals=d.get("values",[])
    for v in vals: rows[v["datetime"]]=v
    print(interval,"page",p,len(vals),vals[-1]["datetime"] if vals else None)
    if len(vals)<5000: break
    end=vals[-1]["datetime"]; time.sleep(8)
with open(out,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["timestamp","open","high","low","close","volume"])
    for k in sorted(rows): v=rows[k]; w.writerow([k,v["open"],v["high"],v["low"],v["close"],v.get("volume",0) or 0])
print("saved",len(rows))
