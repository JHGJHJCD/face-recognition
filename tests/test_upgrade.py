"""בדיקת השדרוג: איכות וקטור (norm), השפעת תמונת-ראי, התאמה עם מרווח, סיכומי נוכחות. מסד נתונים זמני."""
import os
import sys
import tempfile
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database  # noqa: E402
from core.engine import FaceEngine, enhance_low_light  # noqa: E402
from core.utils import IMAGE_EXT, imread  # noqa: E402

root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~\\Pictures")
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 40
eng = FaceEngine()
files = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if os.path.splitext(f)[1].lower() in IMAGE_EXT][:limit]
norms, blur_norms, diffs, t_tta = [], [], [], []
for p in files:
    img = imread(p, 1920)
    if img is None:
        continue
    faces = [f for f in eng.detect(img, 0.55) if f.size >= 60][:3]
    if not faces:
        continue
    t = time.time()
    eng.embed(img, faces)
    t_tta.append((time.time() - t) / len(faces))
    e_tta = [f.emb.copy() for f in faces]
    norms += [f.norm for f in faces]
    eng.embed(img, faces, tta=False)
    diffs += [float(a @ f.emb) for a, f in zip(e_tta, faces)]
    small = cv2.GaussianBlur(img, (0, 0), 6)
    eng.embed(small, faces)
    blur_norms += [f.norm for f in faces]
print(f"faces={len(norms)}  embed+flip {np.mean(t_tta) * 1000:.0f}ms/face")
print("norm sharp: min %.1f p10 %.1f median %.1f" % (min(norms), np.percentile(norms, 10), np.median(norms)))
print("norm blurred: median %.1f max %.1f" % (np.median(blur_norms), max(blur_norms)))
print("cos(tta, plain): min %.3f mean %.3f" % (min(diffs), np.mean(diffs)))

dark = (imread(files[0], 1280) * 0.15).astype(np.uint8)
print("low light: mean %.0f -> %.0f" % (dark.mean(), enhance_low_light(dark).mean()))

db = Database("t", os.path.join(tempfile.mkdtemp(), "t.db"))
rng = np.random.default_rng(1)
a, b = rng.normal(size=512).astype(np.float32), rng.normal(size=512).astype(np.float32)
a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
b = b - (a @ b) * a
b /= np.linalg.norm(b)
pa, pb = db.add_person("אלף"), db.add_person("בית")
db.add_sample(pa, a)
db.add_sample(pb, b)
n = rng.normal(size=512).astype(np.float32)
n = n - (a @ n) * a - (b @ n) * b          # רעש ניצב לשניהם → דמיון זהה (~0.45) לשני האנשים
mid = a + b + 1.7 * n / np.linalg.norm(n)
mid /= np.linalg.norm(mid)
print("match a:", db.match(a, 0.4)[0] == pa, " ambiguous->None:", db.match(mid, 0.4)[0] is None)
day = time.mktime(time.strptime("2026-09-16 00:00", "%Y-%m-%d %H:%M"))
db.mark_seen(pa, 5, day + 9 * 3600)
db.mark_seen(pa, 5, day + 9 * 3600 + 200)
db.mark_seen(pa, 5, day + 13 * 3600)
s = db.daily_summary(day, day + 86400, "08:30")
print("summary:", [(d["name"], d["visits"], int(d["total"]), d["late"]) for d in s], " absent:", db.absent(day, day + 86400))
db.add_ai_note("scene", "אלף", "בדיקה")
print("notes:", len(db.ai_notes(0)))
