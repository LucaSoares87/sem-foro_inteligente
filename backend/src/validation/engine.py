import hashlib
import json
from collections import defaultdict
from src.validation.contracts import ClassMetric,EvaluationResult

def _canonical(value):
    return json.dumps(value,separators=(",",":"),sort_keys=True,ensure_ascii=False).encode()

def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()

def iou(a,b):
    ax1,ay1,ax2,ay2=a
    bx1,by1,bx2,by2=b
    ix=max(0,min(ax2,bx2)-max(ax1,bx1))
    iy=max(0,min(ay2,by2)-max(ay1,by1))
    inter=ix*iy
    union=(ax2-ax1)*(ay2-ay1)+(bx2-bx1)*(by2-by1)-inter
    return inter/union if union>0 else 0.0

def _safe_ratio(a,b,empty=0.0):
    return a/b if b else empty

def evaluate(request):
    gt_by=defaultdict(list)
    pred_by=defaultdict(list)
    labels=set()
    for obj in request.ground_truth.annotations:
        gt_by[(obj.frame_sequence,obj.label)].append(obj)
        labels.add(obj.label)
    for obj in request.predictions.annotations:
        pred_by[(obj.frame_sequence,obj.label)].append(obj)
        labels.add(obj.label)

    totals={label:{"tp":0,"fp":0,"fn":0} for label in labels}
    last_track={}
    identity_switches=0
    matched_with_track=0
    total_gt=len(request.ground_truth.annotations)

    for key in sorted(set(gt_by)|set(pred_by),key=lambda item:(item[0],item[1])):
        frame,label=key
        gt=gt_by[key]
        preds=sorted(pred_by[key],key=lambda item:item.confidence,reverse=True)
        unmatched=set(range(len(gt)))
        for pred in preds:
            candidates=[(iou(pred.xyxy,gt[index].xyxy),index) for index in unmatched]
            score,index=max(candidates,default=(0.0,None))
            if index is not None and score>=request.iou_threshold:
                unmatched.remove(index)
                totals[label]["tp"]+=1
                truth=gt[index]
                if pred.track_id is not None:
                    matched_with_track+=1
                    previous=last_track.get(truth.object_id)
                    if previous is not None and previous!=pred.track_id:
                        identity_switches+=1
                    last_track[truth.object_id]=pred.track_id
            else:
                totals[label]["fp"]+=1
        totals[label]["fn"]+=len(unmatched)

    class_metrics=[]
    for label in sorted(labels):
        values=totals[label]
        precision=_safe_ratio(values["tp"],values["tp"]+values["fp"],1.0 if values["tp"]==values["fp"]==0 else 0.0)
        recall=_safe_ratio(values["tp"],values["tp"]+values["fn"],1.0 if values["tp"]==values["fn"]==0 else 0.0)
        f1=_safe_ratio(2*precision*recall,precision+recall,0.0)
        class_metrics.append(ClassMetric(label=label,precision=precision,recall=recall,f1=f1,**values))
    macro_f1=sum(item.f1 for item in class_metrics)/len(class_metrics) if class_metrics else 1.0

    truth_counts={(x.line_id,x.direction,x.label):x.count for x in request.ground_truth.counts}
    pred_counts={(x.line_id,x.direction,x.label):x.count for x in request.predictions.counts}
    count_keys=set(truth_counts)|set(pred_counts)
    errors=[abs(truth_counts.get(key,0)-pred_counts.get(key,0)) for key in count_keys]
    count_mae=sum(errors)/len(errors) if errors else 0.0
    truth_total=sum(truth_counts.values())
    absolute_error=sum(errors)
    if truth_total==0:
        count_accuracy=1.0 if absolute_error==0 else 0.0
    else:
        count_accuracy=max(0.0,1-absolute_error/truth_total)

    tracking_recall=_safe_ratio(matched_with_track,total_gt,1.0 if total_gt==0 else 0.0)
    switch_rate=_safe_ratio(identity_switches,matched_with_track,0.0)
    t=request.thresholds
    passed=(macro_f1>=t.detection_macro_f1 and tracking_recall>=t.tracking_match_recall
            and switch_rate<=t.max_identity_switch_rate and count_accuracy>=t.count_accuracy)

    input_dump=request.model_dump(mode="json")
    input_sha=_sha(input_dump)
    body={
        "schema_version":1,"dataset_id":request.manifest.dataset_id,"origin":request.manifest.origin,
        "input_sha256":input_sha,"iou_threshold":request.iou_threshold,
        "per_class":[item.model_dump(mode="json") for item in class_metrics],
        "detection_macro_f1":macro_f1,"tracking_match_recall":tracking_recall,
        "identity_switches":identity_switches,"identity_switch_rate":switch_rate,
        "count_mae":count_mae,"count_accuracy":count_accuracy,
        "meets_supplied_thresholds":passed,
        "operationally_validated":False,"physical_actuation":False,
    }
    body["result_sha256"]=_sha(body)
    return EvaluationResult.model_validate(body)
