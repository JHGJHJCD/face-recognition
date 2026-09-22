"""הגשר בין מנועי הזיהוי (core/) לממשק ה-HTML: שרת HTTP מקומי (127.0.0.1 בלבד, עם אסימון סודי בכתובת).

הממשק עצמו = webui/static (HTML/CSS/JS) בתוך חלון QtWebEngine. כל העבודה הכבדה נשארת ב-core/ בדיוק כמו קודם —
הדפדפן רק מצייר. פריימים של המצלמה נמשכים ב-/frame (JPEG + תוויות בכותרת), והכול השאר ב-/api/*.
"""
import base64
import json
import os
import queue
import secrets
import shutil
import sys
import tempfile
import threading
import time
import winsound
import zipfile
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFileDialog

from core import ai, reports, updater
from core.db import DEFAULTS, Database, Settings, cluster_embeddings
from core.jobs import PhotoScanWorker, VideoScanWorker, YouTubeWorker, enroll_from_image
from core.live import ENROLL_SAMPLES, LiveWorker
from core.utils import mark, BASE_DIR, DATA_DIR, IMAGE_EXT, MODELS_DIR, UNKNOWN_DIR, VIDEO_EXT, crop_square, fmt_time, imread, jpg_bytes
from version import APP_VERSION as _REAL_VERSION

# לבדיקות בלבד: FACEID_FAKE_VERSION=0.9 גורם לתוכנה לחשוב שהיא ישנה, ו---auto-update מתקין עדכון בלי לחיצה
APP_VERSION = os.environ.get("FACEID_FAKE_VERSION") or _REAL_VERSION

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
MODEL_TITLES = {"glintr100": "ArcFace R100 · Glint360K", "w600k_r50": "ArcFace R50 · WebFace600K"}


class ApiError(Exception):
    pass


def _netfree_blocks(url):
    """האם נטפרי חוסם את דף הסרטון (HTTP 418). כל תקלה אחרת = לא חסום (ננסה לנגן)."""
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).close()
    except urllib.error.HTTPError as e:
        return e.code == 418
    except Exception:
        pass
    return False


class Loader(QThread):
    ready = pyqtSignal(object)
    progress = pyqtSignal(int, str)

    def run(self):
        try:
            if updater.models_missing(MODELS_DIR):
                updater.fetch_models(MODELS_DIR, lambda pct, msg: self.progress.emit(pct, msg))
            self.progress.emit(-1, "טוען את מנועי הזיהוי…")
            from core.engine import FaceEngine
            self.ready.emit(FaceEngine())
        except Exception as e:
            self.ready.emit(e)


class Backend(QObject):
    _call = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.window = None
        self.settings = Settings()
        self.ai = ai.GeminiClient()
        self.engine = None
        # מסד הנתונים נפתח מיד — הממשק עולה בלי לחכות למנועי הזיהוי (שנטענים ברקע)
        self.rec_name = "w600k_r50" if (os.path.exists(os.path.join(MODELS_DIR, "w600k_r50.onnx"))
                                         and not os.path.exists(os.path.join(MODELS_DIR, "glintr100.onnx"))) else "glintr100"
        self.db = Database(self.rec_name)
        self.load_error = ""
        self.lock = threading.RLock()
        self.events, self.ev_id = deque(maxlen=80), 0
        self.rev = {"people": 0, "unknown": 0, "photos": 0, "attendance": 0, "video": 0}
        self.frame_cond = threading.Condition()
        self.frame, self.frame_id, self.labels, self.fps = None, 0, [], 0.0
        self.live = self.photo_worker = self.video_worker = None
        self.enroll = {"active": False, "n": 0, "total": ENROLL_SAMPLES, "msg": "", "done": None}
        self.photo = {"running": False, "i": 0, "n": 0, "file": "", "result": None}
        self.video = {"running": False, "pct": 0, "file": "", "status": "", "preview": 0, "phase": "", "notes": []}
        self.video_result, self.video_preview = None, None
        self.clusters = []
        self.ai_note = {"ts": "", "text": "", "error": ""}
        self.camera_error = ""
        self._rematching = False
        self.load_progress = {"pct": -1, "msg": "טוען את מנועי הזיהוי…"}
        self.update = {"version": APP_VERSION, "available": None, "downloading": -1, "error": "", "checked": 0.0, "frozen": bool(updater.current_exe())}
        self._call.connect(self._run_main)
        self.loader = Loader()
        self.loader.ready.connect(self._on_engine)
        self.loader.progress.connect(lambda pct, msg: self.load_progress.update(pct=pct, msg=msg))
        self.loader.start()
        updater.cleanup_old(_REAL_VERSION)
        threading.Thread(target=self._update_loop, daemon=True).start()

    # ---------- תשתית ----------
    def _run_main(self, job):
        fn, box, ev = job
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e
        ev.set()

    def in_main(self, fn):
        """מריץ בחוט הראשי של Qt (חלונות בחירת קבצים, יצירת חוטי עבודה) וממתין לתוצאה."""
        box, ev = {}, threading.Event()
        self._call.emit((fn, box, ev))
        ev.wait()
        if "e" in box:
            raise box["e"]
        return box.get("v")

    def _on_engine(self, engine):
        if isinstance(engine, Exception):
            self.load_error = str(engine)
            mark(f"engine load FAILED: {engine!r}")
            return
        self.engine = engine
        mark("engines ready")

    def bump(self, *keys):
        with self.lock:
            for k in keys:
                self.rev[k] += 1

    def add_event(self, kind, text, img=""):
        with self.lock:
            self.ev_id += 1
            self.events.append({"id": self.ev_id, "kind": kind, "text": text, "img": img, "time": time.strftime("%H:%M")})

    def need_db(self):
        return self.db

    def need_engine(self):
        if self.engine is None:
            raise ApiError(self.load_error or "מנועי הזיהוי עדיין נטענים — עוד כמה שניות")
        return self.engine

    def info(self):
        e = self.engine
        device = "טוען…" if e is None else "מאיץ גרפי (Intel GPU)" if e.device == "GPU" else "מעבד"
        return {"model": MODEL_TITLES.get(self.rec_name, self.rec_name), "device": device, "engine": e is not None,
                "ai": bool(self.settings["ai_enabled"] and self.ai.available), "keys": len(self.ai.keys)}

    @staticmethod
    def person_from(d):
        first, last = " ".join(str(d.get("first", "")).split()), " ".join(str(d.get("last", "")).split())
        if not first or not last:
            raise ApiError("יש למלא שם פרטי ושם משפחה")
        birth = str(d.get("birth") or "")
        if birth:
            try:
                time.strptime(birth, "%Y-%m-%d")
            except ValueError:
                raise ApiError("תאריך לידה לא תקין")
        return {"name": f"{first} {last}", "first": first, "last": last, "birth": birth, "notes": str(d.get("notes") or "").strip()}

    def gallery_changed(self):
        self.bump("people", "unknown")
        if self._rematching or self.db.photo_stats()[1] == 0:
            return
        self._rematching = True

        def work():
            try:
                self.db.rematch_photos(self.settings["threshold"])
            finally:
                self._rematching = False
                self.bump("photos")

        threading.Thread(target=work, daemon=True).start()

    # ---------- מצלמה ----------
    def camera(self, on):
        if on:
            self.need_engine()
        self.in_main(self._camera_on if on else self._camera_off)

    def _camera_on(self):
        if self.live:
            return
        self.camera_error = ""
        w = LiveWorker(self.engine, self.db, self.settings, self.ai)
        w.frame_ready.connect(self._on_frame, Qt.ConnectionType.DirectConnection)   # רץ בחוט המצלמה — רק שומר הפניה
        w.unknown_alert.connect(self._on_unknown)
        w.person_seen.connect(self._on_seen)
        w.learned.connect(lambda n: self.add_event("learned", f"{n} — למדתי מראה חדש"))
        w.enroll_progress.connect(self._on_enroll_progress)
        w.enroll_done.connect(self._on_enroll_done)
        w.ai_note.connect(self._on_ai)
        w.failed.connect(self._on_failed)
        self.live = w
        w.start()

    def _camera_off(self):
        w, self.live = self.live, None
        if w:
            w.stop()
        with self.frame_cond:
            self.frame, self.labels = None, []
            self.frame_cond.notify_all()
        self.enroll.update(active=False, msg="")

    def _on_frame(self, frame, labels, fps):
        with self.frame_cond:
            self.frame, self.labels, self.fps = frame, labels, fps
            self.frame_id += 1
            self.frame_cond.notify_all()

    def get_frame(self, last):
        with self.frame_cond:
            if self.frame_id <= last or self.frame is None:
                self.frame_cond.wait(1.0)
            if self.frame is None or self.frame_id <= last:
                return None
            frame, fid, labels, fps = self.frame, self.frame_id, self.labels, self.fps
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        meta = {"id": fid, "fps": round(fps, 1), "w": frame.shape[1], "h": frame.shape[0],
                "labels": [{"bbox": [float(v) for v in lb["bbox"]], "kps": [[float(a), float(b)] for a, b in lb["kps"]],
                            "state": lb["state"], "title": lb["title"], "sub": lb["sub"]} for lb in labels]}
        return buf.tobytes(), meta

    def _on_failed(self, msg):
        self.camera_error = msg
        self._camera_off()

    def _on_seen(self, name):
        pid = self.db.find_person(name)
        cake = "🎂 יום הולדת היום! · " if pid is not None and self.db.birthday_today(pid) else ""
        self.add_event("seen", f"{name}\n{cake}נרשם ביומן", f"img/person/{pid}" if pid else "")
        self.bump("attendance")

    def _on_unknown(self, path):
        self.add_event("unknown", "אדם לא מוכר", "img/unknownfile/" + os.path.basename(path))
        if self.settings["alert_sound"]:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        self.bump("unknown")

    def _on_ai(self, kind, text):
        if kind == "error":
            self.ai_note["error"] = text
            return
        if kind == "unknown":
            self.bump("unknown")
            text = "אדם לא מוכר: " + text
        self.ai_note.update(ts=time.strftime("%H:%M:%S"), text=text, error="")

    def enroll_start(self, person):
        if not self.live:
            raise ApiError("הפעל קודם את המצלמה")
        self.enroll.update(active=True, n=0, total=ENROLL_SAMPLES, done=None,
                           msg=f"רושם את {person['name']}: הבט למצלמה והזז מעט את הראש לצדדים")
        self.live.start_enroll(person)

    def enroll_cancel(self):
        if self.live:
            self.live.cancel_enroll()
        self.enroll.update(active=False, msg="", done=None)

    def _on_enroll_progress(self, n, total, msg):
        self.enroll.update(n=n, total=total, msg=msg)

    def _on_enroll_done(self, ok, text):
        self.enroll.update(active=False, done={"ok": ok, "text": f"{text} נרשם בהצלחה" if ok else text}, msg="")
        if ok:
            self.gallery_changed()

    # ---------- אנשים ----------
    def people(self):
        db = self.need_db()
        out = []
        photos = {pid: cnt for pid, _, _, cnt in db.photo_people()}
        for pid, name, _, n in db.persons():
            info = db.person_info(pid)
            out.append({"id": pid, "name": name, "samples": n, "age": db.age(pid), "first": info["first"], "last": info["last"],
                        "birth": info["birth"], "notes": info["notes"], "birthday": db.birthday_today(pid), "photos": photos.get(pid, 0)})
        return out

    def samples(self, pid):
        return [{"id": sid, "source": src or ""} for sid, _, src in self.need_db().person_samples(pid)]

    def pick_images(self):
        ext = " ".join("*" + e for e in sorted(IMAGE_EXT))
        return self.in_main(lambda: QFileDialog.getOpenFileNames(
            self.window, "בחר תמונות של האדם (עדיף 3–10 תמונות ברורות)", "", f"תמונות ({ext})")[0])

    def _enroll_files(self, pid, files):
        ok = 0
        for path in files:
            img = imread(path, 1920)
            if img is None:
                continue
            f = enroll_from_image(self.engine, img)
            if f is None or f.size < 40:
                continue
            self.db.add_sample(pid, f.emb, jpg_bytes(crop_square(img, f.bbox)), os.path.basename(path), reload=False)
            ok += 1
        self.db.reload_gallery()
        return ok

    def person_from_files(self, person):
        self.need_engine(); db = self.need_db()
        files = self.pick_images()
        if not files:
            return {"cancelled": True}
        pid = db.get_or_create(person)
        n = self._enroll_files(pid, files)
        if n == 0 and not db.person_samples(pid):
            db.delete_person(pid)
            raise ApiError("לא נמצאו פנים ברורות בתמונות שנבחרו")
        self.gallery_changed()
        return {"added": n, "name": person["name"]}

    def person_add_files(self, pid):
        self.need_engine()
        files = self.pick_images()
        if not files:
            return {"cancelled": True}
        n = self._enroll_files(pid, files)
        self.gallery_changed()
        return {"added": n}

    def unknown(self):
        return [{"id": eid, "time": time.strftime("%d/%m %H:%M", time.localtime(ts)), "note": note or ""}
                for eid, ts, _, _, note in self.need_db().unknown_events()]

    def unknown_name(self, eid, person):
        db = self.need_db()
        row = next((r for r in db.unknown_events(100000) if r[0] == eid), None)
        if row is None:
            raise ApiError("הרשומה לא נמצאה")
        jpg = None
        if row[2] and os.path.exists(row[2]):
            with open(row[2], "rb") as f:
                jpg = f.read()
        pid = db.get_or_create(person, jpg)
        db.add_sample(pid, np.frombuffer(row[3], np.float32), jpg, "מצלמה")
        db.delete_unknown(eid)
        self.gallery_changed()

    # ---------- תמונות ----------
    def photos_scan(self):
        self.need_engine()
        if self.photo_worker:
            return {"running": True}
        folder = self.in_main(lambda: QFileDialog.getExistingDirectory(self.window, "בחר תיקיית תמונות", os.path.expanduser("~\\Pictures")))
        if not folder:
            return {"cancelled": True}
        self.in_main(lambda: self._photos_start(folder))
        return {"started": True}

    def _photos_start(self, folder):
        w = PhotoScanWorker(self.engine, self.db, self.settings, folder)
        w.progress.connect(lambda i, n, path: self.photo.update(i=i, n=n, file=os.path.basename(path)))
        w.finished_scan.connect(self._photos_done)
        self.photo.update(running=True, i=0, n=0, file="", result=None)
        self.photo_worker = w
        w.start()

    def _photos_done(self, new, faces):
        self.photo_worker = None
        self.photo.update(running=False, result={"new": new, "faces": faces})
        self.bump("photos")

    def photos_overview(self):
        db = self.need_db()
        n, f = db.photo_stats()
        return {"photos": n, "faces": f,
                "people": [{"id": pid, "name": name, "count": cnt} for pid, name, _, cnt in db.photo_people()],
                "clusters": [{"idx": i, "count": len(c["ids"])} for i, c in enumerate(self.clusters)]}

    def photos_cluster(self):
        db = self.need_db()
        rows = db.unassigned_faces()
        embs = [np.frombuffer(r[2], np.float32) for r in rows]
        out = []
        for g in cluster_embeddings(embs, 0.5, min_size=4)[:60]:
            g = sorted(g, key=lambda i: -rows[i][4])
            out.append({"ids": [rows[i][0] for i in g], "thumb": rows[g[0]][3]})
        self.clusters = out
        self.bump("photos")
        return {"count": len(out)}

    def photos_list(self, kind, key):
        db = self.need_db()
        if kind == "p":
            return [{"path": path, "name": os.path.basename(path), "img": f"img/personphoto/{key}/{i}"}
                    for i, (path, _, _) in enumerate(db.photos_of(key)[:1500])]
        if not 0 <= key < len(self.clusters):
            return []
        return [{"path": path, "name": os.path.basename(path), "img": f"img/face/{fid}"}
                for fid, path, _, _ in db.face_rows(self.clusters[key]["ids"][:600])]

    def cluster_name(self, idx, person):
        db = self.need_db()
        if not 0 <= idx < len(self.clusters):
            raise ApiError("הקבוצה לא נמצאה")
        c = self.clusters.pop(idx)
        pid = db.get_or_create(person, c["thumb"])
        for _, path, emb, thumb in db.face_rows(c["ids"][:12]):
            db.add_sample(pid, np.frombuffer(emb, np.float32), thumb, os.path.basename(path), reload=False)
        db.reload_gallery()
        self.gallery_changed()

    def photos_copy(self, kind, key):
        paths = sorted({p["path"] for p in self.photos_list(kind, key)})
        if not paths:
            raise ApiError("אין תמונות להעתקה")
        dest = self.in_main(lambda: QFileDialog.getExistingDirectory(self.window, "לאן להעתיק?"))
        if not dest:
            return {"cancelled": True}
        n = 0
        for p in paths:
            if os.path.exists(p):
                b, e = os.path.splitext(os.path.basename(p))
                target, k = os.path.join(dest, b + e), 1
                while os.path.exists(target):
                    target = os.path.join(dest, f"{b} ({k}){e}")
                    k += 1
                shutil.copy2(p, target)
                n += 1
        os.startfile(dest)
        return {"copied": n}

    def open_photo(self, path):
        with self.db.lock:
            known = self.db.con.execute("SELECT 1 FROM photos WHERE path=?", (path,)).fetchone()
        if known and os.path.exists(path):      # פותחים רק קבצים שהתוכנה עצמה סרקה
            os.startfile(path)

    # ---------- וידאו ----------
    def video_scan(self):
        self.need_engine()
        if self.video_worker:
            return {"running": True}
        ext = " ".join("*" + e for e in sorted(VIDEO_EXT))
        path = self.in_main(lambda: QFileDialog.getOpenFileName(self.window, "בחר סרטון", os.path.expanduser("~\\Videos"), f"וידאו ({ext})")[0])
        if not path:
            return {"cancelled": True}
        self.in_main(lambda: self._video_start(path))
        return {"started": True}

    def _gemini(self):
        """לקוח Gemini לבדיקת נשים/ילדות — רק כשה-AI מופעל ויש מפתחות."""
        return self.ai if (self.settings["ai_enabled"] and self.ai.available) else None

    def video_scan_url(self, text):
        """קישור יוטיוב: Gemini צופה מהקישור (בצד של גוגל) + ניסיון הורדה לזיהוי פנים מקומי."""
        self.need_engine()
        if self.video_worker:
            return {"running": True}
        url = ai.youtube_url(text)
        if not url:
            raise ApiError("זה לא נראה כמו קישור יוטיוב")
        blocked = _netfree_blocks(url)      # נטפרי חוסם סרטונים מסוימים (418) — אז אין טעם לפתוח נגן, נשארת בדיקת Gemini מהקישור
        self.in_main(lambda: self._video_start(url, youtube=True, blocked=blocked))
        return {"started": True, "blocked": blocked}

    def _video_start(self, path, youtube=False, blocked=False):
        self._close_player()
        if youtube and blocked:
            w = YouTubeWorker(self.engine, self.db, self.settings, path, self._gemini(), None,
                              ["נטפרי חוסם את הסרטון הזה במחשב — זיהוי אנשים לא אפשרי; בוצעה רק בדיקת Gemini מהקישור (בצד של גוגל)."])
        elif youtube:
            # הנגן (חלון Qt, חוט ראשי) מזרים פריימים לתור; החוט מנתח. בלי הורדה — עובד גם בנטפרי.
            from webui.ytplayer import YouTubePlayer
            frames = queue.Queue(maxsize=60)
            self.yt_player = YouTubePlayer(path, frames, self)
            w = YouTubeWorker(self.engine, self.db, self.settings, path, self._gemini(), frames)
        else:
            w = VideoScanWorker(self.engine, self.db, self.settings, path, self._gemini())
        w.progress.connect(self._video_progress)
        w.finished_scan.connect(self._video_done)
        self.video_result = None
        self.video.update(running=True, pct=0, file=path if youtube else os.path.basename(path), status="", notes=[],
                          phase="פותח את הסרטון ביוטיוב…" if youtube else "סורק…")
        self.video_worker = w
        w.start()
        self.bump("video")

    def _close_player(self):
        p = getattr(self, "yt_player", None)
        if p is not None:
            self.yt_player = None
            p.close()

    def video_stop(self):
        if self.video_worker:
            self.video_worker.stop_flag = True
            self.video["phase"] = "עוצר… (מסכם את מה שנבדק עד עכשיו)"
        self.in_main(self._close_player)

    def _video_progress(self, pct, frame, msg=""):
        self.video["pct"] = pct
        if msg:
            self.video["phase"] = msg
        if frame is not None:
            if max(frame.shape[:2]) > 960:
                s = 960 / max(frame.shape[:2])
                frame = cv2.resize(frame, None, fx=s, fy=s)
            self.video_preview = jpg_bytes(frame, 75)
            self.video["preview"] += 1

    def _video_done(self, res):
        self.video_worker = None
        self._close_player()
        self.video["running"] = False
        if "error" in res:
            self.video["status"] = res["error"]
        else:
            self.video_result = res
            fem = res.get("females", [])
            small = sum(1 for s in fem if s.get("small"))
            st = f"אורך {fmt_time(res['duration'])} · נמצאו {len(res['people'])} אנשים" if res.get("duration") else ""
            st += f" · {len(fem)} קטעים עם נשים/ילדות" + (f" ({small} עם ילדה קטנה)" if small else "") if fem or res.get("duration") else ""
            if res.get("duration") and not fem:
                st += " · לא נמצאו נשים או ילדות"
            self.video["status"] = st.strip(" ·")
            self.video["notes"] = res.get("notes", [])
            if res.get("file"):
                self.video["file"] = os.path.basename(res["file"])
        self.video["phase"] = ""
        self.bump("video")

    def video_people(self):
        if not self.video_result:
            return []
        return [{"idx": i, "name": p["name"], "known": p["known"], "total": fmt_time(p["total"]),
                 "ranges": [f"{fmt_time(a)}–{fmt_time(b)}" for a, b in p["ranges"]]} for i, p in enumerate(self.video_result["people"])]

    def video_females(self):
        if not self.video_result:
            return []
        out = []
        for i, s in enumerate(self.video_result.get("females", [])):
            out.append({"idx": i, "kind": s["kind"], "age": s["age"], "small": bool(s["small"]), "source": s["source"],
                        "start": fmt_time(s["start"]), "end": fmt_time(s["end"]), "n": s["n"], "ai": s["ai"], "ai_female": s["ai_female"],
                        "thumb": s["thumb"] is not None})
        return out

    def video_name(self, idx, person):
        db = self.need_db()
        people = self.video_result["people"] if self.video_result else []
        if not 0 <= idx < len(people) or people[idx]["known"]:
            raise ApiError("בחר אדם לא מוכר מהרשימה")
        p = people[idx]
        pid = db.get_or_create(person, p["thumb"])
        for e, t in zip(p["embs"], p["thumbs"]):
            db.add_sample(pid, e, t, "וידאו", reload=False)
        db.reload_gallery()
        p["name"], p["known"] = person["name"], True
        self.bump("video")
        self.gallery_changed()

    def export(self, headers, rows, default_name):
        path = self.in_main(lambda: QFileDialog.getSaveFileName(self.window, "שמירה לאקסל", default_name, "Excel (*.xlsx)")[0])
        if not path:
            return {"cancelled": True}
        reports.write_xlsx(path, headers, rows)
        os.startfile(path)
        return {"saved": True}

    # ---------- עוזר ----------
    def assistant(self, q, history):
        db = self.need_db()
        if not self.ai.available:
            raise ApiError("לא הוגדר מפתח Gemini. הוסף מפתח בהגדרות.")
        images, live = [], ""
        w = self.live
        if w is not None and w.last_frame is not None:
            images = [w.last_frame.copy()]
            seen = [lb["title"] + (f" ({lb['sub']})" if lb["sub"] else "") for lb in sorted(w._labels(), key=lambda lb: -lb["bbox"][0])]
            live = "\n\nהמצלמה פועלת כעת ומצורפת תמונה ממנה. התוכנה מזהה בה (מימין לשמאל): " + ("; ".join(seen) or "אף אחד")
        hist = "\n".join(f"{'משתמש' if h.get('me') else 'עוזר'}: {h.get('text', '')}" for h in history[-6:])
        prompt = f"נתוני התוכנה:\n{reports.assistant_context(db, self.settings)}{live}\n\nשיחה עד כה:\n{hist}\n\nשאלת המשתמש: {q}"
        return self.ai.ask(prompt, images, ai.SYSTEM, max_tokens=1500)

    # ---------- עדכון תוכנה ----------
    def _update_loop(self):
        time.sleep(20)
        while True:
            self.check_update(quiet=True)
            time.sleep(60 if "--auto-update" in sys.argv else 30 * 60)

    def check_update(self, quiet=False):
        try:
            info = updater.check_latest()
            self.update["available"] = info if info and updater.is_newer(info["version"], APP_VERSION) else None
            self.update["error"] = ""
            if self.update["available"] and "--auto-update" in sys.argv and self.engine is not None:
                self.install_update()
        except Exception as e:
            self.update["error"] = "" if quiet else f"לא ניתן לבדוק עדכונים: {e}"
        self.update["checked"] = time.time()
        return {"available": self.update["available"], "error": self.update["error"]}

    def install_update(self):
        info = self.update["available"]
        if not info:
            raise ApiError("אין עדכון זמין")
        if not updater.current_exe():
            raise ApiError("עדכון אוטומטי זמין רק בגרסת התוכנה (EXE). כאן מריצים מהקוד — משכו מגיטהאב.")
        if self.update["downloading"] >= 0:
            return {"downloading": True}
        self.update["downloading"] = 0

        def work():
            try:
                exe = updater.install_update(info, lambda p: self.update.update(downloading=p))
                self.update.update(downloading=99)
                self.in_main(self.shutdown)
                updater.relaunch(exe, BASE_DIR)
                self.in_main(lambda: QApplication.instance().quit())
            except Exception as e:
                self.update.update(downloading=-1, error=str(e))

        threading.Thread(target=work, daemon=True).start()
        return {"started": True}

    # ---------- ניהול נתונים ----------
    def stats(self):
        st = self.need_db().stats()
        st["unknown_dir_bytes"] = sum(os.path.getsize(os.path.join(UNKNOWN_DIR, f)) for f in os.listdir(UNKNOWN_DIR)) if os.path.isdir(UNKNOWN_DIR) else 0
        st["data_dir"] = DATA_DIR
        st["folders"] = [{"folder": f, "count": n} for f, n in self.db.photo_folders()[:40]]
        return st

    def backup(self):
        db = self.need_db()
        name = time.strftime("גיבוי זיהוי פנים %Y-%m-%d %H%M.zip")
        path = self.in_main(lambda: QFileDialog.getSaveFileName(self.window, "שמירת גיבוי", os.path.join(os.path.expanduser("~\\Documents"), name), "ZIP (*.zip)")[0])
        if not path:
            return {"cancelled": True}
        tmp = os.path.join(tempfile.gettempdir(), "faceid_backup.db")
        db.backup_to(tmp)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "faces.db")
            for f in ("settings.json", "gemini_keys.txt"):
                fp = os.path.join(DATA_DIR, f)
                if os.path.exists(fp):
                    z.write(fp, f)
            if os.path.isdir(UNKNOWN_DIR):
                for f in os.listdir(UNKNOWN_DIR):
                    z.write(os.path.join(UNKNOWN_DIR, f), "unknown/" + f)
        os.remove(tmp)
        return {"path": path, "bytes": os.path.getsize(path)}

    def restore(self):
        db = self.need_db()
        if self.live or self.photo_worker or self.video_worker:
            raise ApiError("עצור קודם את המצלמה והסריקות")
        path = self.in_main(lambda: QFileDialog.getOpenFileName(self.window, "בחר קובץ גיבוי", os.path.expanduser("~\\Documents"), "ZIP (*.zip)")[0])
        if not path:
            return {"cancelled": True}
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "faces.db" not in names:
                raise ApiError("זה לא קובץ גיבוי של זיהוי פנים")
            safety = os.path.join(DATA_DIR, time.strftime("faces_before_restore_%Y%m%d_%H%M%S.db"))
            db.backup_to(safety)
            db.close()
            for stale in ("faces.db", "faces.db-wal", "faces.db-shm"):
                fp = os.path.join(DATA_DIR, stale)
                if os.path.exists(fp):
                    os.remove(fp)
            for n in names:
                if n in ("faces.db", "settings.json", "gemini_keys.txt") or (n.startswith("unknown/") and n != "unknown/"):
                    target = os.path.join(DATA_DIR, *n.split("/"))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(n) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        self.settings = Settings()
        self.ai.reload()
        self.db = Database(self.rec_name)
        with self.db.lock:   # נתיבי התמונות של לא-מוכרים מהמחשב הקודם → לתיקייה כאן
            rows = self.db.con.execute("SELECT id, image FROM unknown_events WHERE image<>''").fetchall()
            self.db.con.executemany("UPDATE unknown_events SET image=? WHERE id=?",
                                    [(os.path.join(UNKNOWN_DIR, os.path.basename(img.replace("/", "\\"))), eid) for eid, img in rows])
            self.db.con.commit()
        self.clusters, self.video_result = [], None
        self.bump("people", "unknown", "photos", "attendance", "video")
        return {"restored": True, "safety": safety}

    def export_people(self):
        rows = [(p["name"], p["first"], p["last"], "/".join(reversed(p["birth"].split("-"))) if p["birth"] else "",
                 p["age"] if p["age"] is not None else "", p["samples"], p["notes"]) for p in self.people()]
        return self.export(["שם", "שם פרטי", "שם משפחה", "תאריך לידה", "גיל", "דגימות", "הערות"], rows, "אנשים רשומים.xlsx")

    def attendance_rows(self, d_from, d_to):
        t0, t1 = reports.day_range(d_from, d_to)
        return [{"id": aid, "pid": pid, "name": name, "first": first, "last": last,
                 "date": time.strftime("%Y-%m-%d", time.localtime(first)), "t_in": time.strftime("%H:%M", time.localtime(first)),
                 "t_out": time.strftime("%H:%M", time.localtime(last)), "dur": fmt_time(last - first)}
                for aid, pid, name, first, last in self.need_db().attendance_rows(t0, t1)]

    @staticmethod
    def _ts(date, hm):
        try:
            return time.mktime(time.strptime(f"{date} {hm}", "%Y-%m-%d %H:%M"))
        except ValueError:
            raise ApiError("תאריך או שעה לא תקינים")

    # ---------- הגדרות ----------
    def set_settings(self, values):
        for k, v in values.items():
            if k not in DEFAULTS:
                continue
            d = DEFAULTS[k]
            self.settings[k] = bool(v) if isinstance(d, bool) else int(v) if isinstance(d, int) else float(v) if isinstance(d, float) else str(v).strip()
        self.settings.save()

    def shutdown(self):
        self._camera_off()
        self._close_player()
        for w in (self.photo_worker, self.video_worker):
            if w:
                w.stop_flag = True
                w.wait(5000)

    # ---------- תמונות ממוזערות ----------
    def image(self, parts):
        db = self.need_db()
        kind = parts[0]
        if kind == "unknownfile":
            p = os.path.join(UNKNOWN_DIR, os.path.basename(parts[1]))
            if os.path.exists(p):
                with open(p, "rb") as f:
                    return f.read()
            return None
        if kind == "cluster":
            i = int(parts[1])
            return self.clusters[i]["thumb"] if 0 <= i < len(self.clusters) else None
        if kind == "vid":
            i = int(parts[1])
            people = self.video_result["people"] if self.video_result else []
            return people[i]["thumb"] if 0 <= i < len(people) else None
        if kind == "videopreview":
            return self.video_preview
        if kind == "vidf":
            i = int(parts[1])
            fem = self.video_result.get("females", []) if self.video_result else []
            return fem[i]["thumb"] if 0 <= i < len(fem) else None
        if kind == "personphoto":
            rows = db.photos_of(int(parts[1]))
            i = int(parts[2])
            return rows[i][2] if 0 <= i < len(rows) else None
        if kind == "unknown":
            with db.lock:
                r = db.con.execute("SELECT image FROM unknown_events WHERE id=?", (int(parts[1]),)).fetchone()
            if r and r[0] and os.path.exists(r[0]):
                with open(r[0], "rb") as f:
                    return f.read()
            return None
        sql = {"person": "SELECT thumb FROM persons WHERE id=?", "sample": "SELECT thumb FROM samples WHERE id=?",
               "face": "SELECT thumb FROM photo_faces WHERE id=?"}.get(kind)
        if not sql:
            return None
        with db.lock:
            r = db.con.execute(sql, (int(parts[1]),)).fetchone()
        return bytes(r[0]) if r and r[0] else None


# ======================================================================
def make_handler(be, token):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode())

        def _route(self):
            u = urlparse(self.path)
            parts = [p for p in u.path.split("/") if p]
            if not parts or parts[0] != token:
                return None, None
            return parts[1:], {k: v[0] for k, v in parse_qs(u.query).items()}

        def do_GET(self):
            parts, q = self._route()
            if parts is None:
                return self._send(403, b"forbidden", "text/plain")
            try:
                if not parts or parts[0] in ("index.html", "app.js", "base.css", "components.css", "pages.css"):
                    name = parts[0] if parts else "index.html"
                    with open(os.path.join(STATIC, name), "rb") as f:
                        return self._send(200, f.read(), MIME[os.path.splitext(name)[1]])
                if parts[0] == "fonts" and len(parts) == 2 and parts[1].endswith(".woff2"):
                    with open(os.path.join(STATIC, "fonts", os.path.basename(parts[1])), "rb") as f:
                        return self._send(200, f.read(), "font/woff2", {"Cache-Control": "max-age=31536000"})
                if parts[0] == "frame":
                    res = be.get_frame(int(q.get("last", 0)))
                    if res is None:
                        return self._send(204)
                    jpg, meta = res
                    return self._send(200, jpg, "image/jpeg", {"X-Meta": base64.b64encode(json.dumps(meta).encode()).decode()})
                if parts[0] == "img":
                    data = be.image(parts[1:])
                    if not data:
                        return self._send(404)
                    return self._send(200, bytes(data), "image/jpeg")
                if parts[0] == "api":
                    return self._json(self.api_get(parts[1:], q))
                self._send(404)
            except ApiError as e:
                self._json({"error": str(e)}, 400)
            except (ConnectionError, BrokenPipeError):
                pass
            except Exception as e:
                self._json({"error": f"תקלה: {e}"}, 500)

        def do_POST(self):
            parts, q = self._route()
            if parts is None or not parts or parts[0] != "api":
                return self._send(403, b"forbidden", "text/plain")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
                self._json(self.api_post("/".join(parts[1:]), body) or {"ok": True})
            except ApiError as e:
                self._json({"error": str(e)}, 400)
            except ai.AIError as e:
                self._json({"error": str(e)}, 400)
            except (ConnectionError, BrokenPipeError):
                pass
            except Exception as e:
                self._json({"error": f"תקלה: {e}"}, 500)

        # ----- GET -----
        def api_get(self, parts, q):
            name = "/".join(parts)
            if name == "boot":
                if be.engine is None and be.load_progress["pct"] >= 0:      # הורדת מודלים בהפעלה ראשונה — מסך פתיחה עם התקדמות
                    return {"ready": False, "load_error": be.load_error, "progress": be.load_progress}
                return {"ready": True, "info": be.info(), "settings": dict(be.settings), "views": reports.VIEWS, "version": APP_VERSION}
            if name == "poll":
                since = int(q.get("ev", 0))
                with be.lock:
                    evs = [e for e in be.events if e["id"] > since]
                    rev = dict(be.rev)
                return {"camera": be.live is not None, "camera_error": be.camera_error, "events": evs, "rev": rev,
                        "enroll": be.enroll, "photo": be.photo, "video": be.video, "ai": be.ai_note,
                        "ai_on": bool(be.settings["ai_enabled"] and be.ai.available), "update": be.update,
                        "engine": be.engine is not None, "load_error": be.load_error}
            if name == "people":
                return be.people()
            if name == "samples":
                return be.samples(int(q["id"]))
            if name == "unknown":
                return be.unknown()
            if name == "photos":
                return be.photos_overview()
            if name == "photos/list":
                return be.photos_list(q["kind"], int(q["id"]))
            if name == "video":
                return {"state": be.video, "people": be.video_people(), "females": be.video_females(),
                        "summary": (be.video_result or {}).get("ai_summary", ""), "url": (be.video_result or {}).get("url", "")}
            if name == "attendance":
                t0, t1 = reports.day_range(q["from"], q["to"])
                headers, rows = reports.attendance_view(be.need_db(), be.settings, int(q.get("view", 0)), t0, t1)
                return {"headers": headers, "rows": rows}
            if name == "keys":
                return {"keys": "\n".join(be.ai.keys)}
            if name == "stats":
                return be.stats()
            if name == "attendance/rows":
                return be.attendance_rows(q["from"], q["to"])
            raise ApiError("לא נמצא")

        # ----- POST -----
        def api_post(self, name, b):
            db = be.need_db()
            if name == "camera":
                return be.camera(bool(b.get("on")))
            if name == "enroll/start":
                return be.enroll_start(be.person_from(b))
            if name == "enroll/cancel":
                return be.enroll_cancel()
            if name == "enroll/ack":
                be.enroll["done"] = None
                return
            if name == "people/from_files":
                return be.person_from_files(be.person_from(b))
            if name == "people/add_files":
                return be.person_add_files(int(b["id"]))
            if name == "people/update":
                db.set_person_info(int(b["id"]), be.person_from(b))
                return be.bump("people")
            if name == "people/delete":
                db.delete_person(int(b["id"]))
                return be.gallery_changed()
            if name == "samples/delete":
                db.delete_sample(int(b["id"]))
                return be.bump("people")
            if name == "unknown/name":
                return be.unknown_name(int(b["id"]), be.person_from(b))
            if name == "unknown/delete":
                db.delete_unknown(int(b["id"]))
                return be.bump("unknown")
            if name == "unknown/clear":
                for eid, *_ in db.unknown_events(100000):
                    db.delete_unknown(eid)
                return be.bump("unknown")
            if name == "photos/scan":
                return be.photos_scan()
            if name == "photos/stop":
                if be.photo_worker:
                    be.photo_worker.stop_flag = True
                return
            if name == "photos/ack":
                be.photo["result"] = None
                return
            if name == "photos/cluster":
                return be.photos_cluster()
            if name == "photos/name_cluster":
                return be.cluster_name(int(b["idx"]), be.person_from(b))
            if name == "photos/copy":
                return be.photos_copy(b["kind"], int(b["id"]))
            if name == "photos/open":
                return be.open_photo(str(b["path"]))
            if name == "video/scan":
                return be.video_scan()
            if name == "video/url":
                return be.video_scan_url(str(b.get("url", "")))
            if name == "video/stop":
                return be.video_stop()
            if name == "video/name":
                return be.video_name(int(b["idx"]), be.person_from(b))
            if name == "video/export":
                rows = [("אדם", p["name"], p["total"], ", ".join(p["ranges"]), "") for p in be.video_people()]
                rows += [(("ילדה קטנה" if f["small"] else f["kind"]), f"גיל ~{f['age']}" if f["age"] is not None else "", "",
                          f"{f['start']}–{f['end']}", f"{f['source']}: {f['ai']}".strip(": ")) for f in be.video_females()]
                return be.export(["סוג", "שם / גיל", "זמן מסך", "טווחי זמן", "הערה"], rows, "בדיקת סרטון.xlsx")
            if name == "attendance/export":
                t0, t1 = reports.day_range(b["from"], b["to"])
                view = int(b.get("view", 0))
                headers, rows = reports.attendance_view(db, be.settings, view, t0, t1)
                return be.export(headers, rows, f"נוכחות - {reports.VIEWS[view]}.xlsx")
            if name == "assistant":
                return {"answer": be.assistant(str(b.get("q", "")).strip(), b.get("history") or [])}
            if name == "settings":
                be.set_settings(b)
                return {"settings": dict(be.settings), "info": be.info()}
            if name == "keys":
                ai.save_keys(str(b.get("keys", "")))
                be.ai.reload()
                return {"info": be.info()}
            if name == "update/check":
                return be.check_update()
            if name == "update/install":
                return be.install_update()
            if name == "backup":
                return be.backup()
            if name == "restore":
                return be.restore()
            if name == "people/export":
                return be.export_people()
            if name == "people/merge":
                db.merge_persons(int(b["src"]), int(b["dst"]))
                return be.gallery_changed()
            if name == "attendance/add":
                db.add_attendance(int(b["pid"]), be._ts(b["date"], b["t_in"]), be._ts(b["date"], b["t_out"]))
                return be.bump("attendance")
            if name == "attendance/update":
                db.update_attendance(int(b["id"]), be._ts(b["date"], b["t_in"]), be._ts(b["date"], b["t_out"]))
                return be.bump("attendance")
            if name == "attendance/delete":
                db.delete_attendance(b.get("ids") or [])
                return be.bump("attendance")
            if name == "clear":
                kind = str(b.get("kind"))
                if kind not in ("attendance", "photos", "ai_notes", "unknown", "all"):
                    raise ApiError("סוג לא מוכר")
                if kind == "all" and (be.live or be.photo_worker or be.video_worker):
                    raise ApiError("עצור קודם את המצלמה והסריקות")
                if kind == "attendance" and b.get("from"):
                    db.clear(kind, *reports.day_range(b["from"], b["to"]))
                else:
                    db.clear(kind)
                be.clusters = []
                return be.bump("people", "unknown", "photos", "attendance")
            if name == "photos/forget":
                n = db.forget_folder(str(b["folder"]))
                be.bump("photos")
                return {"removed": n}
            if name == "unknown/purge":
                n = db.purge_unknown(int(b.get("days", 30)))
                be.bump("unknown")
                return {"removed": n}
            raise ApiError("לא נמצא")

    return Handler


def start_server(be):
    token = secrets.token_urlsafe(16)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(be, token))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/{token}/"
