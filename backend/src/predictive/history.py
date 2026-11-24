from collections import defaultdict

def build_intersection_history(intersection_code, histories):
    """Build chart-ready observed series without combining cameras or epochs."""
    series=defaultdict(list)
    windows=0
    sources=[]
    for source_id,items in sorted(histories.items()):
        if items:
            sources.append(source_id)
        for window in items:
            if window.source_id!=source_id or window.intersection_code!=intersection_code:
                raise ValueError("history/source intersection mismatch")
            windows+=1
            quality="limited" if window.skipped_frames or window.limited_intervals else "observed"
            for line in window.lines:
                for direction in ("negative_to_positive","positive_to_negative"):
                    key=(source_id,line.line_id,direction)
                    series[key].append({
                        "ended_at":window.ended_at.isoformat(),
                        "observed_passages":getattr(line,direction),
                        "duration_seconds":window.duration_seconds,
                        "quality":quality,
                        "analytics_epoch":str(window.analytics_epoch),
                        "purpose":window.purpose,
                    })
    output=[]
    for (source_id,line_id,direction),points in sorted(series.items()):
        output.append({
            "source_id":source_id,
            "line_id":line_id,
            "direction":direction,
            "points":points,
        })
    return {
        "schema_version":1,
        "intersection_code":intersection_code,
        "state":"available" if output else "empty",
        "window_semantics":"observed_non_overlapping_approximately_60s",
        "aggregation_across_sources":False,
        "operationally_validated":False,
        "source_ids":sources,
        "windows":windows,
        "series":output,
    }
