from statistics import mean

MIN_WINDOWS=12
MAX_WINDOWS=60

def estimate(windows,line_id,direction):
    """One-minute passage-rate baseline with chronological walk-forward errors."""
    if direction not in {"negative_to_positive","positive_to_negative"}:
        raise ValueError("invalid direction")
    def abstain(reason):
        return {"state":"insufficient_data","reason":reason,"operationally_validated":False}
    values=[]
    previous=None
    for w in windows[-MAX_WINDOWS:]:
        if previous is not None and (w.analytics_epoch!=previous.analytics_epoch or
            w.source_id!=previous.source_id or w.geometry_sha256!=previous.geometry_sha256 or
            w.model_sha256!=previous.model_sha256 or w.purpose!=previous.purpose or
            w.start_sequence!=previous.end_sequence or w.started_at!=previous.ended_at):
            values=[]
        previous=w
        line=next((l for l in w.lines if l.line_id==line_id),None)
        if line is None or w.limited_intervals or w.skipped_frames or w.sampled_intervals<30:
            values=[]
            continue
        values.append(getattr(line,direction)*60/w.duration_seconds)
    if len(values)<MIN_WINDOWS:
        return abstain("insufficient_contiguous_quality_windows")
    errors=[abs(values[i]-mean(values[i-3:i])) for i in range(3,len(values))]
    baseline=[abs(values[i]-values[i-1]) for i in range(3,len(values))]
    mae=mean(errors)
    naive_mae=mean(baseline)
    use_mean=mae<=naive_mae
    selected=errors if use_mean else baseline
    prediction=mean(values[-3:]) if use_mean else values[-1]
    spread=sorted(selected)[min(len(selected)-1,int(.9*len(selected)))]
    return {"state":"experimental","method":"mean_last_3" if use_mean else "persistence",
        "horizon_seconds":60,"unit":"observed_passages_per_minute",
        "estimate":prediction,"empirical_error_band":[max(0,prediction-spread),prediction+spread],
        "mae_mean_last_3":mae,"mae_persistence":naive_mae,
        "backtest_samples":len(errors),"quality_windows":len(values),
        "anomaly_candidate":abs(values[-1]-mean(values[-4:-1]))>max(1,2*mae),
        "operationally_validated":False}
