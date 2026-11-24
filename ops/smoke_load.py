#!/usr/bin/env python3
import argparse
import json
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor,as_completed

def one(url,timeout):
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(url,timeout=timeout) as response:
            response.read()
            ok=200<=response.status<300
            status=response.status
    except Exception:
        ok=False
        status=0
    return ok,status,(time.perf_counter()-start)*1000

def percentile(values,p):
    if not values:
        return 0.0
    ordered=sorted(values)
    index=min(len(ordered)-1,max(0,int(round((len(ordered)-1)*p))))
    return ordered[index]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",required=True)
    parser.add_argument("--requests",type=int,default=100)
    parser.add_argument("--concurrency",type=int,default=10)
    parser.add_argument("--timeout",type=float,default=5)
    parser.add_argument("--p95-ms",type=float,default=5000)
    args=parser.parse_args()
    if not (1<=args.requests<=5000 and 1<=args.concurrency<=100):
        raise SystemExit("limites inválidos")
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results=[future.result() for future in as_completed(
            [pool.submit(one,args.url,args.timeout) for _ in range(args.requests)])]
    latencies=[item[2] for item in results]
    errors=sum(1 for ok,_,_ in results if not ok)
    summary={
        "requests":args.requests,"concurrency":args.concurrency,"errors":errors,
        "mean_ms":round(statistics.fmean(latencies),2),
        "p95_ms":round(percentile(latencies,.95),2),
        "max_ms":round(max(latencies),2),
    }
    print(json.dumps(summary,sort_keys=True))
    if errors or summary["p95_ms"]>args.p95_ms:
        raise SystemExit(1)

if __name__=="__main__":
    main()
