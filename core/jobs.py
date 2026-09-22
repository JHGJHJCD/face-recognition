"""עבודות רקע: סריקת תיקיות תמונות וסריקת סרטוני וידאו."""
import os
import queue
import threading

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from . import ai
from .db import cluster_embeddings
from .utils import DATA_DIR, IMAGE_EXT, crop_square, fmt_time, imread, jpg_bytes, short_path


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


# ======================================================================
# סריקת וידאו: מי מופיע (זיהוי פנים) + בדיקת נשים וילדות (FairFace מקומי → אימות Gemini על פריימים).
# קישור יוטיוב: Gemini צופה בסרטון בצד של גוגל (נטפרי לא מפריע) ובמקביל מנסים להוריד לזיהוי פנים מקומי.

VIDEOS_DIR = os.path.join(DATA_DIR, "videos")


def _ranges(times, step):
    """מאחד רגעי-דגימה רצופים לטווחי זמן (הפסקה > 3.5 דגימות = טווח חדש)."""
    out, start, prev = [], times[0], times[0]
    for t in times[1:]:
        if t - prev > step * 3.5:
            out.append((start, prev + step))
            start = t
        prev = t
    out.append((start, prev + step))
    return out


def _small(frame, size):
    if max(frame.shape[:2]) > size:
        s = size / max(frame.shape[:2])
        return cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return frame


def _kind(age, girl_age):
    return "ילדה" if age < 13 else ("נערה" if age < 18 else "אישה")


def _ts(text):
    """'mm:ss' / 'h:mm:ss' / מספר → שניות."""
    try:
        parts = [float(p) for p in str(text).strip().split(":")]
    except ValueError:
        return 0.0
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


class FrameAnalyzer:
    """מנתח פריימים אחד-אחד (מקובץ או מנגן יוטיוב): זיהוי פנים + סיווג נשים/ילדות. feed(frame, t) ואז finish()."""

    def __init__(self, engine, db, st, gemini=None):
        self.engine, self.db, self.st, self.gemini = engine, db, st, gemini
        self.step = max(0.2, float(st["video_step"]))
        self.girl_age = float(st.get("girl_age", 7))
        self.seen = {}                 # pid -> [(זמן, דמיון)]
        self.best = {}                 # pid -> (דמיון, thumb)
        self.unk_embs, self.unk_meta = [], []
        self.fem = []                  # (זמן, גיל משוער, thumb, איכות) — כל פנים שסווגו כנשיות
        self.fem_frames = {}           # דלי של 5 שנ' -> (איכות, זמן, JPEG של הפריים המלא) — לאימות Gemini עם הקשר של הגוף
        self.last_t = 0.0
        self.times = []                # זמני הדגימות — למרווח בפועל (בנגן יוטיוב הוא לא קבוע)
        self.snaps = {}                # דלי של 5 שנ' -> JPEG קטן של הפריים — תמונה לקטעים של Gemini כשאין קובץ

    def feed(self, frame, t):
        frame = _small(frame, 1920)
        self.last_t = max(self.last_t, t)
        self.times.append(t)
        self.snaps.setdefault(int(t // 5), jpg_bytes(_small(frame, 320), 80))
        faces = [f for f in self.engine.detect(frame, 0.55) if f.size >= 40]
        self.engine.embed(frame, faces)
        for f in faces:
            pid, sim = self.db.match(f.emb, self.st["threshold"])
            if pid is not None:
                self.seen.setdefault(pid, []).append((t, sim))
                if pid not in self.best or sim > self.best[pid][0]:
                    self.best[pid] = (sim, jpg_bytes(crop_square(frame, f.bbox, size=112)))
            elif f.size >= 60 and f.det > 0.65:
                self.unk_embs.append(f.emb)
                self.unk_meta.append((t, jpg_bytes(crop_square(frame, f.bbox, size=112)), f.size * f.frontal))
            try:
                self.engine.gender_age(frame, f)
            except Exception:
                continue
            if f.male is False:
                q = f.size * (0.3 + f.frontal) * f.det
                self.fem.append((t, float(f.age), jpg_bytes(crop_square(frame, f.bbox, margin=0.6, size=112)), q))
                b = int(t // 5)
                if b not in self.fem_frames or q > self.fem_frames[b][0]:
                    self.fem_frames[b] = (q, t, jpg_bytes(_small(frame, 800), 80))
        return faces

    def snap(self, t):
        return self.snaps.get(int(t // 5)) or (self.snaps[min(self.snaps, key=lambda b: abs(b * 5 - t))] if self.snaps else None)

    def finish(self, stop, progress, duration=None):
        ts = sorted(self.times)
        gaps = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
        if gaps:
            self.step = max(self.step, gaps[len(gaps) // 2])      # מרווח חציוני בפועל — כדי שלא יתפצל לקטעים של שנייה
        people = []
        for pid, hits in self.seen.items():
            r = _ranges(sorted(t for t, _ in hits), self.step)
            people.append({"name": self.db.names.get(pid, "?"), "thumb": self.best[pid][1], "ranges": r,
                           "total": sum(b - a for a, b in r), "sim": float(np.mean([s for _, s in hits])), "known": True})
        people.sort(key=lambda p: -p["total"])
        for n, grp in enumerate(cluster_embeddings(self.unk_embs, 0.45, min_size=2), 1):
            r = _ranges(sorted(self.unk_meta[i][0] for i in grp), self.step)
            order = sorted(grp, key=lambda i: -self.unk_meta[i][2])
            people.append({"name": f"לא מוכר {n}", "thumb": self.unk_meta[order[0]][1], "ranges": r, "total": sum(b - a for a, b in r),
                           "sim": 0.0, "known": False, "embs": [self.unk_embs[i] for i in order[:8]],
                           "thumbs": [self.unk_meta[i][1] for i in order[:8]]})
        females = _female_segments(self.fem, self.fem_frames, self.step, self.girl_age, self.gemini, stop, progress)
        return {"people": people, "females": females, "duration": duration if duration else self.last_t, "stopped": stop()}


def scan_video(engine, db, st, path, progress, stop, gemini=None):
    """סורק קובץ וידאו. progress(pct, frame|None, msg) · stop() → True לעצירה · gemini = GeminiClient או None.
    מחזיר {"people": [...], "females": [...], "duration": שניות, "stopped": bool} או {"error": ...}."""
    cap = cv2.VideoCapture(short_path(path))
    if not cap.isOpened():
        return {"error": "לא הצלחתי לפתוח את קובץ הווידאו."}
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    an = FrameAnalyzer(engine, db, st, gemini)
    every = max(1, int(round(fps * an.step)))
    idx = 0
    while not stop():
        if not cap.grab():
            break
        if idx % every == 0:
            ok, frame = cap.retrieve()
            if ok and frame is not None:
                an.feed(frame, idx / fps)
                progress(int(idx * 100 / total), frame if (idx // every) % 3 == 0 else None, "")
        idx += 1
    cap.release()
    if stop():
        an.gemini = None
    return an.finish(stop, progress, idx / fps)


def _female_segments(fem, frames, step, girl_age, gemini, stop, progress):
    """מאחד את הפנים הנשיות לקטעי זמן; לכל קטע גיל משוער (הצעירה בקטע) ואימות Gemini על 1–2 פריימים."""
    if not fem:
        return []
    segs = []
    for a, b in _ranges(sorted({t for t, *_ in fem}), step):
        hits = [x for x in fem if a <= x[0] <= b]
        age = min(x[1] for x in hits)
        top = max(hits, key=lambda x: x[3])
        segs.append({"start": a, "end": b, "n": len(hits), "age": int(round(age)), "kind": _kind(age, girl_age),
                     "small": age < girl_age, "thumb": top[2], "source": "פנים", "ai": "", "ai_female": None})
    if gemini is None or stop():
        return segs
    # פריימים לאימות: הטוב ביותר בכל קטע, ועוד אחד לקטע ארוך (> 20 שנ')
    picks = []                # (מספר קטע, JPEG)
    for i, s in enumerate(segs):
        cands = sorted((v for k, v in frames.items() if s["start"] - 5 <= v[1] <= s["end"]), key=lambda v: -v[0])
        for v in cands[:2 if s["end"] - s["start"] > 20 else 1]:
            picks.append((i, v[2]))
    verdict = {}              # מספר קטע -> רשימת תשובות
    for j in range(0, len(picks), 6):
        if stop():
            break
        batch = picks[j:j + 6]
        progress(100, None, f"Gemini בודק נשים וילדות בפריימים… {j + len(batch)}/{len(picks)}")
        try:
            ans = ai.parse_json(gemini.ask(ai.frames_check_prompt(len(batch), int(girl_age)), [b for _, b in batch],
                                           temperature=0.1, max_tokens=1500, timeout=45, stop=stop))
            for row in ans if isinstance(ans, list) else []:
                k = int(row.get("i", -1))
                if 0 <= k < len(batch):
                    verdict.setdefault(batch[k][0], []).append(row)
        except Exception as e:
            for i, _ in batch:
                verdict.setdefault(i, []).append({"error": str(e)[:80]})
    for i, s in enumerate(segs):
        rows = verdict.get(i, [])
        good = [r for r in rows if "error" not in r]
        if not good:
            s["ai"] = "Gemini: " + (rows[0]["error"] if rows else "לא נבדק")
            continue
        fem_rows = [r for r in good if r.get("female")]
        s["ai_female"] = bool(fem_rows)
        if not fem_rows:
            s["ai"] = "Gemini: לא זיהה דמות נשית"
            continue
        ages = [float(r["age"]) for r in fem_rows if isinstance(r.get("age"), (int, float))]
        if ages:
            s["age"] = int(round(min(ages)))
            s["kind"] = _kind(min(ages), girl_age)
            s["small"] = min(ages) < girl_age or any(r.get("small") for r in fem_rows)
        note = "; ".join(str(r.get("note", "")).strip() for r in fem_rows if r.get("note"))
        s["ai"] = "Gemini: " + (note or "אישר")
    return segs


def ai_video_check(gemini, url, girl_age, stop=None):
    """Gemini צופה בסרטון יוטיוב שלם מהקישור. מחזיר (קטעים, סיכום). מעלה AIError בכישלון."""
    text = gemini.ask(ai.video_check_prompt(int(girl_age)), video_url=url, temperature=0.2, max_tokens=8000, timeout=600, stop=stop)
    data = ai.parse_json(text)
    segs = []
    for r in data.get("segments", []) if isinstance(data, dict) else []:
        a, b = _ts(r.get("start", 0)), _ts(r.get("end", 0))
        if b < a:
            a, b = b, a
        age = r.get("age")
        age = float(age) if isinstance(age, (int, float)) else None
        who = str(r.get("who", "") or "")
        kind = _kind(age, girl_age) if age is not None else (who if who in ("אישה", "נערה", "ילדה") else "אישה")
        segs.append({"start": a, "end": max(b, a + 1), "n": 0, "age": int(round(age)) if age is not None else None, "kind": kind,
                     "small": bool(r.get("small")) or (age is not None and age < girl_age), "thumb": None, "source": "Gemini",
                     "ai": str(r.get("note", "") or ""), "ai_female": True})
    segs.sort(key=lambda s: s["start"])
    return segs, str(data.get("summary", "") if isinstance(data, dict) else "")


def _frame_at(path, sec):
    cap = cv2.VideoCapture(short_path(path))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ok, frame = cap.read()
        return jpg_bytes(_small(frame, 320), 80) if ok and frame is not None else None
    finally:
        cap.release()


def download_youtube(url, progress, stop):
    """מוריד סרטון יוטיוב ל-data/videos (עד 720p, קובץ אחד בלי ffmpeg). מחזיר נתיב או מעלה שגיאה.
    בנטפרי יוטיוב חסום (HTTP 418) — הקורא מציג הודעה ומסתפק בבדיקת Gemini."""
    import yt_dlp
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    vid = ai._YT_RE.search(url).group(1)
    for f in os.listdir(VIDEOS_DIR):
        if f.startswith(vid + ".") and not f.endswith(".part"):
            return os.path.join(VIDEOS_DIR, f)

    def hook(d):
        if stop():
            raise yt_dlp.utils.DownloadCancelled()
        if d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            progress(int(d.get("downloaded_bytes", 0) * 100 / tot) if tot else 0, None,
                     f"מוריד מיוטיוב… {d.get('downloaded_bytes', 0) // 1048576}MB")

    opts = {"format": "b[ext=mp4][height<=720]/b[height<=720]/b", "outtmpl": os.path.join(VIDEOS_DIR, "%(id)s.%(ext)s"),
            "noplaylist": True, "quiet": True, "no_warnings": True, "progress_hooks": [hook], "retries": 2, "socket_timeout": 20}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
        path = y.prepare_filename(info)
    # שומרים רק את 3 הסרטונים האחרונים
    files = sorted((os.path.join(VIDEOS_DIR, f) for f in os.listdir(VIDEOS_DIR)), key=os.path.getmtime)
    for f in files[:-3]:
        try:
            os.remove(f)
        except OSError:
            pass
    return path


class VideoScanWorker(QThread):
    progress = pyqtSignal(int, object, str)      # אחוזים, פריים לתצוגה מקדימה (או None), הודעת שלב
    finished_scan = pyqtSignal(object)           # תוצאת scan_video | {"error": ...}

    def __init__(self, engine, db, settings, path, gemini=None):
        super().__init__()
        self.engine, self.db, self.st, self.path, self.gemini = engine, db, settings, path, gemini
        self.stop_flag = False

    def run(self):
        try:
            res = scan_video(self.engine, self.db, self.st, self.path, self.progress.emit, lambda: self.stop_flag, self.gemini)
        except Exception as e:
            res = {"error": f"שגיאה בסריקה: {e}"}
        self.finished_scan.emit(res)


class YouTubeWorker(QThread):
    """קישור יוטיוב, שלושה מסלולים במקביל/בגיבוי:
    1. player — נגן יוטיוב בתוך חלון של התוכנה (webui/ytplayer.py) מזרים לנו פריימים דרך תור (frames), בלי הורדה. זה עובד גם בנטפרי.
    2. Gemini צופה בסרטון מהקישור בצד של גוגל (חוט נפרד) — קטעי נשים/ילדות של כל הסרטון.
    3. אם אין נגן / הנגן נכשל — הורדה עם yt-dlp (נכשלת בנטפרי) וסריקה מקומית."""
    progress = pyqtSignal(int, object, str)
    finished_scan = pyqtSignal(object)

    def __init__(self, engine, db, settings, url, gemini=None, frames=None, notes=()):
        super().__init__()
        self.engine, self.db, self.st, self.url, self.gemini = engine, db, settings, url, gemini
        self.frames = frames          # queue.Queue של (זמן, אורך, frame) ; (None, אורך, "ended"|"error:…") בסיום
        self.pre_notes = list(notes)  # הודעות שכבר ידועות (למשל: נטפרי חוסם את הסרטון — אין נגן)
        self.stop_flag = False

    def _from_player(self, stop):
        """מנתח פריימים מהנגן עד סיום. מחזיר (תוצאה, הודעת שגיאה)."""
        an = FrameAnalyzer(self.engine, self.db, self.st, self.gemini)
        last_key, duration, n = -1, 0.0, 0
        while not stop():
            try:
                t, duration, frame = self.frames.get(timeout=1.0)
            except queue.Empty:
                continue
            if t is None:
                if isinstance(frame, str) and frame.startswith("error:"):
                    return None, frame[6:]
                break
            key = int(t / an.step)
            if key == last_key:       # אותו רגע בסרטון (הנגן מושהה/טוען) — לא סופרים פעמיים
                continue
            last_key = key
            n += 1
            an.feed(frame, t)
            pct = int(t * 100 / duration) if duration else 0
            self.progress.emit(pct, frame if n % 3 == 0 else None, f"מנתח בתוך יוטיוב… {fmt_time(t)} / {fmt_time(duration)}")
        if n == 0:
            return None, "לא התקבלו פריימים מהנגן"
        if stop():
            an.gemini = None              # נעצר — מסכמים מה שיש בלי להמתין ל-Gemini
        res = an.finish(stop, self.progress.emit, duration)
        res["snap"] = an.snap
        return res, ""

    def run(self):
        stop = lambda: self.stop_flag  # noqa: E731
        girl_age = float(self.st.get("girl_age", 7))
        box = {}
        th = None
        if self.gemini is not None:
            def ai_pass():
                try:
                    box["segs"], box["summary"] = ai_video_check(self.gemini, self.url, girl_age, stop)
                except Exception as e:
                    box["error"] = str(e)
            th = threading.Thread(target=ai_pass, daemon=True)
            th.start()
        notes, res, path = list(self.pre_notes), None, None
        if self.frames is not None:
            res, err = self._from_player(stop)
            if res is None and not stop():
                notes.append("הנגן של יוטיוב לא הצליח להריץ את הסרטון (" + err + ") — מנסה להוריד.")
        if res is None and not stop() and not self.pre_notes:
            try:
                path = download_youtube(self.url, self.progress.emit, stop)
            except Exception as e:
                msg = str(e)
                if "418" in msg or "NetFree" in msg:
                    notes.append("גם ההורדה חסומה (נטפרי) — זיהוי האנשים לא בוצע; נשארה בדיקת Gemini מהקישור.")
                elif "Cancelled" in type(e).__name__:
                    notes.append("ההורדה בוטלה.")
                else:
                    notes.append("ההורדה מיוטיוב נכשלה: " + msg[:160])
            if path and not stop():
                self.progress.emit(0, None, "סורק פנים בסרטון…")
                try:
                    res = scan_video(self.engine, self.db, self.st, path, self.progress.emit, stop, self.gemini)
                except Exception as e:
                    notes.append(f"שגיאה בסריקה המקומית: {e}")
        if res is None or "error" in res:
            if res:
                notes.append(res["error"])
            res = {"people": [], "females": [], "duration": 0.0, "stopped": stop()}
        if th is not None:
            while th.is_alive() and not stop():
                self.progress.emit(100, None, "Gemini צופה בסרטון המלא מהקישור…")
                th.join(1.0)
            if "segs" in box:
                for s in box["segs"]:
                    mid = (s["start"] + s["end"]) / 2
                    s["thumb"] = _frame_at(path, mid) if path else (res["snap"](mid) if "snap" in res else None)
                res["females"] = sorted(res["females"] + box["segs"], key=lambda s: s["start"])
                res["ai_summary"] = box.get("summary", "")
            elif "error" in box:
                notes.append("בדיקת Gemini מהקישור נכשלה: " + box["error"][:160])
        res.pop("snap", None)
        res["url"], res["notes"], res["file"] = self.url, notes, path or ""
        self.finished_scan.emit(res)
