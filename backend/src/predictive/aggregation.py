from src.analytics.contracts import LineMetric
from src.predictive.contracts import RegionAggregate, TrafficWindow

WINDOW_SECONDS=60
MAX_INTERVAL_SECONDS=2

class WindowAccumulator:
    """Non-overlapping observed intervals; gaps never become fabricated zero flow."""
    def __init__(self):
        self.previous=None
        self.reset()

    def reset(self,snapshot=None):
        self.start=self.previous=snapshot
        self.intervals=self.limited=self.skipped=0
        self.integrals={}
        self.peaks={r.region_id:r.confirmed_visible for r in snapshot.regions} if snapshot else {}

    @staticmethod
    def identity(s):
        return (s.source_id,s.intersection_code,s.analytics_epoch,s.geometry_sha256,s.model_sha256,s.purpose)

    def consume(self,s):
        p=self.previous
        if p is None or self.identity(p)!=self.identity(s):
            self.reset(s)
            return None
        dt=(s.received_at-p.received_at).total_seconds()
        delta=s.frame_sequence-p.frame_sequence
        skipped=s.skipped_frames-p.skipped_frames
        if (not 0<dt<=MAX_INTERVAL_SECONDS or delta<=0 or skipped<0 or
                s.discontinuities!=p.discontinuities or s.observed_batches!=p.observed_batches+1):
            self.reset(s)
            return None
        old_lines={l.line_id:l for l in self.start.lines}
        prev_lines={l.line_id:l for l in p.lines}
        if set(old_lines)!={l.line_id for l in s.lines} or set(prev_lines)!=set(old_lines) or any(
            l.negative_to_positive<prev_lines[l.line_id].negative_to_positive or
            l.positive_to_negative<prev_lines[l.line_id].positive_to_negative for l in s.lines):
            self.reset(s)
            return None
        old_regions={r.region_id:r for r in p.regions}
        if set(old_regions)!={r.region_id for r in s.regions}:
            self.reset(s)
            return None
        for r in s.regions:
            before=old_regions[r.region_id]
            acc=self.integrals.setdefault(r.region_id,[0.,0.])
            acc[0]+=dt*(before.confirmed_visible+r.confirmed_visible)/2
            acc[1]+=dt*(before.image_coverage_pct+r.image_coverage_pct)/2
            self.peaks[r.region_id]=max(self.peaks.get(r.region_id,0),r.confirmed_visible)
        self.intervals+=1
        self.skipped+=skipped
        self.limited+=int(bool(skipped or p.tentative_visible or p.lost_private or s.tentative_visible or s.lost_private))
        self.previous=s
        duration=(s.received_at-self.start.received_at).total_seconds()
        if duration<WINDOW_SECONDS:
            return None
        result=TrafficWindow(source_id=s.source_id,intersection_code=s.intersection_code,
            analytics_epoch=s.analytics_epoch,geometry_sha256=s.geometry_sha256,model_sha256=s.model_sha256,
            purpose=s.purpose,start_sequence=self.start.frame_sequence,end_sequence=s.frame_sequence,
            started_at=self.start.received_at,ended_at=s.received_at,duration_seconds=duration,
            sampled_intervals=self.intervals,skipped_frames=self.skipped,limited_intervals=self.limited,
            discontinuities_at_end=s.discontinuities,
            regions=tuple(RegionAggregate(region_id=k,mean_visible=min(100,v[0]/duration),
                peak_visible=self.peaks[k],mean_image_coverage_pct=min(100,v[1]/duration))
                for k,v in self.integrals.items()),
            lines=tuple(LineMetric(line_id=l.line_id,
                negative_to_positive=l.negative_to_positive-old_lines[l.line_id].negative_to_positive,
                positive_to_negative=l.positive_to_negative-old_lines[l.line_id].positive_to_negative)
                for l in s.lines))
        self.reset(s)
        return result
