# SI-10A — CPU performance investigation (research)

Base: 4a5de35eecd9f00a51e3296bf300ee1d2375b3ff. SI-09F merged and post-merge CI 45515024887 passed. No production source, detector, tracking, geometry or operational confidence thresholds modified. No promotion or physical actuation.

## SI-09F evidence ledger
Run 45513126744; both holdout jobs succeeded.
- 07h08 artifact 14976248641, ZIP SHA-256 0a120cc8cf2fe1fcc11a925f84feac71dd4806e542397adf2e0fb0b68fb0d7b1, report 7922cdfd34121b341a7237c985b5892e398f49b5fda28415d91f653fdb7f9980; baseline/candidate at 30/15/10/5 FPS: 5/6, 4/4, 6/6, 1/1. Mean inference at 30 FPS 500.986 ms.
- 11h08 artifact 14976724021, ZIP SHA-256 2b4a7211112414eaee1cc0c666d0bf12bfc3ef9be973e1299ed6729d79ecd7fc, report 1c6889eeac8f835acab6a0254adb08ec238c127fc4a87462b18ec3ee5f30f91f; baseline/candidate: 4/14, 10/13, 11/11, 9/9. Mean inference at 30 FPS 515.918 ms.
- Both independent annotation gates BLOCKED_BY_INDEPENDENT_ANNOTATION; 68 missing keys per annotator per case, no accuracy metrics. Blinded packets: 14976926728 and 14976786903. Distinct time of same camera, not cross-camera. Preserve external copies before artifact expiration. Candidate not promoted.

## Hypothesis and fixed method
The existing YoloDetector explicitly calls cv2.setNumThreads(1), a plausible performance constraint, not yet a demonstrated root cause. Test 1/2/4 threads if allowed by logical cores, CPU affinity and readable cgroup v2 quota; skip configurations exceeding detected budget. Use one process and the exact existing pinned YOLOX-S detector; override OpenCV thread setting only in the offline experiment after detector initialization. No change to production defaults. Restore prior thread setting on exit.

Use the two exact SI-09F source hashes and verify the decoded hash of all 960 frames of each registered native span. Profile 32 fixed frames per case, source indices 1,31,...931 (zero-based); no selection by model output. Forward and reverse configuration order, two trials per available thread count, warm-up three frames before each trial. Same input and JPEG quality 90; measure JPEG encode/decode, detector preprocess/forward/postprocess and combined elapsed wall time. Capture CPU budget and software version. Excludes video decoding, subprocess IPC, tracking, queueing, API, I/O and multi-camera scheduling: NOT a real-time system benchmark.

Compare detections to the first single-thread trial on every sampled frame using class, one-to-one match, maximum normalized coordinate error <=0.0001 and confidence error <=0.0001. Parity means computational agreement, not accuracy. Candidate passes this microbenchmark only if all trial frames match baseline on both cases and relative median trial mean latency reduction >=10% on both. Report whether both worst-trial p95 values <=200 ms as an engineering target for 5 FPS, not evidence of live capacity. No automatic FPS recommendation, no runtime change, no accuracy promotion. Baseline repeat parity required. All thresholds fixed before execution.

## Next gates
Review results and regression CI. A promising thread count merits a separate real subprocess/load benchmark with latency, CPU/RAM, backpressure, skipped frames, per-camera fairness and recovery; actual target hardware validation remains necessary. Investigate ONNX Runtime or lighter models separately with provenance/licensing and independent accuracy gates. Adaptive FPS is not enabled. SI-09F calibration, independent references, F1/identity evaluation, X validation and SI-08B field acceptance remain blocked or pending.
