import io
import zipfile
import pytest
from src.validation import field_annotation as a,field_jaad_range as j,field_hardware_observation as h
from src.benchmarking.pimcat_c3_study import COMMON

def test_private_html_no_prelabels():
    text=a.render({"decoded_pixel_sha256":"a"*64},["AA=="]*40)
    assert "__PRIVATE_PAYLOAD__" not in text and '"boxes":null' in text
    assert text.count('"reviewed":false')==len(COMMON)
    assert "connect-src 'none'" in text and "rows.every(r=>r.reviewed)" in text
    with pytest.raises(ValueError):a.render({"decoded_pixel_sha256":"a"*64},[])

class Response(io.BytesIO):
    def __init__(self,data,start,end,total,status=206,tag='"stable"'):
        super().__init__(data);self.status=status;self.headers={"Content-Range":f"bytes {start}-{end}/{total}","ETag":tag}
    def geturl(self):return j.URL

class Client:
    def __init__(self,data,status=206):self.data=data;self.status=status;self.tag='"stable"'
    def open(self,req,timeout):
        start,end=map(int,req.get_header("Range")[6:].split("-"))
        return Response(self.data[start:end+1],start,end,len(self.data),self.status,self.tag)

def test_range_and_exact_selection():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        for clip in j.CLIPS:z.writestr("clips/"+clip+".mp4",b"fixture")
        z.writestr("other.mp4",b"not selected")
    client=Client(buf.getvalue())
    with j.RangeFile(client) as remote,zipfile.ZipFile(remote) as z:
        assert set(j.select(z))==set(j.CLIPS)
    with pytest.raises(ValueError):j.RangeFile(Client(buf.getvalue(),200))
    remote=j.RangeFile(Client(buf.getvalue()),budget=2)
    with pytest.raises(ValueError):remote.read(3)
    client=Client(buf.getvalue());remote=j.RangeFile(client);client.tag='"changed"'
    with pytest.raises(ValueError):remote.read(1)

def test_duplicate_selection_and_no_receipt(tmp_path):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        for clip in j.CLIPS:z.writestr(clip+".mp4",b"fixture")
        z.writestr("duplicate/video_0005.mp4",b"x")
    with zipfile.ZipFile(buf) as z:
        with pytest.raises(ValueError):j.select(z)
    with pytest.raises(ValueError):j.acquire({},tmp_path,tmp_path/"out")

def rows():
    result=[]
    for i in range(3):
        x={"recent":True,"frames":i*5,"restarts":0,"session_overwrites":i,
           "decode_receive_ms":1.,"latest_inference_ms":2.,"inferred_at":"same",
           "inference_frame":1,"model_sha256":"a"*64,"global_processed":i,"global_discarded":0}
        result.append(dict(t=float(i),capture=x,resource=dict(cpu_usage_usec=i*500000,memory_current_bytes=100),http_ms=1.))
    return result

def test_benchmark_denominator_and_unknown():
    r=h.summarize(rows(),"LAB","fixture",1)
    assert r["sustained_capture_fps"]==5 and r["cgroup_average_cpu_cores"]==.5
    assert r["distinct_latest_inference_ms"]["count"]==1 and r["source_dropped_frames"] is None and not r["pilot_ready"]
    x=rows();x[1]["capture"]=None
    assert h.summarize(x,"LAB","fixture",1)["sustained_capture_fps"] is None
    x=rows();x[-1]["capture"]["restarts"]=1
    assert h.summarize(x,"LAB","fixture",1)["sustained_capture_fps"] is None
    x=rows();x[-1]["capture"]["frames"]=0
    assert h.summarize(x,"LAB","fixture",1)["sustained_capture_fps"] is None
