from src.analytics.engine import TrafficEngine

class AnalyticsService:
    def __init__(self,tracking,geometry,config_invalid=False):
        self.tracking=tracking
        self.geometry=geometry
        self.config_invalid=config_invalid
        self.engines={}
        self.results={}
        self.errors={}
        self.processed=0
        self.failed=0

    def consume(self,batch):
        source=batch.source_id
        if source not in self.geometry:
            return
        try:
            engine=self.engines.get(source)
            if engine is None:
                engine=self.engines[source]=TrafficEngine(self.geometry[source])
            self.results[source]=engine.consume(batch)
            self.errors.pop(source,None)
            self.processed+=1
        except Exception:
            self.engines.pop(source,None)
            self.results.pop(source,None)
            self.errors[source]="analytics_failed"
            self.failed+=1

    def clear(self):
        self.engines.clear()
        self.results.clear()
        self.errors.clear()

    def latest(self,source):
        tracked=self.tracking.latest(source)
        result=self.results.get(source)
        if tracked is None or result is None:
            return None
        if (tracked.session_id,tracked.tracking_epoch,tracked.frame_sequence,tracked.model_sha256)!=(
                result.session_id,result.tracking_epoch,result.frame_sequence,result.model_sha256):
            return None
        return result

    def status(self):
        snapshots=[]
        for source in self.geometry:
            result=self.latest(source)
            if result is not None:
                session=self.tracking.vision.video.sessions[source]
                snapshots.append({**result.model_dump(mode="json"),"live":session.state=="running"})
        state=("error" if self.config_invalid else "not_configured" if not self.geometry else
               "degraded" if self.errors else "available" if snapshots else "idle")
        return {"state":state,"configured_sources":len(self.geometry),"processed":self.processed,
                "failed":self.failed,"error_code":"geometry_config_invalid" if self.config_invalid else None,
                "errors":dict(self.errors),"sources":snapshots,"operationally_validated":False,
                "decision_mode":"abstention_only"}
