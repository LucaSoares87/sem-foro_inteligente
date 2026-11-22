from math import hypot

def foot(box):
    x1,y1,x2,y2=box
    return ((x1+x2)/2,y2)

def contains(box,p):
    x1,y1,x2,y2=box
    return x1<=p[0]<=x2 and y1<=p[1]<=y2

def clip(box,roi):
    x1,y1,x2,y2=box
    a,b,c,d=roi
    out=(max(x1,a),max(y1,b),min(x2,c),min(y2,d))
    return out if out[0]<out[2] and out[1]<out[3] else None

def union_area(boxes):
    if not boxes:
        return 0.0
    xs=sorted({x for a,b,c,d in boxes for x in (a,c)})
    area=0.0
    for left,right in zip(xs,xs[1:]):
        spans=sorted((b,d) for a,b,c,d in boxes if a<right and c>left)
        if not spans:
            continue
        low,high=spans[0]
        length=0.0
        for b,d in spans[1:]:
            if b>high:
                length+=high-low
                low,high=b,d
            else:
                high=max(high,d)
        area+=(right-left)*(length+high-low)
    return area

def image_coverage(roi,boxes):
    clipped=[c for b in boxes if (c:=clip(b,roi)) is not None]
    area=(roi[2]-roi[0])*(roi[3]-roi[1])
    return min(100.0,max(0.0,100*union_area(clipped)/area))

def distance(line,p):
    ax,ay=line.start
    dx,dy=line.end[0]-ax,line.end[1]-ay
    return (dx*(p[1]-ay)-dy*(p[0]-ax))/hypot(dx,dy)

def side(line,p):
    d=distance(line,p)
    return 1 if d>line.deadband else -1 if d<-line.deadband else 0

def crosses_segment(line,previous,current):
    a,b=distance(line,previous),distance(line,current)
    if a*b>=0:
        return False
    t=a/(a-b)
    x=previous[0]+t*(current[0]-previous[0])
    y=previous[1]+t*(current[1]-previous[1])
    dx,dy=line.end[0]-line.start[0],line.end[1]-line.start[1]
    u=((x-line.start[0])*dx+(y-line.start[1])*dy)/(dx*dx+dy*dy)
    return 0<=u<=1
