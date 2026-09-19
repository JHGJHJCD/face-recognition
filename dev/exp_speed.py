"""ניסויי מהירות: (1) טעינה מ-IR שמור מול ONNX (2) הטמעה במקביל (AsyncInferQueue) (3) קריאת JPEG מוקטנת (4) קצב המצלמה הגולמי."""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import openvino as ov  # noqa: E402

from core.utils import IMAGE_EXT, MODELS_DIR  # noqa: E402

core = ov.Core()
cache = os.path.join(os.environ["LOCALAPPDATA"], "FaceID_ov_cache")
core.set_property({"CACHE_DIR": cache})
ir_dir = os.path.join(cache, "ir")
os.makedirs(ir_dir, exist_ok=True)
SHAPES = {"det_10g": [1, 3, 640, 640], "glintr100": [1, 3, 112, 112], "fairface": [1, 3, 224, 224], "emotion": [1, 3, 224, 224],
          "MiniFASNetV2": [1, 3, 80, 80], "MiniFASNetV1SE": [1, 3, 80, 80]}

# ---- 1. IR
for name, shape in SHAPES.items():
    xml = os.path.join(ir_dir, name + ".xml")
    if not os.path.exists(xml):
        with open(os.path.join(MODELS_DIR, name + ".onnx"), "rb") as f:
            m = core.read_model(model=f.read())
        m.reshape({m.inputs[0].any_name: shape})
        ov.save_model(m, xml, compress_to_fp16=True)
for rnd in (1, 2):
    t = time.perf_counter()
    nets = {n: core.compile_model(os.path.join(ir_dir, n + ".xml"), "GPU", {"PERFORMANCE_HINT": "LATENCY"}) for n in SHAPES}
    print("IR sequential load, round %d: %.2fs" % (rnd, time.perf_counter() - t))
t = time.perf_counter()
out = {}
ths = [threading.Thread(target=lambda n=n: out.__setitem__(n, core.compile_model(os.path.join(ir_dir, n + ".xml"), "GPU", {"PERFORMANCE_HINT": "LATENCY"}))) for n in SHAPES]
[x.start() for x in ths]; [x.join() for x in ths]
print("IR parallel load: %.2fs" % (time.perf_counter() - t))

# ---- 2. embedding throughput
rec = nets["glintr100"]
x = np.random.rand(1, 3, 112, 112).astype(np.float32)
ref = rec(x)[0].copy()
for _ in range(5):
    rec(x)
t = time.perf_counter()
for _ in range(40):
    rec(x)
print("embed sequential (LATENCY): %.1fms" % ((time.perf_counter() - t) / 40 * 1000))
for hint, jobs in (("THROUGHPUT", 0), ("LATENCY", 4)):
    cm = core.compile_model(os.path.join(ir_dir, "glintr100.xml"), "GPU", {"PERFORMANCE_HINT": hint})
    q = ov.AsyncInferQueue(cm, jobs)
    res = []
    q.set_callback(lambda req, _: res.append(req.get_output_tensor(0).data.copy()))
    for _ in range(8):
        q.start_async({0: x})
    q.wait_all()
    t = time.perf_counter()
    for _ in range(40):
        q.start_async({0: x})
    q.wait_all()
    print("embed async %s jobs=%d: %.1fms/face  maxdiff=%.4f" % (hint, len(q), (time.perf_counter() - t) / 40 * 1000, float(np.abs(res[-1] - ref).max())))
# batch model
with open(os.path.join(MODELS_DIR, "glintr100.onnx"), "rb") as f:
    mb = core.read_model(model=f.read())
mb.reshape({mb.inputs[0].any_name: [8, 3, 112, 112]})
t = time.perf_counter(); cb = core.compile_model(mb, "GPU", {"PERFORMANCE_HINT": "THROUGHPUT"}); print("compile batch8 %.1fs" % (time.perf_counter() - t))
xb = np.repeat(x, 8, 0)
cb(xb)
t = time.perf_counter()
for _ in range(6):
    cb(xb)
print("embed batch8: %.1fms/face" % ((time.perf_counter() - t) / 48 * 1000))

# ---- 3. JPEG read
root = os.path.expanduser("~\\Pictures")
files = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if f.lower().endswith((".jpg", ".jpeg"))][:30]
for flag, label in ((cv2.IMREAD_COLOR, "full"), (cv2.IMREAD_REDUCED_COLOR_2, "reduced/2")):
    t = time.perf_counter(); px = 0
    for p in files:
        im = cv2.imdecode(np.fromfile(p, np.uint8), flag)
        px += 0 if im is None else max(im.shape[:2])
    print("decode %-10s %.0fms/photo  avg max side %d" % (label, (time.perf_counter() - t) / len(files) * 1000, px / len(files)))

# ---- 4. camera
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if cap.isOpened():
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")); cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    for _ in range(10):
        cap.read()
    t = time.perf_counter(); n = 0
    while time.perf_counter() - t < 3:
        ok, fr = cap.read(); n += ok
    print("camera raw: %.1f fps  %s  mean brightness %.0f" % (n / 3, fr.shape if ok else None, fr.mean() if ok else 0))
    cap.release()
else:
    print("camera busy/unavailable")
