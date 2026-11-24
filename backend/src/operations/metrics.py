from threading import Lock
from time import monotonic

class OperationsMetrics:
    def __init__(self):
        self.started=monotonic()
        self.lock=Lock()
        self.requests=0
        self.errors=0
        self.denied=0
        self.inflight=0
        self.audit_failures=0
        self.latency_seconds=0.0

    def begin(self):
        with self.lock:
            self.inflight+=1
        return monotonic()

    def finish(self,started,status_code,denied=False):
        elapsed=max(0.0,monotonic()-started)
        with self.lock:
            self.inflight=max(0,self.inflight-1)
            self.requests+=1
            self.latency_seconds+=elapsed
            if status_code>=500:
                self.errors+=1
            if denied:
                self.denied+=1

    def audit_failed(self):
        with self.lock:
            self.audit_failures+=1

    def snapshot(self):
        with self.lock:
            requests=self.requests
            return {
                "uptime_seconds":max(0.0,monotonic()-self.started),
                "requests_total":requests,
                "server_errors_total":self.errors,
                "auth_denied_total":self.denied,
                "requests_inflight":self.inflight,
                "audit_failures_total":self.audit_failures,
                "mean_request_latency_ms":(self.latency_seconds/requests*1000) if requests else 0.0,
            }

    def prometheus(self):
        values=self.snapshot()
        mapping=[
            ("si_uptime_seconds","uptime_seconds"),
            ("si_http_requests_total","requests_total"),
            ("si_http_server_errors_total","server_errors_total"),
            ("si_auth_denied_total","auth_denied_total"),
            ("si_http_requests_inflight","requests_inflight"),
            ("si_audit_failures_total","audit_failures_total"),
            ("si_http_mean_request_latency_ms","mean_request_latency_ms"),
        ]
        return "\n".join(f"{metric} {values[key]}" for metric,key in mapping)+"\n"
