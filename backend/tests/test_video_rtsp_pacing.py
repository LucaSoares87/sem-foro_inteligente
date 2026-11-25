"""Regression: live input consumption and JPEG emission are independent."""
import io
from types import SimpleNamespace
import cv2
import numpy as np
from src.video import worker
from src.video.protocol import HEADER

def test_rtsp_drains_native_10hz_and_emits_5hz(monkeypatch):
    class Capture:
        n=0
        released=False
        def open(self,*a):return True
        def get(self,*a):return 10
        def set(self,*a):return False
        def read(self):
            self.n+=1
            if self.n>10:return False,None
            clock.ns=self.n*100_000_000
            return True,np.zeros((24,32,3),dtype=np.uint8)
        def release(self):self.released=True
    cap=Capture()
    clock=SimpleNamespace(ns=0)
    sleeps=[]
    monkeypatch.setattr(worker,"time",SimpleNamespace(monotonic=lambda:clock.ns/1e9,monotonic_ns=lambda:clock.ns,sleep=sleeps.append))
    stream=io.BytesIO()
    monkeypatch.setattr(worker,"sys",SimpleNamespace(stdout=SimpleNamespace(buffer=stream)))
    monkeypatch.setattr(cv2,"VideoCapture",lambda:cap)
    assert worker.run({"kind":"rtsp","locator":"rtsp://127.0.0.1/lab","fps":5})==3
    assert cap.n==11 and cap.released and sleeps==[]
    stream.seek(0);timestamps=[]
    while header:=stream.read(HEADER.size):
        width,height,sequence,decoded,size=HEADER.unpack(header)
        assert (width,height)==(32,24)
        assert sequence==len(timestamps)+1
        timestamps.append(decoded)
        assert len(stream.read(size))==size
    assert timestamps==[100_000_000,300_000_000,500_000_000,700_000_000,900_000_000]
