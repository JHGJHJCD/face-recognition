"""זיהוי חי: לכידת מצלמה, מעקב אחרי פנים בין פריימים, הצבעת זהות, נוכחות, התרעות ורישום."""
import os
import queue
import threading
import time
from collections import Counter, deque

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from . import ai
from .db import AUTO_SOURCE
from .engine import EMOTIONS, enhance_low_light, sharpness
from .utils import UNKNOWN_DIR, crop_square, imwrite, jpg_bytes

REC_EVERY = 0.5      # שניות בין זיהויים חוזרים לאותו אדם במעקב
ENROLL_SAMPLES = 8
AUTO_LEARN_MAX = 20  # תקרת דגימות שנלמדות לבד לכל אדם


def _iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


class Track:
    _next = 1

    def __init__(self, face, now):
        self.id = Track._next
        Track._next += 1
        self.face = face
        self.born = self.last_seen = now
        self.last_rec = 0.0
        self.votes = deque(maxlen=6)
        self.pid, self.sim = None, 0.0
        self.ages = deque(maxlen=12)
        self.male_votes = deque(maxlen=12)
        self.emo_p = None
        self.real_ema, self.real_n = None, 0
        self.alerted = False
        self.best_unknown = None  # (איכות, emb, תמונה)

    @property
    def spoof(self):
        return self.real_n >= 3 and self.real_ema is not None and self.real_ema < 0.45

    def decide(self):
        known = [(p, s) for p, s in self.votes if p is not None]
        if not known:
            self.pid, self.sim = None, max((s for _, s in self.votes), default=0.0)
            return
        pid, cnt = Counter(p for p, _ in known).most_common(1)[0]
        sims = [s for p, s in known if p == pid]
        if cnt >= 2 or len(self.votes) == 1 or cnt / len(self.votes) >= 0.5:
            self.pid, self.sim = pid, float(np.mean(sims))
        else:
            self.pid, self.sim = None, float(np.mean(sims))


class LiveWorker(QThread):
    frame_ready = pyqtSignal(object, object, float)   # תמונת BGR, רשימת תוויות, FPS
    unknown_alert = pyqtSignal(str)                  # נתיב תמונה
    person_seen = pyqtSignal(str)                    # שם — כניסה חדשה ליומן הנוכחות
    enroll_progress = pyqtSignal(int, int, str)      # נאספו, מתוך, הודעה
    enroll_done = pyqtSignal(bool, str)
    failed = pyqtSignal(str)
    ai_note = pyqtSignal(str, str)                   # סוג ("scene"/"unknown"/"error"), טקסט
    learned = pyqtSignal(str)                        # שם — נוספה דגימה בלמידה אוטומטית

    def __init__(self, engine, db, settings, ai_client=None):
        super().__init__()
        self.engine, self.db, self.st = engine, db, settings
        self.ai = ai_client
        self.ai_jobs = queue.Queue(maxsize=4)
        self.ai_last, self.ai_people, self.ai_fail = 0.0, frozenset(), 0
        self.last_learn = {}
        self.last_frame = None
        self._job, self._job_ready = None, threading.Event()
        self.running = False
        self.last_view = 0.0        # מתי הממשק ביקש תמונה בפעם האחרונה — כשלא צופים, הזיהוי מאט כדי לא להכביד על ההקלדה במסכים אחרים
        self.paused = False         # חלון הקלדה פתוח — המצלמה משוחררת זמנית (ראה run)
        self.tracks = []
        self.recent_unknown = deque(maxlen=50)   # (זמן, emb)
        self.last_marked = {}
        self._enroll = None

    # ---------- רישום אדם מהמצלמה ----------
    def start_enroll(self, info):
        self._enroll = {"name": info["name"], "info": info, "embs": [], "thumbs": [], "last": 0.0, "t0": time.time()}

    def cancel_enroll(self):
        self._enroll = None

    def _enroll_step(self, frame, now):
        en = self._enroll
        if en is None:
            return
        if now - en["t0"] > 60:     # לפני בדיקת הפנים — אחרת מי שיצא מהפריים משאיר "רושם…" לנצח (ומשתיק התרעות ו-AI)
            self._enroll = None
            self.enroll_done.emit(False, "לא הצלחתי לקלוט פנים ברורות. נסה שוב בתאורה טובה יותר.")
            return
        if not self.tracks:
            return
        tr = max(self.tracks, key=lambda t: t.face.size)
        f = tr.face
        if now - en["last"] < 0.45 or tr.last_seen != now:
            return
        msg = ""
        if f.size < 90:
            msg = "התקרב למצלמה"
        elif f.frontal < 0.35 and len(en["embs"]) < 3:
            msg = "הבט ישר למצלמה"
        elif sharpness(frame, f.bbox) < 25:
            msg = "התמונה מטושטשת — אל תזוז"
        elif self.st["antispoof"] and tr.spoof:
            msg = "זוהה ניסיון זיוף — נדרשות פנים אמיתיות"
        if msg:
            self.enroll_progress.emit(len(en["embs"]), ENROLL_SAMPLES, msg)
            return
        if f.emb is None:
            self.engine.embed(frame, [f])
        if en["embs"] and float(np.max(np.stack(en["embs"]) @ f.emb)) > 0.93 and now - en["last"] < 2.5:
            self.enroll_progress.emit(len(en["embs"]), ENROLL_SAMPLES, "הזז מעט את הראש לצדדים")
            return
        en["embs"].append(f.emb)
        en["thumbs"].append(jpg_bytes(crop_square(frame, f.bbox)))
        en["last"] = now
        self.enroll_progress.emit(len(en["embs"]), ENROLL_SAMPLES, "מצוין, ממשיך לקלוט…")
        if len(en["embs"]) >= ENROLL_SAMPLES:
            pid = self.db.get_or_create(en["info"], en["thumbs"][0])
            for e, t in zip(en["embs"], en["thumbs"]):
                self.db.add_sample(pid, e, t, "מצלמה", reload=False)
            self.db.reload_gallery()
            for t in self.tracks:
                t.votes.clear()
                t.last_rec = 0
            self._enroll = None
            self.enroll_done.emit(True, en["name"])

    # ---------- לולאה ראשית ----------
    def _open(self):
        cap = cv2.VideoCapture(int(self.st["camera"]), cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(int(self.st["camera"]))
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return cap

    def run(self):
        cap = self._open()
        if cap is None:
            self.failed.emit("לא הצלחתי לפתוח את המצלמה. בדוק שהיא מחוברת ושאף תוכנה אחרת לא משתמשת בה.")
            return
        self.running = True
        threading.Thread(target=self._ai_loop, daemon=True).start()
        threading.Thread(target=self._analyze_loop, daemon=True).start()
        fps, t_prev, fails, n_frame = 0.0, time.time(), 0, 0
        while self.running:
            if self.paused:
                # חלון הקלדה פתוח — משחררים את המצלמה לגמרי. נמדד 22/9: עצם הזרמת המצלמה (גם בתהליך אחר, בלי זיהוי)
                # מקפיאה את הממשק ל-0.3–0.5 שנ' בכל פעם, וההקלדה "נתקעת". ברגע שהחלון נסגר פותחים מחדש (~1 שנ').
                if cap is not None:
                    cap.release()
                    cap = None
                    self.tracks = []
                time.sleep(0.1)
                continue
            if cap is None:
                cap = self._open()
                if cap is None:
                    self.failed.emit("המצלמה לא נפתחה מחדש אחרי ההשהיה.")
                    break
            ok, frame = cap.read()
            if not ok:
                fails += 1
                if fails > 30:
                    self.failed.emit("המצלמה הפסיקה לשדר.")
                    break
                time.sleep(0.05)
                continue
            fails = 0
            if self.st["mirror"]:
                frame = cv2.flip(frame, 1)
            now = time.time()
            frame = enhance_low_light(frame)
            self.last_frame = frame
            try:
                # איתור פנים (~45ms) רק בכל תמונה שנייה — התצוגה רצה בקצב המלא של המצלמה, והמסגרות נשארות מהאיתור האחרון (33ms קודם)
                n_frame += 1
                # כשאף אחד לא צופה בזיהוי החי (מסך אחר / חלון פתוח) — איתור כל 6 תמונות במקום כל 2 (נמדד 22/9: ההקלדה נתקעה בגלל העומס על המאיץ)
                if n_frame % (2 if now - self.last_view < 2 else 6) == 0:
                    self._process(frame, now)
                    self._ai_tick(frame, now)
                    self._enroll_step(frame, now)
            except Exception as e:  # פריים בעייתי לא מפיל את הזיהוי
                print("live error:", e)
            dt = now - t_prev
            t_prev = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 / dt if fps else 1 / dt
            self.frame_ready.emit(frame, self._labels(), fps)
        if cap is not None:
            cap.release()
        self.tracks = []

    def stop(self):
        self.running = False
        self.wait(3000)

    def _process(self, frame, now):
        faces = self.engine.detect(frame, 0.55, max_faces=12)
        # שיוך פנים למעקבים קיימים
        free = list(self.tracks)
        for f in faces:
            best, best_iou = None, 0.25
            for t in free:
                v = _iou(f.bbox, t.face.bbox)
                if v > best_iou:
                    best, best_iou = t, v
            if best is None:
                best = Track(f, now)
                self.tracks.append(best)
            else:
                free.remove(best)
            best.face, best.last_seen = f, now
        self.tracks = [t for t in self.tracks if now - t.last_seen < 0.7]

        due = [t for t in self.tracks if t.last_seen == now and now - t.last_rec >= REC_EVERY and t.face.size >= self.st["min_face"]]
        due.sort(key=lambda t: t.last_rec)
        # הניתוח (זהות/גיל/הבעה/זיוף ≈ 100ms לפנים) רץ בחוט נפרד — התצוגה נשארת חלקה בקצב המצלמה (נמדד: 11 → ~30 תמונות בשנייה)
        if due and not self._job_ready.is_set():
            for t in due[:3]:
                t.last_rec = now
            self._job = (frame, [(t, t.face) for t in due[:3]], now)   # הפנים של הפריים הזה — עד שהניתוח ירוץ t.face כבר יתחלף
            self._job_ready.set()

    def _analyze_loop(self):
        while self.running:
            if not self._job_ready.wait(0.3):
                continue
            frame, tracks, now = self._job
            for t, face in tracks:
                try:
                    self._analyze(frame, t, now, face)
                except Exception as e:
                    print("analyze error:", e)
            self._job_ready.clear()

    def _analyze(self, frame, t, now, face=None):
        f = face or t.face
        t.last_rec = now
        thr = self.st["threshold"]
        self.engine.embed(frame, [f], tta=False)
        vote = self.db.match(f.emb, thr)
        if thr - 0.12 <= vote[1] < thr + 0.15:     # מקרה גבולי — מדידה מדויקת יותר (תמונה + תמונת ראי, כפול זמן)
            self.engine.embed(frame, [f], tta=True)
            vote = self.db.match(f.emb, thr)
        sharp = sharpness(frame, f.bbox)
        poor = sharp < 12 or f.frontal < 0.15
        if vote[0] is not None or not poor or not t.votes:   # פריים גרוע שלא זוהה אינו ראיה ל"לא מוכר"
            t.votes.append(vote)
        t.decide()
        if self.st["show_age"] and len(t.ages) < t.ages.maxlen:
            self.engine.gender_age(frame, f)
            t.ages.append(f.age)
            t.male_votes.append(f.male)
        if self.st["show_emotion"]:
            self.engine.emotion(frame, f)
            if f.emotion_p is not None:
                t.emo_p = f.emotion_p if t.emo_p is None else 0.5 * t.emo_p + 0.5 * f.emotion_p
        if self.st["antispoof"]:
            self.engine.liveness(frame, f)
            if f.real_p is not None:
                t.real_ema = f.real_p if t.real_ema is None else 0.6 * t.real_ema + 0.4 * f.real_p
                t.real_n += 1

        if t.pid is not None:
            if self.st["attendance"] and not t.spoof and len(t.votes) >= 2 and now - self.last_marked.get(t.pid, 0) > 10:
                self.last_marked[t.pid] = now
                if self.db.mark_seen(t.pid, self.st["attendance_gap_min"], now):
                    self.person_seen.emit(self.db.names.get(t.pid, ""))
            self._auto_learn(frame, t, sharp, now, f)
            return
        # אדם לא מוכר — שומרים את הצילום הטוב ביותר ומתריעים פעם אחת
        q = f.size * f.frontal * f.det
        if f.size >= 80 and f.frontal > 0.4 and (t.best_unknown is None or q > t.best_unknown[0]):
            t.best_unknown = (q, f.emb, frame.copy(), f.bbox.copy())
        if (self.st["alert_unknown"] and not t.alerted and t.best_unknown and len(t.votes) >= 4
                and all(p is None for p, _ in t.votes) and not t.spoof and self._enroll is None):
            t.alerted = True
            _, emb, img, bbox = t.best_unknown
            if any(now - ts < 600 and float(e @ emb) > 0.45 for ts, e in self.recent_unknown):
                return
            self.recent_unknown.append((now, emb))
            path = os.path.join(UNKNOWN_DIR, time.strftime("%Y%m%d_%H%M%S") + f"_{t.id}.jpg")
            imwrite(path, crop_square(img, bbox, margin=0.8, size=320))
            self.db.add_unknown(path, emb)
            self.unknown_alert.emit(path)
            self._ai_submit(("unknown", path))

    def _auto_learn(self, frame, t, sharp, now, face=None):
        """אדם שזוהה בביטחון גבוה לאורך זמן אבל נראה שונה מהדגימות שלו (תאורה/זווית/משקפיים) — לומדים את המראה החדש."""
        f = face or t.face
        if (not self.st["auto_learn"] or self._enroll is not None or t.spoof or len(t.votes) < t.votes.maxlen
                or any(p != t.pid for p, _ in t.votes) or t.sim < 0.58 or now - self.last_learn.get(t.pid, 0) < 30
                or f.size < 100 or sharp < 30 or f.frontal < 0.3 or (self.st["antispoof"] and t.real_n < 3)):
            return
        sims = self.db.person_sims(t.pid, f.emb)
        if len(sims) == 0 or float(sims.max()) > 0.75:
            return
        self.last_learn[t.pid] = now
        if self.db.auto_sample_count(t.pid) >= AUTO_LEARN_MAX:
            return
        self.db.add_sample(t.pid, f.emb, jpg_bytes(crop_square(frame, f.bbox)), AUTO_SOURCE)
        self.learned.emit(self.db.names.get(t.pid, ""))

    # ---------- בינה מלאכותית (Gemini) — רץ בחוט נפרד כדי לא לעכב את המצלמה ----------
    def _ai_on(self):
        return self.ai is not None and self.st["ai_enabled"] and self.ai.available

    def _ai_submit(self, job):
        if self._ai_on():
            try:
                self.ai_jobs.put_nowait(job)
            except queue.Full:
                pass

    def _ai_tick(self, frame, now):
        if not self._ai_on() or not self.tracks or self._enroll is not None:
            return
        settled = [t for t in self.tracks if len(t.votes) >= 2]
        if not settled:
            return
        people = frozenset(t.pid if t.pid is not None else -t.id for t in settled)
        wait = max(10, int(self.st["ai_interval"])) * (1 + min(self.ai_fail, 5))
        changed = people != self.ai_people and now - self.ai_last > 8
        if changed or now - self.ai_last > wait:
            self.ai_last, self.ai_people = now, people
            order = sorted(self._labels(), key=lambda lb: -lb["bbox"][0])
            desc = [lb["title"].split("  ")[0] + (f" ({lb['sub']})" if lb["sub"] else "") for lb in order]
            self._ai_submit(("scene", frame.copy(), desc))

    def _ai_loop(self):
        while self.running:
            try:
                job = self.ai_jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if job[0] == "scene":
                    text = self.ai.ask(ai.scene_prompt(job[2]), [job[1]], ai.SYSTEM, max_tokens=300)
                    self.db.add_ai_note("scene", ", ".join(job[2]), text)
                else:
                    with open(job[1], "rb") as fh:
                        text = self.ai.ask(ai.UNKNOWN_PROMPT, [fh.read()], ai.SYSTEM, max_tokens=200)
                    self.db.set_unknown_note(job[1], text)
                    self.db.add_ai_note("unknown", "", text)
                self.ai_fail = 0
                self.ai_note.emit(job[0], text)
            except Exception as e:
                self.ai_fail += 1
                self.ai_note.emit("error", str(e))

    def _labels(self):
        out = []
        for t in self.tracks:
            if t.spoof and self.st["antispoof"]:
                state, title = "spoof", "⚠ זיוף — תמונה או מסך"
            elif t.pid is not None:
                state, title = "known", f"{self.db.names.get(t.pid, '?')}  {int(round(min(1.0, t.sim / 0.7) * 100))}%"
            elif len(t.votes) >= 2:
                state, title = "unknown", "לא מוכר"
            else:
                state, title = "pending", "מזהה…"
            sub = []
            real_age = self.db.age(t.pid) if t.pid is not None else None
            if self.st["show_age"] and t.ages:
                male = sum(t.male_votes) * 2 >= len(t.male_votes)
                if real_age is not None:     # תאריך לידה שהוזן גובר על ההערכה של המודל
                    sub.append((f"גבר, בן {real_age}" if male else f"אישה, בת {real_age}") + (" 🎂" if self.db.birthday_today(t.pid) else ""))
                else:
                    age = int(round(float(np.median(t.ages)) / 5) * 5)
                    sub.append(f"גבר, כבן {age}" if male else f"אישה, כבת {age}")
            elif real_age is not None:
                sub.append(f"גיל {real_age}")
            if self.st["show_emotion"] and t.emo_p is not None:
                sub.append(EMOTIONS[int(np.argmax(t.emo_p))])
            out.append({"bbox": t.face.bbox, "kps": t.face.kps, "state": state, "title": title, "sub": " · ".join(sub)})
        return out
