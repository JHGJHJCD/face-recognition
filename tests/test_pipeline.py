"""בדיקה מקצה לקצה בלי ממשק: טעינה, סריקת תמונות, קיבוץ, רישום, התאמה, נוכחות. מסד נתונים זמני."""
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database, cluster_embeddings  # noqa: E402
from core.engine import FaceEngine  # noqa: E402
from core.utils import IMAGE_EXT, imread  # noqa: E402

root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~\\Pictures")
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 60

t = time.time()
eng = FaceEngine()
print(f"load {time.time() - t:.1f}s  device={eng.device}  rec={eng.rec_name}")
db = Database(eng.rec_name, os.path.join(tempfile.mkdtemp(), "t.db"))

files = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if os.path.splitext(f)[1].lower() in IMAGE_EXT][:limit]
t = time.time()
embs = []
for p in files:
    img = imread(p, 1920)
    if img is None:
        continue
    faces = [f for f in eng.detect(img, 0.55) if f.size >= 50]
    eng.embed(img, faces)
    db.save_photo(p, os.path.getmtime(p), [(f.bbox, f.det, f.emb, b"", None, 0.0) for f in faces])
    embs += [f.emb for f in faces]
dt = time.time() - t
print(f"{len(files)} photos, {len(embs)} faces in {dt:.1f}s ({dt / max(1, len(files)):.2f}s/photo)")

groups = cluster_embeddings(embs, 0.5, 3)
print("clusters:", [len(g) for g in groups][:12])
assert groups, "no clusters found"
g = groups[0]
pid = db.add_person("בדיקה")
for i in g[:4]:
    db.add_sample(pid, embs[i])
hits = [db.match(e, 0.40) for e in embs]
inside = sum(1 for i in g if hits[i][0] == pid)
outside = sum(1 for i, h in enumerate(hits) if h[0] == pid and i not in set(g))
print(f"enrolled 4 samples -> matched {inside}/{len(g)} of the cluster, {outside} matches outside it")
E = np.stack(embs)
print(f"rematch rows: {db.rematch_photos(0.40)}  photos_of: {len(db.photos_of(pid))}")
assert db.mark_seen(pid, 5) is True and db.mark_seen(pid, 5) is False
print("attendance rows:", len(db.attendance(0, time.time() + 1)))
print("OK")
