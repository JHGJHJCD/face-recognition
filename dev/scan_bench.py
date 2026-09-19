"""מודד את מהירות סריקת התמונות האמיתית (PhotoScanWorker) על מסד נתונים זמני. שימוש: scan_bench.py [תיקייה] [כמות]"""
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.db import Database, Settings  # noqa: E402
from core.engine import FaceEngine  # noqa: E402
from core.jobs import PhotoScanWorker  # noqa: E402
from core.utils import IMAGE_EXT  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~\\Pictures")
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 40
files = [os.path.join(d, f) for d, _, fs in os.walk(src) for f in fs if os.path.splitext(f)[1].lower() in IMAGE_EXT][:limit]
tmp = tempfile.mkdtemp()
for i, f in enumerate(files):
    shutil.copy2(f, os.path.join(tmp, f"{i:03d}{os.path.splitext(f)[1]}"))
eng = FaceEngine()
db = Database(eng.rec_name, os.path.join(tempfile.mkdtemp(), "t.db"))
w = PhotoScanWorker(eng, db, Settings(), tmp)
res = []
w.finished_scan.connect(lambda n, f: res.append((n, f)))
t = time.perf_counter()
w.run()
dt = time.perf_counter() - t
n, f = db.photo_stats()
print("scanned %d photos, %d faces in %.1fs = %.0f ms/photo" % (n, f, dt, dt / max(1, n) * 1000))
shutil.rmtree(tmp, ignore_errors=True)
