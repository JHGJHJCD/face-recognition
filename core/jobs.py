"""עבודות רקע: סריקת תיקיות תמונות וסריקת סרטוני וידאו."""
import os

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from .db import cluster_embeddings
from .utils import IMAGE_EXT, crop_square, imread, jpg_bytes, short_path


def enroll_from_image(engine, img):
    """מחזיר את הפנים הגדולות ביותר בתמונה (עם וקטור זהות) או None."""
    faces = engine.detect(img, 0.5)
    if not faces:
        return None
    engine.embed(img, faces[:1])
    return faces[0]


class PhotoScanWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_scan = pyqtSignal(int, int)   # תמונות חדשות, פנים

    def __init__(self, engine, db, settings, folder):
        super().__init__()
        self.engine, self.db, self.st, self.folder = engine, db, settings, folder
        self.stop_flag = False

    def run(self):
        files = []
        for d, _, fs in os.walk(self.folder):
            for f in fs:
                if os.path.splitext(f)[1].lower() in IMAGE_EXT:
                    files.append(os.path.join(d, f))
        new = nfaces = 0
        thr = self.st["threshold"]

        def fetch(path):
            """רץ בחוטי רקע: קריאה ופענוח של התמונה בזמן שהמאיץ הגרפי עסוק בקודמת."""
            try:
                mtime = os.path.getmtime(path)
                if self.db.photo_known(path, mtime):
                    return mtime, None
                return mtime, imread(path, 1920)
            except Exception:
                return 0, None

        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(3)
        ahead = {}
        for i, path in enumerate(files):
            if self.stop_flag:
                break
            for p in files[i:i + 6]:
                if p not in ahead:
                    ahead[p] = pool.submit(fetch, p)
            self.progress.emit(i + 1, len(files), path)
            try:
                mtime, img = ahead.pop(path).result()
                if img is None:
                    continue
                faces = [f for f in self.engine.detect(img, 0.55) if f.size >= 36]
                self.engine.embed(img, faces, tta=False)
                # מדידה כפולה (תמונה + ראי) רק לפנים גבוליות — חוסך כמעט חצי מזמן ההטמעה
                edge = [f for f in faces if thr - 0.12 <= self.db.match(f.emb, thr)[1] < thr + 0.15]
                self.engine.embed(img, edge, tta=True)
                rows = []
                for f in faces:
                    pid, sim = self.db.match(f.emb, thr)
                    rows.append((f.bbox, f.det, f.emb, jpg_bytes(crop_square(img, f.bbox, size=112), 85), pid, sim))
                self.db.save_photo(path, mtime, rows)
                new += 1
                nfaces += len(rows)
            except Exception as e:
                print("photo error:", path, e)
        pool.shutdown(wait=False, cancel_futures=True)
        self.finished_scan.emit(new, nfaces)


class VideoScanWorker(QThread):
    progress = pyqtSignal(int, object)      # אחוזים, פריים לתצוגה מקדימה (או None)
    finished_scan = pyqtSignal(object)      # {"people": [...], "duration": שניות} | {"error": ...}

    def __init__(self, engine, db, settings, path):
        super().__init__()
        self.engine, self.db, self.st, self.path = engine, db, settings, path
        self.stop_flag = False

    def run(self):
        cap = cv2.VideoCapture(short_path(self.path))
        if not cap.isOpened():
            self.finished_scan.emit({"error": "לא הצלחתי לפתוח את קובץ הווידאו."})
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        step = max(0.2, float(self.st["video_step"]))
        every = max(1, int(round(fps * step)))
        seen = {}                 # pid -> [(זמן, דמיון)]
        best = {}                 # pid -> (דמיון, thumb)
        unk_embs, unk_meta = [], []
        idx = 0
        while not self.stop_flag:
            if not cap.grab():
                break
            if idx % every == 0:
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    if max(frame.shape[:2]) > 1920:
                        s = 1920 / max(frame.shape[:2])
                        frame = cv2.resize(frame, None, fx=s, fy=s)
                    t = idx / fps
                    faces = [f for f in self.engine.detect(frame, 0.55) if f.size >= 40]
                    self.engine.embed(frame, faces)
                    for f in faces:
                        pid, sim = self.db.match(f.emb, self.st["threshold"])
                        if pid is not None:
                            seen.setdefault(pid, []).append((t, sim))
                            if pid not in best or sim > best[pid][0]:
                                best[pid] = (sim, jpg_bytes(crop_square(frame, f.bbox, size=112)))
                        elif f.size >= 60 and f.det > 0.65:
                            unk_embs.append(f.emb)
                            unk_meta.append((t, jpg_bytes(crop_square(frame, f.bbox, size=112)), f.size * f.frontal))
                    self.progress.emit(int(idx * 100 / total), frame if (idx // every) % 3 == 0 else None)
            idx += 1
        cap.release()

        def ranges(times):
            out, start, prev = [], times[0], times[0]
            for t in times[1:]:
                if t - prev > step * 3.5:
                    out.append((start, prev + step))
                    start = t
                prev = t
            out.append((start, prev + step))
            return out

        people = []
        for pid, hits in seen.items():
            times = sorted(t for t, _ in hits)
            r = ranges(times)
            people.append({"name": self.db.names.get(pid, "?"), "thumb": best[pid][1], "ranges": r,
                           "total": sum(b - a for a, b in r), "sim": float(np.mean([s for _, s in hits])), "known": True})
        people.sort(key=lambda p: -p["total"])
        for n, grp in enumerate(cluster_embeddings(unk_embs, 0.45, min_size=2), 1):
            times = sorted(unk_meta[i][0] for i in grp)
            r = ranges(times)
            top = max(grp, key=lambda i: unk_meta[i][2])
            people.append({"name": f"לא מוכר {n}", "thumb": unk_meta[top][1], "ranges": r, "total": sum(b - a for a, b in r),
                           "sim": 0.0, "known": False, "embs": [unk_embs[i] for i in sorted(grp, key=lambda i: -unk_meta[i][2])[:8]],
                           "thumbs": [unk_meta[i][1] for i in sorted(grp, key=lambda i: -unk_meta[i][2])[:8]]})
        self.finished_scan.emit({"people": people, "duration": idx / fps, "stopped": self.stop_flag})
