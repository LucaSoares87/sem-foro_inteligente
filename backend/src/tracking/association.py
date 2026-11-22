import numpy as np
from scipy.optimize import linear_sum_assignment

def iou(a,b):
    x1,y1,x2,y2=a
    u1,v1,u2,v2=b
    overlap=max(0,min(x2,u2)-max(x1,u1))*max(0,min(y2,v2)-max(y1,v1))
    union=max(0,x2-x1)*max(0,y2-y1)+max(0,u2-u1)*max(0,v2-v1)-overlap
    return overlap/union if union>0 else 0.0

def associate(tracks,detections,threshold):
    if not tracks or not detections:
        return [],list(range(len(tracks))),list(range(len(detections)))
    cost=np.full((len(tracks),len(detections)),1000.0)
    for i,track in enumerate(tracks):
        for j,det in enumerate(detections):
            if track.label==det.label:
                score=iou(track.predicted_box(),det.xyxy)
                if score>=threshold:
                    cost[i,j]=1-score
    rows,cols=linear_sum_assignment(cost)
    pairs=[(int(i),int(j)) for i,j in zip(rows,cols) if cost[i,j]<1000]
    matched_i={i for i,j in pairs}
    matched_j={j for i,j in pairs}
    return pairs,[i for i in range(len(tracks)) if i not in matched_i],[j for j in range(len(detections)) if j not in matched_j]
