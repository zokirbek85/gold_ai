import sys, warnings, json; warnings.filterwarnings("ignore")
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import numpy as np, pandas as pd
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from strategy.data_quality import clean_candles
from services.ml_service import _build_dataset
now=datetime(2026,10,22,7)
h4,_=clean_candles(pd.read_csv(sys.argv[1]),240,now)
c=h4.to_dict("records")
X,y=_build_dataset(c)               # the production feature/label code, unchanged
X,y=np.array(X),np.array(y)
ts=pd.to_datetime([c[i]["timestamp"] for i in range(50,len(c)-5)])[:len(y)]
res=[]; allp=[]; ally=[]
for start in pd.date_range("2022-01-01","2026-04-01",freq="6MS"):
    tr=ts<start; te=(ts>=start)&(ts<start+pd.DateOffset(months=6))
    # purge 5 bars before the test window (labels look 5 bars ahead)
    tr_idx=np.flatnonzero(tr)[:-5]
    if te.sum()<50: continue
    m=RandomForestClassifier(n_estimators=100,max_depth=10,random_state=42,n_jobs=-1).fit(X[tr_idx],y[tr_idx])
    p=m.predict(X[te]); maj=pd.Series(y[tr_idx]).mode()[0]
    res.append({"test_start":str(start.date()),"n":int(te.sum()),"acc":round(accuracy_score(y[te],p),3),
                "majority_baseline_acc":round(float((y[te]==maj).mean()),3),"balanced_acc":round(balanced_accuracy_score(y[te],p),3)})
    allp+=list(p); ally+=list(y[te])
allp,ally=np.array(allp),np.array(ally)
out={"windows":res,"pooled":{"n":len(ally),"acc":round(float((allp==ally).mean()),3),
     "balanced_acc":round(float(balanced_accuracy_score(ally,allp)),3),"chance_balanced":0.333,
     "label_dist":{int(k):int(v) for k,v in zip(*np.unique(ally,return_counts=True))}}}
json.dump(out,open(sys.argv[2],"w"),indent=1); print(json.dumps(out["pooled"])); [print(r) for r in res]
