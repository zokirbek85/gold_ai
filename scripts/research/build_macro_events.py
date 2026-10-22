import re, csv
from datetime import datetime, time
from zoneinfo import ZoneInfo
NY=ZoneInfo("America/New_York"); UTC=ZoneInfo("UTC")
rows=[]
def add(kind, d, hh, mm, src):
    loc=datetime.combine(d, time(hh,mm), NY); rows.append((kind, d.isoformat(), loc.astimezone(UTC).strftime("%Y-%m-%d %H:%M"), src))
e=open("empsit.htm").read(); c=open("cpi.htm").read(); f=open("fomccalendars.htm").read()
for m in sorted(set(re.findall(r'empsit_(\d{2})(\d{2})(\d{4})\.htm', e))):
    add("NFP", datetime(int(m[2]),int(m[0]),int(m[1])).date(), 8,30, "bls.gov/bls/news-release/empsit.htm")
for m in sorted(set(re.findall(r'cpi_(\d{2})(\d{2})(\d{4})\.htm', c))):
    add("CPI", datetime(int(m[2]),int(m[0]),int(m[1])).date(), 8,30, "bls.gov/bls/news-release/cpi.htm")
for y,mo,d in sorted(set(re.findall(r'pressreleases/monetary(\d{4})(\d{2})(\d{2})a\.htm', f))):
    i=f.find(f"monetary{y}{mo}{d}a"); ctx=f[max(0,i-400):i]
    if "notation vote" in ctx or "unscheduled" in ctx.lower(): continue
    add("FOMC", datetime(int(y),int(mo),int(d)).date(), 14,0, "federalreserve.gov/monetarypolicy/fomccalendars.htm")
rows=[r for r in rows if "2022-01-01"<=r[1]<="2026-10-21"]
with open("events.csv","w",newline="") as fh:
    w=csv.writer(fh); w.writerow(["kind","date","release_utc","source"]); w.writerows(sorted(rows,key=lambda r:r[2]))
from collections import Counter; print(len(rows), Counter(r[0] for r in rows))
