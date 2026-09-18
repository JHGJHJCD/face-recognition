"""מסד הנתונים (SQLite) + גלריית הזהויות בזיכרון."""
import json
import os
import sqlite3
import threading
import time

import numpy as np

from .utils import DATA_DIR

DEFAULTS = {
    "camera": 0,
    "threshold": 0.40,          # סף דמיון קוסינוס לזיהוי
    "mirror": True,
    "show_age": True,
    "show_emotion": True,
    "antispoof": True,
    "alert_unknown": True,
    "alert_sound": True,
    "attendance": True,
    "attendance_gap_min": 5,    # הפסקה שאחריה נפתחת רשומת נוכחות חדשה
    "min_face": 60,             # גודל פנים מינימלי (פיקסלים) לזיהוי חי
    "video_step": 1.0,          # שניות בין דגימות בסריקת וידאו
    "auto_learn": True,         # הוספת דגימות לבד כשאדם מזוהה בביטחון גבוה במראה חדש
    "work_start": "",           # שעת התחלה (HH:MM) לחישוב איחורים; ריק = בלי
    "ai_enabled": True,         # Gemini בענן: תיאור סצנה, תיאור לא-מוכרים, עוזר
    "ai_interval": 30,          # שניות בין תיאורי סצנה אוטומטיים
}


class Settings(dict):
    path = os.path.join(DATA_DIR, "settings.json")

    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                self.update(json.load(f))
        except Exception:
            pass

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self, f, ensure_ascii=False, indent=1)


AUTO_SOURCE = "למידה אוטומטית"


def _blob(emb):
    return np.asarray(emb, np.float32).tobytes()


def _emb(blob):
    return np.frombuffer(blob, np.float32)


class Database:
    def __init__(self, model_name="default", path=None):
        self.model = model_name  # וקטורים של מודלים שונים אינם ברי-השוואה
        self.lock = threading.RLock()
        self.path = path or os.path.join(DATA_DIR, "faces.db")
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS persons(id INTEGER PRIMARY KEY, name TEXT NOT NULL, notes TEXT DEFAULT '',
            thumb BLOB, created REAL);
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL, model TEXT,
            emb BLOB NOT NULL, thumb BLOB, source TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL,
            first_seen REAL, last_seen REAL);
        CREATE TABLE IF NOT EXISTS unknown_events(id INTEGER PRIMARY KEY, ts REAL, image TEXT, emb BLOB, model TEXT);
        CREATE TABLE IF NOT EXISTS photos(path TEXT PRIMARY KEY, mtime REAL, faces INTEGER);
        CREATE TABLE IF NOT EXISTS photo_faces(id INTEGER PRIMARY KEY, path TEXT, x1 REAL, y1 REAL, x2 REAL, y2 REAL,
            det REAL, model TEXT, emb BLOB, thumb BLOB, person_id INTEGER, sim REAL, cluster INTEGER);
        CREATE TABLE IF NOT EXISTS ai_notes(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, people TEXT, text TEXT);
        CREATE INDEX IF NOT EXISTS ix_pf_person ON photo_faces(person_id);
        CREATE INDEX IF NOT EXISTS ix_pf_path ON photo_faces(path);
        """)
        for ddl in ("ALTER TABLE unknown_events ADD COLUMN note TEXT DEFAULT ''",
                    "ALTER TABLE persons ADD COLUMN first_name TEXT DEFAULT ''",
                    "ALTER TABLE persons ADD COLUMN last_name TEXT DEFAULT ''",
                    "ALTER TABLE persons ADD COLUMN birth TEXT DEFAULT ''"):      # birth = YYYY-MM-DD
            try:
                self.con.execute(ddl)
            except sqlite3.OperationalError:
                pass
        self.con.commit()
        self.reload_gallery()

    # ---------- גלריה ----------
    def reload_gallery(self):
        with self.lock:
            rows = self.con.execute("SELECT person_id, emb FROM samples WHERE model=?", (self.model,)).fetchall()
            self.names = dict(self.con.execute("SELECT id, name FROM persons").fetchall())
            self.births = dict(self.con.execute("SELECT id, birth FROM persons WHERE birth<>''").fetchall())
        if rows:
            self.g_ids = np.array([r[0] for r in rows], np.int64)
            self.g_embs = np.stack([_emb(r[1]) for r in rows])
        else:
            self.g_ids = np.zeros(0, np.int64)
            self.g_embs = np.zeros((0, 512), np.float32)
        self.g_index = [(int(p), np.where(self.g_ids == p)[0]) for p in np.unique(self.g_ids)]

    def match(self, emb, threshold):
        """מחזיר (person_id | None, דמיון). דמיון לאדם = שילוב שתי הדגימות הקרובות ביותר.
        כששני אנשים שונים קרובים כמעט באותה מידה והציון לא גבוה — עדיף "לא מוכר" מאשר טעות."""
        if len(self.g_ids) == 0:
            return None, 0.0
        sims = self.g_embs @ emb
        scores = []
        for pid, idx in self.g_index:
            v = sims[idx]
            if len(v) == 1:
                scores.append((float(v[0]), pid))
            else:
                top = np.partition(v, -2)[-2:]
                scores.append((float(0.7 * top.max() + 0.3 * top.min()), pid))
        scores.sort(reverse=True)
        best, best_pid = scores[0]
        if best < threshold:
            return None, best
        if len(scores) > 1 and best < 0.55 and best - scores[1][0] < 0.04:
            return None, best
        return best_pid, best

    def person_sims(self, pid, emb):
        idx = next((i for p, i in self.g_index if p == pid), None)
        return self.g_embs[idx] @ emb if idx is not None else np.zeros(0, np.float32)

    def auto_sample_count(self, pid):
        with self.lock:
            return self.con.execute("SELECT COUNT(*) FROM samples WHERE person_id=? AND model=? AND source=?",
                                    (pid, self.model, AUTO_SOURCE)).fetchone()[0]

    def match_many(self, embs, threshold):
        return [self.match(e, threshold) for e in embs]

    # ---------- אנשים ----------
    def add_person(self, name, thumb=None):
        with self.lock:
            cur = self.con.execute("INSERT INTO persons(name, thumb, created) VALUES(?,?,?)", (name.strip(), thumb, time.time()))
            self.con.commit()
        self.reload_gallery()
        return cur.lastrowid

    def age(self, pid, now=None):
        """גיל מדויק לפי תאריך הלידה שהוזן, או None."""
        b = self.births.get(pid)
        if not b:
            return None
        try:
            y, m, d = (int(v) for v in b.split("-"))
        except ValueError:
            return None
        t = time.localtime(now)
        return t.tm_year - y - ((t.tm_mon, t.tm_mday) < (m, d))

    def birthday_today(self, pid):
        b = self.births.get(pid, "")
        return b[5:] == time.strftime("%m-%d")

    def person_info(self, pid):
        with self.lock:
            r = self.con.execute("SELECT name, first_name, last_name, birth, notes FROM persons WHERE id=?", (pid,)).fetchone()
        if not r:
            return None
        first, last = (r[1], r[2]) if (r[1] or r[2]) else (r[0].split(" ", 1) + [""])[:2]
        return {"name": r[0], "first": first, "last": last, "birth": r[3] or "", "notes": r[4] or ""}

    def set_person_info(self, pid, info):
        with self.lock:
            self.con.execute("UPDATE persons SET name=?, first_name=?, last_name=?, birth=?, notes=? WHERE id=?",
                             (info["name"], info["first"], info["last"], info["birth"], info.get("notes", ""), pid))
            self.con.commit()
        self.reload_gallery()

    def merge_persons(self, src, dst):
        """כל הנתונים של src (דגימות, נוכחות, תמונות) עוברים ל-dst ו-src נמחק — לרישום כפול של אותו אדם."""
        if src == dst:
            return
        with self.lock:
            for t in ("samples", "attendance", "photo_faces"):
                self.con.execute(f"UPDATE {t} SET person_id=? WHERE person_id=?", (dst, src))
            self.con.execute("UPDATE persons SET thumb=(SELECT thumb FROM persons WHERE id=?) WHERE id=? AND thumb IS NULL", (src, dst))
            self.con.execute("DELETE FROM persons WHERE id=?", (src,))
            self.con.commit()
        self.reload_gallery()

    def get_or_create(self, info, thumb=None):
        """info = {"name","first","last","birth"} מחלון הפרטים. אדם קיים באותו שם — מתעדכן (תאריך לידה רק אם הוזן)."""
        pid = self.find_person(info["name"])
        if pid is None:
            pid = self.add_person(info["name"], thumb)
        else:   # פרטים שלא הוזנו עכשיו נשמרים מהרישום הקודם
            cur = self.person_info(pid)
            info = dict(info, birth=info["birth"] or cur["birth"], notes=info.get("notes") or cur["notes"])
        self.set_person_info(pid, info)
        return pid

    def find_person(self, name):
        with self.lock:
            r = self.con.execute("SELECT id FROM persons WHERE name=?", (name.strip(),)).fetchone()
        return r[0] if r else None

    def add_sample(self, person_id, emb, thumb=None, source="", reload=True):
        with self.lock:
            self.con.execute("INSERT INTO samples(person_id, model, emb, thumb, source, created) VALUES(?,?,?,?,?,?)",
                             (person_id, self.model, _blob(emb), thumb, source, time.time()))
            if thumb is not None:
                self.con.execute("UPDATE persons SET thumb=? WHERE id=? AND thumb IS NULL", (thumb, person_id))
            self.con.commit()
        if reload:
            self.reload_gallery()

    def persons(self):
        with self.lock:
            return self.con.execute(
                "SELECT p.id, p.name, p.thumb, (SELECT COUNT(*) FROM samples s WHERE s.person_id=p.id AND s.model=?) "
                "FROM persons p ORDER BY p.name", (self.model,)).fetchall()

    def person_samples(self, pid):
        with self.lock:
            return self.con.execute("SELECT id, thumb, source FROM samples WHERE person_id=? AND model=?", (pid, self.model)).fetchall()

    def delete_sample(self, sid):
        with self.lock:
            self.con.execute("DELETE FROM samples WHERE id=?", (sid,))
            self.con.commit()
        self.reload_gallery()

    def rename_person(self, pid, name):
        with self.lock:
            self.con.execute("UPDATE persons SET name=? WHERE id=?", (name.strip(), pid))
            self.con.commit()
        self.reload_gallery()

    def delete_person(self, pid):
        with self.lock:
            self.con.execute("DELETE FROM samples WHERE person_id=?", (pid,))
            self.con.execute("DELETE FROM attendance WHERE person_id=?", (pid,))
            self.con.execute("UPDATE photo_faces SET person_id=NULL, sim=NULL WHERE person_id=?", (pid,))
            self.con.execute("DELETE FROM persons WHERE id=?", (pid,))
            self.con.commit()
        self.reload_gallery()

    # ---------- נוכחות ----------
    def mark_seen(self, pid, gap_min, now=None):
        now = now or time.time()
        with self.lock:
            r = self.con.execute("SELECT id, last_seen FROM attendance WHERE person_id=? ORDER BY last_seen DESC LIMIT 1", (pid,)).fetchone()
            if r and now - r[1] <= gap_min * 60:
                self.con.execute("UPDATE attendance SET last_seen=? WHERE id=?", (now, r[0]))
                new = False
            else:
                self.con.execute("INSERT INTO attendance(person_id, first_seen, last_seen) VALUES(?,?,?)", (pid, now, now))
                new = True
            self.con.commit()
        return new

    def attendance(self, t_from, t_to):
        with self.lock:
            return self.con.execute(
                "SELECT p.name, a.first_seen, a.last_seen FROM attendance a JOIN persons p ON p.id=a.person_id "
                "WHERE a.first_seen>=? AND a.first_seen<? ORDER BY a.first_seen DESC", (t_from, t_to)).fetchall()

    def attendance_rows(self, t_from, t_to):
        """[(id, person_id, name, first, last)] לעריכה ידנית."""
        with self.lock:
            return self.con.execute(
                "SELECT a.id, a.person_id, p.name, a.first_seen, a.last_seen FROM attendance a JOIN persons p ON p.id=a.person_id "
                "WHERE a.first_seen>=? AND a.first_seen<? ORDER BY a.first_seen DESC", (t_from, t_to)).fetchall()

    def add_attendance(self, pid, first, last):
        with self.lock:
            self.con.execute("INSERT INTO attendance(person_id, first_seen, last_seen) VALUES(?,?,?)", (pid, first, max(first, last)))
            self.con.commit()

    def update_attendance(self, aid, first, last):
        with self.lock:
            self.con.execute("UPDATE attendance SET first_seen=?, last_seen=? WHERE id=?", (first, max(first, last), aid))
            self.con.commit()

    def delete_attendance(self, ids):
        with self.lock:
            self.con.executemany("DELETE FROM attendance WHERE id=?", [(int(i),) for i in ids])
            self.con.commit()

    def clear(self, kind, t_from=None, t_to=None):
        """מחיקה מרוכזת: attendance (בטווח או הכול) / photos / ai_notes / unknown / all (הכול חוץ מהגדרות)."""
        with self.lock:
            c = self.con
            if kind == "attendance":
                if t_from is not None:
                    c.execute("DELETE FROM attendance WHERE first_seen>=? AND first_seen<?", (t_from, t_to))
                else:
                    c.execute("DELETE FROM attendance")
            elif kind == "photos":
                c.execute("DELETE FROM photo_faces")
                c.execute("DELETE FROM photos")
            elif kind == "ai_notes":
                c.execute("DELETE FROM ai_notes")
            elif kind == "unknown":
                for (img,) in c.execute("SELECT image FROM unknown_events").fetchall():
                    if img and os.path.exists(img):
                        try:
                            os.remove(img)
                        except OSError:
                            pass
                c.execute("DELETE FROM unknown_events")
            elif kind == "all":
                for t in ("samples", "attendance", "photo_faces", "photos", "ai_notes", "persons"):
                    c.execute(f"DELETE FROM {t}")
                for (img,) in c.execute("SELECT image FROM unknown_events").fetchall():
                    if img and os.path.exists(img):
                        try:
                            os.remove(img)
                        except OSError:
                            pass
                c.execute("DELETE FROM unknown_events")
            c.commit()
            c.execute("VACUUM")
        self.reload_gallery()

    def forget_folder(self, folder):
        """מסיר תיקייה מאינדקס התמונות (התמונות עצמן לא נמחקות)."""
        like = folder.rstrip("\\/") + "%"
        with self.lock:
            n = self.con.execute("SELECT COUNT(*) FROM photos WHERE path LIKE ?", (like,)).fetchone()[0]
            self.con.execute("DELETE FROM photo_faces WHERE path LIKE ?", (like,))
            self.con.execute("DELETE FROM photos WHERE path LIKE ?", (like,))
            self.con.commit()
        return n

    def photo_folders(self):
        """[(תיקייה, מספר תמונות)] — לפי תיקיית-האב הישירה, מקובץ לתיקיות-שורש שנסרקו."""
        with self.lock:
            rows = self.con.execute("SELECT path FROM photos").fetchall()
        counts = {}
        for (p,) in rows:
            counts[os.path.dirname(p)] = counts.get(os.path.dirname(p), 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])

    def purge_unknown(self, days):
        cutoff = time.time() - days * 86400
        with self.lock:
            rows = self.con.execute("SELECT id FROM unknown_events WHERE ts<?", (cutoff,)).fetchall()
        for (eid,) in rows:
            self.delete_unknown(eid)
        return len(rows)

    def stats(self):
        with self.lock:
            q = lambda sql: self.con.execute(sql).fetchone()[0]
            out = {"persons": q("SELECT COUNT(*) FROM persons"), "samples": q("SELECT COUNT(*) FROM samples"),
                   "attendance": q("SELECT COUNT(*) FROM attendance"), "photos": q("SELECT COUNT(*) FROM photos"),
                   "faces": q("SELECT COUNT(*) FROM photo_faces"), "unknown": q("SELECT COUNT(*) FROM unknown_events"),
                   "ai_notes": q("SELECT COUNT(*) FROM ai_notes"),
                   "first_attendance": q("SELECT MIN(first_seen) FROM attendance")}
        try:
            out["db_bytes"] = os.path.getsize(self.path)
        except OSError:
            out["db_bytes"] = 0
        return out

    def backup_to(self, dest_db):
        """עותק עקבי של מסד הנתונים (גם באמצע עבודה) דרך sqlite backup."""
        with self.lock:
            dst = sqlite3.connect(dest_db)
            self.con.backup(dst)
            dst.close()

    def close(self):
        with self.lock:
            self.con.close()

    def attendance_raw(self, t_from, t_to):
        with self.lock:
            return self.con.execute(
                "SELECT a.person_id, p.name, a.first_seen, a.last_seen FROM attendance a JOIN persons p ON p.id=a.person_id "
                "WHERE a.first_seen>=? AND a.first_seen<? ORDER BY a.first_seen", (t_from, t_to)).fetchall()

    def daily_summary(self, t_from, t_to, work_start=""):
        """לכל אדם ולכל יום: הגעה, עזיבה, זמן נוכחות בפועל, מספר כניסות, דקות איחור (או None)."""
        start_min = None
        try:
            hh, mm = work_start.split(":")
            start_min = int(hh) * 60 + int(mm)
        except Exception:
            pass
        days = {}
        for pid, name, first, last in self.attendance_raw(t_from, t_to):
            d = days.setdefault((time.strftime("%Y-%m-%d", time.localtime(first)), pid),
                                {"name": name, "first": first, "last": last, "total": 0.0, "visits": 0})
            d["first"], d["last"] = min(d["first"], first), max(d["last"], last)
            d["total"] += last - first
            d["visits"] += 1
        out = []
        for (day, pid), d in sorted(days.items(), key=lambda kv: (kv[0][0], kv[1]["name"]), reverse=True):
            lt = time.localtime(d["first"])
            late = max(0, lt.tm_hour * 60 + lt.tm_min - start_min) if start_min is not None else None
            out.append({"day": day, "pid": pid, **d, "late": late})
        return out

    def absent(self, t_from, t_to):
        """[(יום, שם)] — אנשים רשומים שלא נראו כלל באותו יום (רק ימים שהמצלמה רשמה בהם מישהו)."""
        seen = {}
        for pid, _, first, _ in self.attendance_raw(t_from, t_to):
            seen.setdefault(time.strftime("%Y-%m-%d", time.localtime(first)), set()).add(pid)
        out = []
        for day in sorted(seen, reverse=True):
            out += [(day, n) for p, n in sorted(self.names.items(), key=lambda x: x[1]) if p not in seen[day]]
        return out

    # ---------- הערות AI ----------
    def add_ai_note(self, kind, people, text):
        with self.lock:
            self.con.execute("INSERT INTO ai_notes(ts, kind, people, text) VALUES(?,?,?,?)", (time.time(), kind, people, text))
            self.con.execute("DELETE FROM ai_notes WHERE ts<?", (time.time() - 60 * 86400,))
            self.con.commit()

    def ai_notes(self, t_from, limit=80):
        with self.lock:
            return self.con.execute("SELECT ts, kind, people, text FROM ai_notes WHERE ts>=? ORDER BY ts DESC LIMIT ?", (t_from, limit)).fetchall()

    def set_unknown_note(self, image, note):
        with self.lock:
            self.con.execute("UPDATE unknown_events SET note=? WHERE image=?", (note, image))
            self.con.commit()

    # ---------- לא מוכרים ----------
    def add_unknown(self, image, emb):
        with self.lock:
            self.con.execute("INSERT INTO unknown_events(ts, image, emb, model) VALUES(?,?,?,?)", (time.time(), image, _blob(emb), self.model))
            self.con.commit()

    def unknown_events(self, limit=200):
        with self.lock:
            return self.con.execute("SELECT id, ts, image, emb, note FROM unknown_events WHERE model=? ORDER BY ts DESC LIMIT ?", (self.model, limit)).fetchall()

    def delete_unknown(self, eid):
        with self.lock:
            r = self.con.execute("SELECT image FROM unknown_events WHERE id=?", (eid,)).fetchone()
            self.con.execute("DELETE FROM unknown_events WHERE id=?", (eid,))
            self.con.commit()
        if r and r[0] and os.path.exists(r[0]):
            try:
                os.remove(r[0])
            except OSError:
                pass

    # ---------- תמונות ----------
    def photo_known(self, path, mtime):
        with self.lock:
            r = self.con.execute("SELECT mtime FROM photos WHERE path=?", (path,)).fetchone()
        return bool(r) and abs(r[0] - mtime) < 1

    def save_photo(self, path, mtime, faces):
        """faces: רשימת (bbox, det, emb, thumb, person_id, sim)"""
        with self.lock:
            self.con.execute("DELETE FROM photo_faces WHERE path=?", (path,))
            self.con.execute("INSERT OR REPLACE INTO photos(path, mtime, faces) VALUES(?,?,?)", (path, mtime, len(faces)))
            for bbox, det, emb, thumb, pid, sim in faces:
                self.con.execute(
                    "INSERT INTO photo_faces(path,x1,y1,x2,y2,det,model,emb,thumb,person_id,sim) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (path, *[float(v) for v in bbox], det, self.model, _blob(emb), thumb, pid, sim))
            self.con.commit()

    def photo_stats(self):
        with self.lock:
            n = self.con.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            f = self.con.execute("SELECT COUNT(*) FROM photo_faces WHERE model=?", (self.model,)).fetchone()[0]
        return n, f

    def rematch_photos(self, threshold):
        """התאמה מחדש של כל הפנים שנסרקו מול הגלריה העדכנית — בלי לסרוק שוב את התמונות."""
        with self.lock:
            rows = self.con.execute("SELECT id, emb FROM photo_faces WHERE model=?", (self.model,)).fetchall()
            for fid, blob in rows:
                pid, sim = self.match(_emb(blob), threshold)
                self.con.execute("UPDATE photo_faces SET person_id=?, sim=? WHERE id=?", (pid, sim, fid))
            self.con.commit()
        return len(rows)

    def photo_people(self):
        with self.lock:
            return self.con.execute(
                "SELECT p.id, p.name, p.thumb, COUNT(DISTINCT f.path) FROM photo_faces f JOIN persons p ON p.id=f.person_id "
                "WHERE f.model=? GROUP BY p.id ORDER BY 4 DESC", (self.model,)).fetchall()

    def photos_of(self, pid):
        with self.lock:
            return self.con.execute(
                "SELECT path, MAX(sim), thumb FROM photo_faces WHERE person_id=? AND model=? GROUP BY path ORDER BY path", (pid, self.model)).fetchall()

    def unassigned_faces(self, min_det=0.6, min_size=50):
        with self.lock:
            rows = self.con.execute(
                "SELECT id, path, emb, thumb, (x2-x1) FROM photo_faces WHERE person_id IS NULL AND model=? AND det>=? AND (x2-x1)>=?",
                (self.model, min_det, min_size)).fetchall()
        return rows

    def face_rows(self, ids):
        with self.lock:
            q = ",".join("?" * len(ids))
            return self.con.execute(f"SELECT id, path, emb, thumb FROM photo_faces WHERE id IN ({q})", list(ids)).fetchall()


def cluster_embeddings(embs, threshold=0.5, min_size=3):
    """קיבוץ פנים לא-מזוהות לאנשים (Chinese Whispers על גרף דמיון) — מחזיר רשימת קבוצות אינדקסים."""
    n = len(embs)
    if n == 0:
        return []
    E = np.asarray(embs, np.float32)
    labels = np.arange(n)
    nbrs = []
    for i in range(0, n, 512):
        S = E[i:i + 512] @ E.T
        for r, row in enumerate(S):
            idx = np.where(row >= threshold)[0]
            idx = idx[idx != i + r]
            nbrs.append((idx, row[idx]))
    rng = np.random.default_rng(0)
    for _ in range(15):
        changed = 0
        for i in rng.permutation(n):
            idx, w = nbrs[i]
            if len(idx) == 0:
                continue
            votes = {}
            for j, wt in zip(labels[idx], w):
                votes[j] = votes.get(j, 0.0) + float(wt)
            best = max(votes, key=votes.get)
            if best != labels[i]:
                labels[i] = best
                changed += 1
        if not changed:
            break
    groups = {}
    for i, l in enumerate(labels):
        groups.setdefault(int(l), []).append(i)
    out = [g for g in groups.values() if len(g) >= min_size]
    out.sort(key=len, reverse=True)
    return out
