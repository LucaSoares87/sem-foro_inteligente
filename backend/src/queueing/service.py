from src.queueing.engine import QueueEstimator

class QueueService:
    def __init__(self,tracking,analytics,geometry):
        self.tracking=tracking
        self.analytics=analytics
        self.geometry=geometry
        self.engines={}
        self.results={}
        self.errors={}
        self.processed=0
        self.failed=0
        self.optimizer=None
        self.persistence=None

    def consume(self,batch):
        source=batch.source_id
        config=self.geometry.get(source)
        if config is None or not config.approaches:
            return
        try:
            analytics_snapshot=self.analytics.latest(source)
            if analytics_snapshot is None:
                return
            engine=self.engines.get(source)
            if engine is None:
                engine=self.engines[source]=QueueEstimator(config)
            spec=self.tracking.vision.video.sessions[source].spec
            snapshot=engine.consume(batch,analytics_snapshot,spec)
            self.results[source]=snapshot
            self.errors.pop(source,None)
            self.processed+=1
            experiment=self.optimizer.consume(snapshot) if self.optimizer is not None else None
            if self.persistence is not None:
                self.persistence.consume(snapshot,experiment)
        except Exception:
            self.engines.pop(source,None)
            self.results.pop(source,None)
            self.errors[source]="queue_estimation_failed"
            self.failed+=1

    def clear(self):
        self.engines.clear()
        self.results.clear()
        self.errors.clear()
        if self.optimizer is not None:
            self.optimizer.clear()

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
        configured=sum(bool(config.approaches) for config in self.geometry.values())
        sources=[]
        for source in self.geometry:
            result=self.latest(source)
            if result is not None:
                sources.append(result.model_dump(mode="json"))
        state=("not_configured" if configured==0 else "degraded" if self.errors else
               "available" if sources else "idle")
        return {"state":state,"configured_sources":configured,"processed":self.processed,
                "failed":self.failed,"errors":dict(self.errors),"sources":sources,
                "physical_speed_available":False,"operationally_validated":False,
                "decision_mode":"simulation_only"}

    def health_status(self):
        status=self.status()
        return {k:status[k] for k in ("state","configured_sources","processed","failed",
                                      "physical_speed_available","operationally_validated","decision_mode")}
