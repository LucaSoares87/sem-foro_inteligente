from collections import deque
from dataclasses import dataclass
from math import hypot
from uuid import uuid4
from src.analytics.geometry import contains,foot
from src.queueing.contracts import QueueApproachState,QueueSnapshot

@dataclass
class TrackState:
    inside: bool
    point: tuple[float,float]
    timestamp: object
    stopped_since: object | None
    queued: bool

class QueueEstimator:
    def __init__(self,config):
        if not config.approaches:
            raise ValueError("queue approaches not configured")
        self.config=config
        self.reset()

    def reset(self):
        self.identity=None
        self.epoch=uuid4()
        self.started=None
        self.track_states={a.approach_id:{} for a in self.config.approaches}
        self.arrivals={a.approach_id:deque() for a in self.config.approaches}
        self.discharges={a.approach_id:deque() for a in self.config.approaches}
        self.line_counts={}

    @staticmethod
    def _line_count(snapshot,approach):
        line=next((x for x in snapshot.lines if x.line_id==approach.discharge_line_id),None)
        if line is None:
            raise ValueError("queue discharge line missing")
        return getattr(line,approach.discharge_direction)

    @staticmethod
    def _purge(events,now,window):
        while events and (now-events[0][0]).total_seconds()>window:
            events.popleft()

    @staticmethod
    def _rate(events,now,window,started):
        elapsed=max(1.0,min(window,(now-started).total_seconds()))
        return min(20.0,sum(count for _,count in events)/elapsed)

    def consume(self,batch,analytics_snapshot,source_spec):
        if analytics_snapshot is None:
            raise ValueError("current analytics required")
        if (batch.source_id,batch.intersection_code,batch.session_id,batch.tracking_epoch,batch.frame_sequence,
            batch.model_sha256)!=(analytics_snapshot.source_id,analytics_snapshot.intersection_code,
            analytics_snapshot.session_id,analytics_snapshot.tracking_epoch,analytics_snapshot.frame_sequence,
            analytics_snapshot.model_sha256):
            raise ValueError("queue analytics identity mismatch")
        identity=(batch.session_id,batch.tracking_epoch,analytics_snapshot.analytics_epoch,
                  analytics_snapshot.geometry_sha256,batch.model_sha256,batch.purpose)
        if identity!=self.identity:
            self.reset()
            self.identity=identity
            self.started=batch.received_at

        confirmed=[track for track in batch.tracks if track.state=="confirmed"]
        tentative=len(batch.tracks)-len(confirmed)
        result=[]
        region_map={r.region_id:r.xyxy for r in self.config.regions}

        for approach in self.config.approaches:
            previous=self.track_states[approach.approach_id]
            current={}
            arrivals=self.arrivals[approach.approach_id]
            discharges=self.discharges[approach.approach_id]
            waits=[]
            visible=0
            queued=0

            for track in confirmed:
                point=foot(track.xyxy)
                inside=contains(region_map[approach.region_id],point)
                before=previous.get(track.track_id)
                if before is not None and not before.inside and inside:
                    arrivals.append((batch.received_at,1))
                stopped_since=None
                is_queued=False
                if inside:
                    visible+=1
                    if before is not None:
                        dt=(batch.received_at-before.timestamp).total_seconds()
                        speed=(hypot(point[0]-before.point[0],point[1]-before.point[1])/dt
                               if dt>0 else float("inf"))
                        if speed<=approach.stop_speed_normalized_per_s:
                            stopped_since=before.stopped_since or batch.received_at
                            waited=max(0.0,(batch.received_at-stopped_since).total_seconds())
                            is_queued=waited>=approach.min_stop_seconds
                            if is_queued:
                                queued+=1
                                waits.append(waited)
                    current[track.track_id]=TrackState(True,point,batch.received_at,stopped_since,is_queued)
                else:
                    current[track.track_id]=TrackState(False,point,batch.received_at,None,False)

            line_count=self._line_count(analytics_snapshot,approach)
            old_count=self.line_counts.get(approach.approach_id)
            if old_count is not None:
                if line_count<old_count:
                    raise ValueError("nonmonotonic queue discharge count")
                delta=line_count-old_count
                if delta:
                    discharges.append((batch.received_at,delta))
            self.line_counts[approach.approach_id]=line_count

            self._purge(arrivals,batch.received_at,approach.rate_window_seconds)
            self._purge(discharges,batch.received_at,approach.rate_window_seconds)
            arrival_rate=self._rate(arrivals,batch.received_at,approach.rate_window_seconds,self.started)
            discharge_rate=self._rate(discharges,batch.received_at,approach.rate_window_seconds,self.started)

            elapsed=max(0.0,(batch.received_at-self.started).total_seconds())
            tracking_den=len(batch.tracks)+batch.lost_private
            tracking_factor=(len(confirmed)/tracking_den if tracking_den else 1.0)
            sampling_factor=1/(1+batch.skipped_frames)
            analytics_factor=.75 if analytics_snapshot.quality=="limited_sampling" else .85 if analytics_snapshot.quality=="initializing" else 1.0
            confidence=max(0.0,min(1.0,approach.visibility_score*tracking_factor*sampling_factor*analytics_factor))
            if not approach.visibility_calibrated:
                confidence=min(.6,confidence)
            quality=("initializing" if elapsed<min(10.0,approach.rate_window_seconds/2) else
                     "limited_sampling" if batch.skipped_frames or batch.lost_private or tentative or
                     analytics_snapshot.quality=="limited_sampling" else "experimental")
            occupancy=min(2.0,queued/approach.storage_capacity_vehicles)
            result.append(QueueApproachState(
                approach_id=approach.approach_id,service_group=approach.service_group,
                visible_vehicles=visible,queue_length=queued,
                stopped_ratio=(queued/visible if visible else 0.0),
                arrival_rate_vps=arrival_rate,discharge_rate_vps=discharge_rate,
                queue_growth_vps=max(-20.0,min(20.0,arrival_rate-discharge_rate)),
                mean_wait_seconds=(sum(waits)/len(waits) if waits else 0.0),
                max_wait_seconds=(max(waits) if waits else 0.0),
                storage_capacity_vehicles=approach.storage_capacity_vehicles,
                storage_occupancy_ratio=occupancy,
                spillback_margin_ratio=max(0.0,1-min(1.0,occupancy)),
                observation_confidence=confidence,
                visibility_calibrated=approach.visibility_calibrated,
                quality=quality))
            self.track_states[approach.approach_id]=current

        return QueueSnapshot(source_id=batch.source_id,intersection_code=batch.intersection_code,
            session_id=batch.session_id,tracking_epoch=batch.tracking_epoch,
            analytics_epoch=analytics_snapshot.analytics_epoch,queue_epoch=self.epoch,
            geometry_sha256=analytics_snapshot.geometry_sha256,model_sha256=batch.model_sha256,
            purpose=batch.purpose,data_origin=source_spec.data_origin,
            commercial_demo_authorized=source_spec.commercial_demo_authorized,
            frame_sequence=batch.frame_sequence,received_at=batch.received_at,approaches=tuple(result))
