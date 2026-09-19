"""מדידת מהירות: טעינת כל מודל, זמן לכל שלב בניתוח, קריאת תמונות. שימוש: bench.py [תיקיית תמונות] [כמות]"""
import os
import sys
import time

T0 = time.perf_counter()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cv2  # noqa: E402
import numpy as np  # noqa: E402

print("import cv2/numpy %.2fs" % (time.perf_counter() - T0))
t = time.perf_counter()
import openvino as ov  # noqa: E402,F401

print("import openvino %.2fs" % (time.perf_counter() - t))
from core import engine as E  # noqa: E402
from core.utils import IMAGE_EXT, imread  # noqa: E402

_orig = E.Net.__init__


def timed(self, name, *a, **k):
    t = time.perf_counter()
    _orig(self, name, *a, **k)
    print("  load %-22s %.2fs" % (name, time.perf_counter() - t))


E.Net.__init__ = timed
t = time.perf_counter()
eng = E.FaceEngine()
print("engine total %.2fs  device=%s" % (time.perf_counter() - t, eng.device))

root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~\\Pictures")
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 25
files = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if os.path.splitext(f)[1].lower() in IMAGE_EXT][:limit]
acc = {"read": 0.0, "detect": 0.0, "embed_tta": 0.0, "embed": 0.0, "age": 0.0, "emotion": 0.0, "live": 0.0}
nf = 0
for p in files:
    t = time.perf_counter(); img = imread(p, 1920); acc["read"] += time.perf_counter() - t
    if img is None:
        continue
    t = time.perf_counter(); faces = [f for f in eng.detect(img, 0.55) if f.size >= 36]; acc["detect"] += time.perf_counter() - t
    nf += len(faces)
    t = time.perf_counter(); eng.embed(img, faces); acc["embed_tta"] += time.perf_counter() - t
    t = time.perf_counter(); eng.embed(img, faces, tta=False); acc["embed"] += time.perf_counter() - t
    for f in faces[:2]:
        t = time.perf_counter(); eng.gender_age(img, f); acc["age"] += time.perf_counter() - t
        t = time.perf_counter(); eng.emotion(img, f); acc["emotion"] += time.perf_counter() - t
        t = time.perf_counter(); eng.liveness(img, f); acc["live"] += time.perf_counter() - t
n = max(1, len(files))
print("%d photos, %d faces" % (len(files), nf))
print("per photo: read %.0fms  detect %.0fms" % (acc["read"] / n * 1000, acc["detect"] / n * 1000))
print("per face : embed+flip %.0fms  embed %.0fms" % (acc["embed_tta"] / max(1, nf) * 1000, acc["embed"] / max(1, nf) * 1000))
k = max(1, min(nf, 2 * len(files)))
print("per face : age %.0fms  emotion %.0fms  liveness(x2) %.0fms" % (acc["age"] / k * 1000, acc["emotion"] / k * 1000, acc["live"] / k * 1000))
