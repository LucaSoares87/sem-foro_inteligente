"""Read-only daily analytics report; never a controller or field acceptance gate."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.db import TrafficWindowRecord
from src.predictive.store import HistoryStore, HistoryIntegrityError
from src.archive.store import fingerprint

ZONE="America/Sao_Paulo"
MAX_SCAN=20000
MAX_SOURCES=32

def bounds(day):
    z=ZoneInfo(ZONE)
    start=datetime.combine(day,time.min,z).astimezone(timezone.utc)
    end=datetime.combine(day+timedelta(days=1),time.min,z).astimezone(timezone.utc)
    return start,end

def unavailable():
    return {k:{"value":None,"reason":reason} for k,reason in {
        "pedestrian_wait":"independent_C3_reference_blocked",
        "pedestrian_crossings":"no_validated_pedestrian_daily_contract",
        "physical_speed":"metric_calibration_not_validated",
        "trip_time":"no_validated_corridor_attribution",
        "queue_wait":"no_validated_daily_wait_population",
        "network_criticity":"no_validated_network_observations",
        "camera_availability":"coverage_is_not_camera_uptime",
        "counterfactual_improvement":"no_matched_field_comparator",
    }.items()}

def daily_report(intersection,day,histories):
    start,end=bounds(day);seconds=(end-start).total_seconds()
    groups=defaultdict(list);boundaries=0;accepted=0
    sources=[]
    for source,windows in sorted(histories.items()):
        found=0;seen=set()
        for w in windows:
            if w.source_id!=source or w.intersection_code!=intersection:
                raise ValueError("history scope mismatch")
            a,b=w.started_at,w.ended_at
            if b<=start or a>=end:continue
            if not a<b or w.start_sequence>w.end_sequence:
                raise ValueError("invalid window")
            if a<start or b>end:
                boundaries+=1;continue
            key=(str(w.analytics_epoch),w.start_sequence)
            if key in seen:raise ValueError("duplicate window")
            seen.add(key);found+=1;accepted+=1
            duration=(b-a).total_seconds()
            if abs(duration-w.duration_seconds)>1:raise ValueError("invalid duration")
            limited=bool(w.skipped_frames or w.limited_intervals)
            line_ids=set()
            for line in w.lines:
                if line.line_id in line_ids:raise ValueError("duplicate line")
                line_ids.add(line.line_id)
                for direction in ("negative_to_positive","positive_to_negative"):
                    k=(source,line.line_id,direction,str(w.analytics_epoch),w.geometry_sha256,w.model_sha256,w.purpose)
                    groups[k].append((a,b,getattr(line,direction),limited,w.start_sequence,w.end_sequence))
        sources.append({"source_id":source,"complete_windows":found})
    series=[]
    for key,points in sorted(groups.items()):
        points.sort(key=lambda p:p[0])
        for a,b in zip(points,points[1:]):
            if b[0]<a[1] or b[4]<a[5]:raise ValueError("overlapping series")
        observed=[p for p in points if not p[3]]
        limited=[p for p in points if p[3]]
        def stats(items):
            return {"windows":len(items),"seconds":sum((p[1]-p[0]).total_seconds() for p in items),
                    "passages":sum(p[2] for p in items) if items else None}
        obs,lim=stats(observed),stats(limited)
        total=obs["seconds"]+lim["seconds"]
        series.append(dict(zip(("source_id","line_id","direction","analytics_epoch","geometry_sha256","model_sha256","purpose"),key),
            observed=obs,limited=lim,coverage_fraction=total/seconds,unobserved_seconds=seconds-total,
            first_window_started_at=points[0][0].isoformat(),last_window_ended_at=points[-1][1].isoformat(),
            window_sha256=fingerprint({"windows":[[p[0].isoformat(),p[1].isoformat(),*p[2:]] for p in points]})))
    report={"schema_version":1,"date":day.isoformat(),"timezone":ZONE,"interval_start":start.isoformat(),"interval_end":end.isoformat(),
            "day_seconds":seconds,"intersection_code":intersection,"scope":"configured_sources_only",
            "origin":"observed_analytics_source_origin_unverified","state":"available" if series else "empty",
            "sources":sources,"complete_windows":accepted,"boundary_windows_excluded":boundaries,"series":series,
            "aggregation_across_sources":False,"extrapolated":False,"unique_vehicles":None,"network_total":None,
            "unavailable_metrics":unavailable(),"operationally_validated":False,"physical_actuation":False,
            "operational_decision":"abstain","candidate_promoted":False}
    return {**report,"report_sha256":fingerprint(report)}

def load_day(engine,intersection,day,source_ids):
    if len(source_ids)>MAX_SOURCES:raise HistoryIntegrityError("source limit")
    histories={s:[] for s in source_ids}
    if not source_ids:return daily_report(intersection,day,histories)
    # No date column/index exists. Bounded, integrity-checked scan; never silently truncate.
    # A future migration can add a timestamp index without changing this report contract.
    with Session(engine) as session:
        rows=session.scalars(select(TrafficWindowRecord).where(TrafficWindowRecord.source_id.in_(source_ids))
            .order_by(TrafficWindowRecord.id).limit(MAX_SCAN+1)).all()
        if len(rows)>MAX_SCAN:raise HistoryIntegrityError("daily_scan_limit")
        for row in rows:
            w=HistoryStore.decode(row)
            histories[w.source_id].append(w)
    return daily_report(intersection,day,histories)
