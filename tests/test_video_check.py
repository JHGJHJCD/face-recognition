"""בדיקת "בדיקת סרטון" (22/9/2026) בלי ממשק: בונה סרטון סינתטי מתמונות ב-Pictures, מריץ scan_video (זיהוי פנים + נשים/ילדות
עם אימות Gemini על פריימים), ואופציונלית בודק קישור יוטיוב דרך Gemini (--yt <קישור>) — הסרטון נצפה בצד של גוגל.
שימוש: test_video_check.py [תיקיית תמונות] [כמות] [--no-ai] [--yt קישור]"""
import os
import sys
import tempfile
import time

import cv2

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import ai  # noqa: E402
from core.db import Database, Settings  # noqa: E402
from core.jobs import ai_video_check, scan_video  # noqa: E402
from core.utils import IMAGE_EXT, fmt_time, imread  # noqa: E402

yt = sys.argv[sys.argv.index("--yt") + 1] if "--yt" in sys.argv else ""
args = [a for a in sys.argv[1:] if not a.startswith("--") and a != yt]
root = args[0] if args else os.path.expanduser("~\\Pictures")
limit = int(args[1]) if len(args) > 1 else 12
use_ai = "--no-ai" not in sys.argv

st = Settings()
gem = ai.GeminiClient() if use_ai else None
if gem is not None and not gem.available:
    gem = None
    print("אין מפתחות Gemini — בדיקה מקומית בלבד")

if yt:
    t = time.time()
    segs, summary = ai_video_check(gem, ai.youtube_url(yt), st["girl_age"])
    print(f"YouTube via Gemini: {len(segs)} segments in {time.time() - t:.0f}s · {summary}")
    for s in segs[:15]:
        print(f"  {fmt_time(s['start'])}–{fmt_time(s['end'])}  {s['kind']:<5} גיל~{s['age']}  קטנה={s['small']}  {s['ai']}")
    if not args:
        sys.exit(0)

# --- סרטון סינתטי: כל תמונה 2 שניות ב-10fps, 640x480 ---
files = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if os.path.splitext(f)[1].lower() in IMAGE_EXT][:limit]
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "test.mp4")
vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 480))
for p in files:
    img = imread(p, 640)
    if img is None:
        continue
    canvas = cv2.resize(img, (640, 480))
    for _ in range(20):
        vw.write(canvas)
vw.release()
print(f"video: {len(files)} photos → {path}")

from core.engine import FaceEngine  # noqa: E402
t = time.time()
eng = FaceEngine()
print(f"load {time.time() - t:.1f}s")
db = Database(eng.rec_name, os.path.join(tmp, "t.db"))
t = time.time()
res = scan_video(eng, db, st, path, lambda pct, fr, msg: msg and print("  ", msg), lambda: False, gem)
assert "error" not in res, res
print(f"scan {time.time() - t:.1f}s · duration {fmt_time(res['duration'])} · people {len(res['people'])} · female segments {len(res['females'])}")
for s in res["females"]:
    assert s["start"] <= s["end"] and s["kind"] in ("אישה", "נערה", "ילדה") and isinstance(s["thumb"], bytes)
    print(f"  {fmt_time(s['start'])}–{fmt_time(s['end'])}  {s['kind']:<5} גיל~{s['age']}  קטנה={s['small']}  n={s['n']}  {s['ai']}")
for p in res["people"]:
    print("  person:", p["name"], [(fmt_time(a), fmt_time(b)) for a, b in p["ranges"]])
print("OK")
