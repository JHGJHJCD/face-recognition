"""טעינת המודלים בתהליך נקי: exp_load.py onnx|ir seq|par"""
import os
import sys
import threading
import time

T0 = time.perf_counter()
import openvino as ov  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")
kind, mode = sys.argv[1], sys.argv[2]
core = ov.Core()
cache = os.path.join(os.environ["LOCALAPPDATA"], "FaceID_ov_cache")
core.set_property({"CACHE_DIR": cache})
SHAPES = {"det_10g": [1, 3, 640, 640], "glintr100": [1, 3, 112, 112], "fairface": [1, 3, 224, 224], "emotion": [1, 3, 224, 224],
          "MiniFASNetV2": [1, 3, 80, 80], "MiniFASNetV1SE": [1, 3, 80, 80]}
times = {}


def load(n):
    t = time.perf_counter()
    if kind == "ir":
        core.compile_model(os.path.join(cache, "ir", n + ".xml"), "GPU", {"PERFORMANCE_HINT": "LATENCY"})
    else:
        with open(os.path.join(MODELS, n + ".onnx"), "rb") as f:
            m = core.read_model(model=f.read())
        m.reshape({m.inputs[0].any_name: SHAPES[n]})
        core.compile_model(m, "GPU", {"PERFORMANCE_HINT": "LATENCY"})
    times[n] = time.perf_counter() - t


t = time.perf_counter()
if mode == "par":
    ths = [threading.Thread(target=load, args=(n,)) for n in SHAPES]
    [x.start() for x in ths]
    [x.join() for x in ths]
else:
    for n in SHAPES:
        load(n)
print(kind, mode, "total %.2fs (import %.2fs)" % (time.perf_counter() - t, t - T0), {k: round(v, 2) for k, v in times.items()})
