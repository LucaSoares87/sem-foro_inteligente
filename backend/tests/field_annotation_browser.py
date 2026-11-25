"""Real Chromium regression with synthetic frames only, never C3 reference evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import cv2
import numpy as np
from playwright.sync_api import sync_playwright,expect
from src.validation import field_annotation as a
from src.validation.io import sha256_file
from src.benchmarking.pimcat_c3_study import COMMON

def main():
    out=Path("/tmp/fr-b-browser");out.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);video=root/"fixture.mkv"
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*"FFV1"),30,(1280,720))
        assert writer.isOpened()
        pixels=hashlib.sha256()
        for i in range(240):
            img=np.zeros((720,1280,3),np.uint8)
            img[:]=((i%100)+30,60,80)
            cv2.rectangle(img,(240,160),(420,530),(160,220,240),-1)
            cv2.putText(img,"SYNTHETIC "+str(i+1),(20,60),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
            pixels.update(img.tobytes());writer.write(img)
        writer.release()
        pre=dict(frames=240,fps=30,derived_sha256=sha256_file(video),decoded_pixel_sha256=pixels.hexdigest())
        images=a.frames(video,pre);assert len(images)==40
        for key in ("derived_sha256","decoded_pixel_sha256"):
            try:a.frames(video,{**pre,key:"0"*64})
            except ValueError:pass
            else:raise AssertionError("altered preflight accepted")
        a.prepare(video,pre,root/"private","SYNTHETIC TEST ONLY")
        assert (root/"private/a/annotation.html").read_bytes()==(root/"private/b/annotation.html").read_bytes()
        errors=[];requests=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
            page=browser.new_page(viewport={"width":1280,"height":900},accept_downloads=True)
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.on("request",lambda r:requests.append(r.url) if r.url.startswith(("http:","https:")) else None)
            page.goto((root/"private/a/annotation.html").as_uri())
            expect(page.locator("#review")).to_be_enabled()
            expect(page.locator("#export")).to_be_disabled()
            page.locator("#annotator").fill("SYNTHETIC_UI_TEST_NOT_HUMAN")
            box=page.locator("canvas").bounding_box()
            page.mouse.move(box["x"]+box["width"]*.2,box["y"]+box["height"]*.2)
            page.mouse.down();page.mouse.move(box["x"]+box["width"]*.4,box["y"]+box["height"]*.6,steps=8);page.mouse.up()
            expect(page.locator("#status")).to_contain_text("1 caixas")
            page.locator("#review").click();page.locator("#undo").click()
            expect(page.locator("#status")).to_contain_text("não revisado")
            page.locator("#review").click()
            page.screenshot(path=str(out/"desktop-synthetic.png"))
            for i in range(1,40):
                page.locator("#next").click();expect(page.locator("#review")).to_be_enabled();page.locator("#review").click()
            expect(page.locator("#export")).to_be_enabled()
            with page.expect_download() as dl:page.locator("#export").click()
            target=root/"fixture-only.json";dl.value.save_as(target)
            r=json.loads(target.read_text());assert r["pixel_sha256"]==pre["decoded_pixel_sha256"]
            assert [x["frame"] for x in r["frames"]]==list(COMMON) and all(x["reviewed"] and x["boxes"]==[] for x in r["frames"])
            page.set_viewport_size({"width":390,"height":844});page.locator("#prev").click();expect(page.locator("#review")).to_be_enabled()
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2")
            page.screenshot(path=str(out/"mobile-synthetic.png"),full_page=True)
            assert not errors and not requests
            browser.close()
        (out/"report.json").write_text(json.dumps(dict(scope="synthetic_browser_fixture_not_c3_reference",frames_decoded=240,frames_selected=40,hash_mismatch_rejected=True,export_verified=True,desktop=True,mobile=True,network_requests=len(requests),page_errors=len(errors),human_acceptance="PENDING_HUMAN",physical_actuation=False),indent=2))
if __name__=="__main__":main()
