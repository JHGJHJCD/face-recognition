"""לשוניות התוכנה: זיהוי חי, אנשים, תמונות, וידאו, נוכחות, הגדרות."""
import os
import shutil
import time
import winsound

import numpy as np
from PyQt6.QtCore import QDate, QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QLineEdit,
                             QPlainTextEdit, QTextBrowser, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QHeaderView, QInputDialog, QLabel, QListWidget, QMessageBox, QProgressBar,
                             QPushButton, QSlider, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from core import ai
from core.db import cluster_embeddings
from core.jobs import PhotoScanWorker, VideoScanWorker, enroll_from_image
from core.live import LiveWorker
from core.utils import IMAGE_EXT, VIDEO_EXT, crop_square, fmt_time, imread, jpg_bytes
from .widgets import FuncThread, ThumbList, VideoWidget, pixmap_from_jpg


def btn(text, slot, kind=None):
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    b.clicked.connect(slot)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def label(text, kind=None, wrap=False):
    lb = QLabel(text)
    if kind:
        lb.setObjectName(kind)
    lb.setWordWrap(wrap)
    return lb


def ask_person(parent, title="פרטי האדם", info=None):
    """חלון פרטים: שם פרטי, שם משפחה, תאריך לידה (לא חובה). מחזיר {"name","first","last","birth"} או None."""
    info = info or {"first": "", "last": "", "birth": ""}
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(420)
    first, last = QLineEdit(info["first"]), QLineEdit(info["last"])
    known = QCheckBox("תאריך לידה ידוע (הגיל יחושב ממנו במקום הערכה)")
    birth = QDateEdit(QDate.fromString(info["birth"], "yyyy-MM-dd") if info["birth"] else QDate(2000, 1, 1))
    birth.setLayoutDirection(Qt.LayoutDirection.LeftToRight)   # לפני הפורמט — אחרת Qt הופך את סדר יום/חודש/שנה ב-RTL
    birth.setDisplayFormat("dd/MM/yyyy")
    birth.setCalendarPopup(True)
    birth.setMaximumDate(QDate.currentDate())
    known.setChecked(bool(info["birth"]))
    birth.setEnabled(bool(info["birth"]))
    known.toggled.connect(birth.setEnabled)
    err = label("", "muted")
    form = QFormLayout()
    form.setVerticalSpacing(12)
    form.addRow("שם פרטי", first)
    form.addRow("שם משפחה", last)
    form.addRow("", known)
    form.addRow("תאריך לידה", birth)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("אישור")
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")

    def ok():
        if not first.text().strip() or not last.text().strip():
            err.setText("יש למלא שם פרטי ושם משפחה.")
            return
        dlg.accept()

    bb.accepted.connect(ok)
    bb.rejected.connect(dlg.reject)
    v = QVBoxLayout(dlg)
    v.addLayout(form)
    v.addWidget(err)
    v.addWidget(bb)
    if not dlg.exec():
        return None
    f, la = " ".join(first.text().split()), " ".join(last.text().split())
    return {"name": f"{f} {la}", "first": f, "last": la, "birth": birth.date().toString("yyyy-MM-dd") if known.isChecked() else ""}


def export_xlsx(parent, headers, rows, default_name):
    path, _ = QFileDialog.getSaveFileName(parent, "שמירה לאקסל", default_name, "Excel (*.xlsx)")
    if not path:
        return
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(list(r))
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22
    wb.save(path)
    os.startfile(path)


# ======================================================================
class LiveTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.worker = None
        self.video = VideoWidget()
        self.fps_lbl = label("", "muted")
        self.start_btn = btn("▶  הפעל מצלמה", self.toggle, "primary")
        self.enroll_btn = btn("➕  רישום אדם חדש מהמצלמה", self.enroll)
        self.enroll_btn.setEnabled(False)
        self.enroll_bar = QProgressBar()
        self.enroll_msg = label("", "muted", wrap=True)
        self.enroll_bar.hide()
        self.events = ThumbList(icon=56, grid=False)
        self.ai_lbl = label("", "card", wrap=True)
        self.ai_lbl.hide()

        side = QVBoxLayout()
        side.addWidget(self.start_btn)
        side.addWidget(self.enroll_btn)
        side.addWidget(self.enroll_bar)
        side.addWidget(self.enroll_msg)
        side.addWidget(self.ai_lbl)
        side.addSpacing(8)
        side.addWidget(label("אירועים אחרונים", "h1"))
        side.addWidget(self.events, 1)
        side.addWidget(self.fps_lbl)
        sidew = QWidget()
        sidew.setLayout(side)
        sidew.setFixedWidth(320)
        lay = QHBoxLayout(self)
        lay.addWidget(sidew)
        lay.addWidget(self.video, 1)

    def toggle(self):
        if self.worker:
            self.stop()
            return
        self.worker = LiveWorker(self.app.engine, self.app.db, self.app.settings, self.app.ai)
        self.worker.ai_note.connect(self.on_ai)
        self.worker.learned.connect(lambda n: self._event(f"{n}\nלמדתי מראה חדש · {time.strftime('%H:%M')}", None))
        self.worker.frame_ready.connect(self.on_frame)
        self.worker.unknown_alert.connect(self.on_unknown)
        self.worker.person_seen.connect(self.on_seen)
        self.worker.enroll_progress.connect(self.on_enroll_progress)
        self.worker.enroll_done.connect(self.on_enroll_done)
        self.worker.failed.connect(self.on_failed)
        self.video.message = "פותח מצלמה…"
        self.video.update()
        self.worker.start()
        self.start_btn.setText("■  עצור מצלמה")
        self.enroll_btn.setEnabled(True)

    def stop(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.video.message = "המצלמה כבויה"
        self.video.set_frame(None, [])
        self.start_btn.setText("▶  הפעל מצלמה")
        self.enroll_btn.setEnabled(False)
        self.enroll_bar.hide()
        self.enroll_msg.setText("")
        self.ai_lbl.hide()
        self.fps_lbl.setText("")

    def on_frame(self, frame, labels, fps):
        self.video.set_frame(frame, labels)
        self.fps_lbl.setText(f"{fps:.0f} תמונות בשנייה · {len(labels)} פנים")

    def on_ai(self, kind, text):
        if kind == "error":
            self.ai_lbl.setToolTip(text)
            return
        if kind == "unknown":
            self.app.people_tab.refresh_unknown()
            text = "אדם לא מוכר: " + text
        self.ai_lbl.setText(f"🤖 {time.strftime('%H:%M:%S')}\n{text}")
        self.ai_lbl.show()

    def on_failed(self, msg):
        self.stop()
        QMessageBox.warning(self, "מצלמה", msg)

    def _event(self, text, jpg):
        self.events.add(text, jpg)
        self.events.insertItem(0, self.events.takeItem(self.events.count() - 1))
        while self.events.count() > 60:
            self.events.takeItem(self.events.count() - 1)

    def on_seen(self, name):
        pid, thumb = next(((p, t) for p, n, t, _ in self.app.db.persons() if n == name), (None, None))
        cake = "🎂 יום הולדת היום! · " if pid is not None and self.app.db.birthday_today(pid) else ""
        self._event(f"{name}\n{cake}נרשם ביומן · {time.strftime('%H:%M')}", thumb)
        self.app.attendance_tab.refresh()

    def on_unknown(self, path):
        try:
            with open(path, "rb") as f:
                jpg = f.read()
        except OSError:
            jpg = None
        self._event(f"⚠ אדם לא מוכר\n{time.strftime('%H:%M:%S')}", jpg)
        if self.app.settings["alert_sound"]:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        self.app.people_tab.refresh_unknown()

    def enroll(self):
        if not self.worker:
            return
        if self.worker._enroll is not None:
            self.worker.cancel_enroll()
            self.on_enroll_done(False, "")
            return
        info = ask_person(self, "רישום אדם חדש")
        if not info:
            return
        name = info["name"]
        self.enroll_bar.setRange(0, 8)
        self.enroll_bar.setValue(0)
        self.enroll_bar.show()
        self.enroll_msg.setText(f"רושם את {name}: הבט למצלמה והזז מעט את הראש לצדדים")
        self.enroll_btn.setText("✖  בטל רישום")
        self.worker.start_enroll(info)

    def on_enroll_progress(self, n, total, msg):
        self.enroll_bar.setRange(0, total)
        self.enroll_bar.setValue(n)
        self.enroll_msg.setText(msg)

    def on_enroll_done(self, ok, text):
        self.enroll_bar.hide()
        self.enroll_btn.setText("➕  רישום אדם חדש מהמצלמה")
        self.enroll_msg.setText(f"✔ {text} נרשם בהצלחה" if ok else text)
        if ok:
            self.app.people_tab.refresh()


# ======================================================================
class PeopleTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.people = ThumbList(icon=110)
        self.samples = ThumbList(icon=72)
        self.unknown = ThumbList(icon=96)
        self.people.currentItemChanged.connect(lambda *_: self.show_samples())

        top = QHBoxLayout()
        top.addWidget(btn("➕  אדם חדש מתמונות", self.add_from_files, "primary"))
        top.addWidget(btn("🖼  הוסף תמונות לאדם", self.add_more))
        top.addWidget(btn("✏  ערוך פרטים", self.rename))
        top.addWidget(btn("🗑  מחק אדם", self.delete, "danger"))
        top.addStretch()

        left = QVBoxLayout()
        left.addLayout(top)
        left.addWidget(label("אנשים רשומים", "h1"))
        left.addWidget(self.people, 3)
        self.samples_title = label("דגימות הפנים של האדם הנבחר", "muted")
        srow = QHBoxLayout()
        srow.addWidget(self.samples_title)
        srow.addStretch()
        srow.addWidget(btn("מחק דגימה", self.delete_sample))
        left.addLayout(srow)
        left.addWidget(self.samples, 1)

        right = QVBoxLayout()
        right.addWidget(label("לא מוכרים שנקלטו במצלמה", "h1"))
        right.addWidget(label("בחר תמונה ותן לה שם — והאדם יזוהה מעכשיו.", "muted", wrap=True))
        right.addWidget(self.unknown, 1)
        self.unknown_note = label("", "card", wrap=True)
        self.unknown_note.hide()
        right.addWidget(self.unknown_note)
        self.unknown.currentItemChanged.connect(self._show_note)
        urow = QHBoxLayout()
        urow.addWidget(btn("תן שם", self.name_unknown, "primary"))
        urow.addWidget(btn("מחק", self.delete_unknown))
        urow.addWidget(btn("מחק הכל", self.clear_unknown))
        right.addLayout(urow)

        lw, rw = QWidget(), QWidget()
        lw.setLayout(left)
        rw.setLayout(right)
        rw.setFixedWidth(380)
        lay = QHBoxLayout(self)
        lay.addWidget(rw)
        lay.addWidget(lw, 1)

    def refresh(self):
        cur = self.people.current_data()
        self.people.clear()
        for pid, name, thumb, n in self.app.db.persons():
            age = self.app.db.age(pid)
            it = self.people.add(f"{name}\n" + (f"גיל {age} · " if age is not None else "") + f"{n} דגימות", thumb, pid)
            if pid == cur:
                self.people.setCurrentItem(it)
        self.show_samples()
        self.refresh_unknown()

    def refresh_unknown(self):
        self.unknown.clear()
        for eid, ts, image, emb, note in self.app.db.unknown_events():
            jpg = None
            if image and os.path.exists(image):
                with open(image, "rb") as f:
                    jpg = f.read()
            it = self.unknown.add(time.strftime("%d/%m %H:%M", time.localtime(ts)) + (" 🤖" if note else ""), jpg, (eid, emb, jpg))
            if note:
                it.setToolTip(note)

    def _show_note(self, it, _=None):
        note = it.toolTip() if it else ""
        self.unknown_note.setText("🤖 " + note)
        self.unknown_note.setVisible(bool(note))

    def show_samples(self):
        self.samples.clear()
        pid = self.people.current_data()
        if pid is None:
            return
        for sid, thumb, source in self.app.db.person_samples(pid):
            self.samples.add(source or "", thumb, sid)

    def _enroll_files(self, pid, files):
        ok = 0
        for path in files:
            img = imread(path, 1920)
            if img is None:
                continue
            f = enroll_from_image(self.app.engine, img)
            if f is None or f.size < 40:
                continue
            self.app.db.add_sample(pid, f.emb, jpg_bytes(crop_square(img, f.bbox)), os.path.basename(path), reload=False)
            ok += 1
        self.app.db.reload_gallery()
        return ok

    def _pick_images(self):
        ext = " ".join("*" + e for e in sorted(IMAGE_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, "בחר תמונות של האדם (עדיף 3–10 תמונות ברורות)", "", f"תמונות ({ext})")
        return files

    def add_from_files(self):
        info = ask_person(self, "אדם חדש")
        if not info:
            return
        name = info["name"]
        files = self._pick_images()
        if not files:
            return
        pid = self.app.db.get_or_create(info)
        n = self._enroll_files(pid, files)
        if n == 0 and not self.app.db.person_samples(pid):
            self.app.db.delete_person(pid)
            QMessageBox.warning(self, "רישום", "לא נמצאו פנים ברורות בתמונות שנבחרו.")
        else:
            QMessageBox.information(self, "רישום", f"{name} נרשם עם {n} תמונות.\nבתמונה עם כמה אנשים נלקחות הפנים הגדולות ביותר.")
        self.refresh()
        self.app.after_gallery_change()

    def add_more(self):
        pid = self.people.current_data()
        if pid is None:
            QMessageBox.information(self, "הוספת תמונות", "בחר קודם אדם מהרשימה.")
            return
        files = self._pick_images()
        if files:
            n = self._enroll_files(pid, files)
            QMessageBox.information(self, "הוספת תמונות", f"נוספו {n} דגימות.")
            self.refresh()
            self.app.after_gallery_change()

    def rename(self):
        pid = self.people.current_data()
        if pid is None:
            return
        info = ask_person(self, "עריכת פרטים", self.app.db.person_info(pid))
        if info:
            self.app.db.set_person_info(pid, info)
            self.refresh()

    def delete(self):
        pid = self.people.current_data()
        if pid is None:
            return
        name = self.app.db.names.get(pid, "")
        if QMessageBox.question(self, "מחיקה", f"למחוק את {name} וכל הנתונים שלו?") == QMessageBox.StandardButton.Yes:
            self.app.db.delete_person(pid)
            self.refresh()
            self.app.after_gallery_change()

    def delete_sample(self):
        sid = self.samples.current_data()
        if sid is not None:
            self.app.db.delete_sample(sid)
            self.refresh()

    def name_unknown(self):
        d = self.unknown.current_data()
        if not d:
            return
        info = ask_person(self, "מי זה?")
        if not info:
            return
        eid, emb, jpg = d
        pid = self.app.db.get_or_create(info, jpg)
        self.app.db.add_sample(pid, np.frombuffer(emb, np.float32), jpg, "מצלמה")
        self.app.db.delete_unknown(eid)
        self.refresh()
        self.app.after_gallery_change()

    def delete_unknown(self):
        d = self.unknown.current_data()
        if d:
            self.app.db.delete_unknown(d[0])
            self.refresh_unknown()

    def clear_unknown(self):
        if QMessageBox.question(self, "מחיקה", "למחוק את כל הלא-מוכרים שנקלטו?") == QMessageBox.StandardButton.Yes:
            for eid, *_ in self.app.db.unknown_events(100000):
                self.app.db.delete_unknown(eid)
            self.refresh_unknown()


# ======================================================================
class PhotosTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.worker = None
        self.thread = None
        self.clusters = []
        self.scan_btn = btn("📁  בחר תיקייה וסרוק", self.scan, "primary")
        self.cluster_btn = btn("🔍  מצא אנשים שעדיין לא רשומים", self.find_clusters)
        self.bar = QProgressBar()
        self.bar.hide()
        self.status = label("", "muted")
        self.people = ThumbList(icon=64, grid=False)
        self.people.currentItemChanged.connect(lambda *_: self.show_photos())
        self.grid = ThumbList(icon=112)
        self.grid.itemDoubleClicked.connect(self.open_photo)
        self.title = label("", "h1")
        self.copy_btn = btn("📋  העתק את התמונות לתיקייה", self.copy_photos)
        self.name_btn = btn("✔  תן שם לקבוצה", self.name_cluster, "primary")
        self.name_btn.hide()

        top = QHBoxLayout()
        top.addWidget(self.scan_btn)
        top.addWidget(self.cluster_btn)
        top.addWidget(self.bar, 1)
        top.addWidget(self.status)
        left = QVBoxLayout()
        left.addWidget(label("מי מופיע בתמונות", "h1"))
        left.addWidget(self.people)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(300)
        right = QVBoxLayout()
        hrow = QHBoxLayout()
        hrow.addWidget(self.title)
        hrow.addStretch()
        hrow.addWidget(self.name_btn)
        hrow.addWidget(self.copy_btn)
        right.addLayout(hrow)
        right.addWidget(self.grid)
        right.addWidget(label("לחיצה כפולה פותחת את התמונה המלאה.", "muted"))
        body = QHBoxLayout()
        body.addWidget(lw)
        body.addLayout(right, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(body, 1)

    def refresh(self):
        n, f = self.app.db.photo_stats()
        self.status.setText(f"נסרקו {n:,} תמונות · {f:,} פנים")
        cur = self.people.current_data()
        self.people.clear()
        for pid, name, thumb, cnt in self.app.db.photo_people():
            it = self.people.add(f"{name}\n{cnt} תמונות", thumb, ("p", pid))
            if cur == ("p", pid):
                self.people.setCurrentItem(it)
        for i, c in enumerate(self.clusters):
            self.people.add(f"לא רשום #{i + 1}\n{len(c['ids'])} הופעות", c["thumb"], ("c", i))
        self.show_photos()

    def scan(self):
        if self.worker:
            self.worker.stop_flag = True
            return
        folder = QFileDialog.getExistingDirectory(self, "בחר תיקיית תמונות", os.path.expanduser("~\\Pictures"))
        if not folder:
            return
        self.worker = PhotoScanWorker(self.app.engine, self.app.db, self.app.settings, folder)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished_scan.connect(self.on_done)
        self.bar.setValue(0)
        self.bar.show()
        self.scan_btn.setText("■  עצור סריקה")
        self.worker.start()

    def on_progress(self, i, n, path):
        self.bar.setRange(0, n)
        self.bar.setValue(i)
        self.status.setText(f"{i:,} / {n:,} · {os.path.basename(path)}")

    def on_done(self, new, faces):
        self.worker = None
        self.bar.hide()
        self.scan_btn.setText("📁  בחר תיקייה וסרוק")
        self.refresh()
        QMessageBox.information(self, "סריקה", f"נסרקו {new:,} תמונות חדשות ונמצאו בהן {faces:,} פנים.\n"
                                "כדי לגלות אנשים שעדיין לא רשומים לחץ על ״מצא אנשים שעדיין לא רשומים״.")

    def find_clusters(self):
        if self.thread:
            return
        self.cluster_btn.setEnabled(False)
        self.status.setText("מקבץ פנים דומות…")

        def work():
            rows = self.app.db.unassigned_faces()
            embs = [np.frombuffer(r[2], np.float32) for r in rows]
            out = []
            for g in cluster_embeddings(embs, 0.5, min_size=4)[:60]:
                g = sorted(g, key=lambda i: -rows[i][4])
                out.append({"ids": [rows[i][0] for i in g], "thumb": rows[g[0]][3]})
            return out

        self.thread = FuncThread(work)
        self.thread.done.connect(self.on_clusters)
        self.thread.start()

    def on_clusters(self, res):
        self.thread = None
        self.cluster_btn.setEnabled(True)
        self.clusters = res if isinstance(res, list) else []
        self.refresh()
        if not self.clusters:
            QMessageBox.information(self, "קיבוץ", "לא נמצאו קבוצות של אנשים לא רשומים (נדרשות לפחות 4 הופעות).")

    def show_photos(self):
        self.grid.clear()
        d = self.people.current_data()
        self.name_btn.setVisible(bool(d) and d[0] == "c")
        if not d:
            self.title.setText("")
            return
        if d[0] == "p":
            rows = self.app.db.photos_of(d[1])
            self.title.setText(f"{self.app.db.names.get(d[1], '')} — {len(rows)} תמונות")
            for path, sim, thumb in rows[:1500]:
                self.grid.add(os.path.basename(path), thumb, path)
        else:
            c = self.clusters[d[1]]
            self.title.setText(f"אדם לא רשום #{d[1] + 1} — {len(c['ids'])} הופעות")
            for fid, path, emb, thumb in self.app.db.face_rows(c["ids"][:600]):
                self.grid.add(os.path.basename(path), thumb, path)

    def open_photo(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            os.startfile(path)

    def name_cluster(self):
        d = self.people.current_data()
        if not d or d[0] != "c":
            return
        info = ask_person(self, "מי זה?")
        if not info:
            return
        c = self.clusters.pop(d[1])
        pid = self.app.db.get_or_create(info, c["thumb"])
        for fid, path, emb, thumb in self.app.db.face_rows(c["ids"][:12]):
            self.app.db.add_sample(pid, np.frombuffer(emb, np.float32), thumb, os.path.basename(path), reload=False)
        self.app.db.reload_gallery()
        self.app.people_tab.refresh()
        self.app.after_gallery_change()

    def copy_photos(self):
        paths = sorted({self.grid.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.grid.count())})
        if not paths:
            return
        dest = QFileDialog.getExistingDirectory(self, "לאן להעתיק?")
        if not dest:
            return
        n = 0
        for p in paths:
            if os.path.exists(p):
                target = os.path.join(dest, os.path.basename(p))
                k = 1
                while os.path.exists(target):
                    b, e = os.path.splitext(os.path.basename(p))
                    target = os.path.join(dest, f"{b} ({k}){e}")
                    k += 1
                shutil.copy2(p, target)
                n += 1
        QMessageBox.information(self, "העתקה", f"הועתקו {n} תמונות. המקור לא השתנה.")
        os.startfile(dest)


# ======================================================================
class VideoTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.worker = None
        self.result = None
        self.scan_btn = btn("🎬  בחר סרטון וסרוק", self.scan, "primary")
        self.bar = QProgressBar()
        self.bar.hide()
        self.status = label("בחר קובץ וידאו כדי לגלות מי מופיע בו ובאילו דקות.", "muted")
        self.preview = VideoWidget()
        self.preview.message = ""
        self.preview.setMinimumSize(320, 200)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "שם", "זמן מסך", "מופיע בדקות"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 72)
        self.table.setColumnWidth(1, 200)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        top = QHBoxLayout()
        top.addWidget(self.scan_btn)
        top.addWidget(self.bar, 1)
        top.addWidget(btn("תן שם ללא-מוכר", self.name_unknown))
        top.addWidget(btn("📊  ייצוא לאקסל", self.export))
        split = QSplitter()
        split.addWidget(self.table)
        split.addWidget(self.preview)
        split.setSizes([700, 400])
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.status)
        lay.addWidget(split, 1)

    def scan(self):
        if self.worker:
            self.worker.stop_flag = True
            return
        ext = " ".join("*" + e for e in sorted(VIDEO_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "בחר סרטון", os.path.expanduser("~\\Videos"), f"וידאו ({ext})")
        if not path:
            return
        self.path = path
        self.worker = VideoScanWorker(self.app.engine, self.app.db, self.app.settings, path)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished_scan.connect(self.on_done)
        self.table.setRowCount(0)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText(f"סורק: {os.path.basename(path)}")
        self.scan_btn.setText("■  עצור סריקה")
        self.worker.start()

    def on_progress(self, pct, frame):
        self.bar.setValue(pct)
        if frame is not None:
            self.preview.set_frame(frame, [])

    def on_done(self, res):
        self.worker = None
        self.bar.hide()
        self.scan_btn.setText("🎬  בחר סרטון וסרוק")
        if "error" in res:
            self.status.setText(res["error"])
            return
        self.result = res
        self.status.setText(f"{os.path.basename(self.path)} · אורך {fmt_time(res['duration'])} · נמצאו {len(res['people'])} אנשים")
        self.fill()

    def fill(self):
        people = self.result["people"]
        self.table.setRowCount(len(people))
        for r, p in enumerate(people):
            it = QTableWidgetItem()
            it.setIcon(QIcon(pixmap_from_jpg(p["thumb"], 56)))
            self.table.setItem(r, 0, it)
            self.table.setItem(r, 1, QTableWidgetItem(p["name"]))
            self.table.setItem(r, 2, QTableWidgetItem(fmt_time(p["total"])))
            self.table.setItem(r, 3, QTableWidgetItem("  ,  ".join(f"{fmt_time(a)}–{fmt_time(b)}" for a, b in p["ranges"])))
            self.table.setRowHeight(r, 62)
        self.table.setIconSize(QSize(56, 56))

    def name_unknown(self):
        r = self.table.currentRow()
        if not self.result or r < 0 or self.result["people"][r]["known"]:
            QMessageBox.information(self, "מתן שם", "בחר בטבלה שורה של אדם לא מוכר.")
            return
        info = ask_person(self, "מי זה?")
        if not info:
            return
        name = info["name"]
        p = self.result["people"][r]
        pid = self.app.db.get_or_create(info, p["thumb"])
        for e, t in zip(p["embs"], p["thumbs"]):
            self.app.db.add_sample(pid, e, t, "וידאו", reload=False)
        self.app.db.reload_gallery()
        p["name"], p["known"] = name, True
        self.fill()
        self.app.people_tab.refresh()
        self.app.after_gallery_change()

    def export(self):
        if not self.result:
            return
        rows = [(p["name"], fmt_time(p["total"]), ", ".join(f"{fmt_time(a)}-{fmt_time(b)}" for a, b in p["ranges"])) for p in self.result["people"]]
        export_xlsx(self, ["שם", "זמן מסך", "טווחי זמן"], rows, "מי בסרטון.xlsx")


# ======================================================================
class AttendanceTab(QWidget):
    VIEWS = ["סיכום יומי", "רשומות מפורטות", "סיכום לתקופה", "נעדרים"]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.d_from = QDateEdit(QDate.currentDate())
        self.d_to = QDateEdit(QDate.currentDate())
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setLayoutDirection(Qt.LayoutDirection.LeftToRight)   # לפני הפורמט — אחרת Qt הופך את סדר יום/חודש/שנה ב-RTL
            d.setDisplayFormat("dd/MM/yyyy")
            d.dateChanged.connect(self.refresh)
        self.view = QComboBox()
        self.view.addItems(self.VIEWS)
        self.view.currentIndexChanged.connect(self.refresh)
        self.table = QTableWidget(0, 0)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.summary = label("", "muted")
        top = QHBoxLayout()
        top.addWidget(label("תצוגה"))
        top.addWidget(self.view)
        top.addWidget(label("מתאריך"))
        top.addWidget(self.d_from)
        top.addWidget(label("עד תאריך"))
        top.addWidget(self.d_to)
        top.addWidget(btn("היום", self.today))
        top.addWidget(btn("השבוע", lambda: self.span(6)))
        top.addWidget(btn("30 יום", lambda: self.span(29)))
        top.addStretch()
        top.addWidget(self.summary)
        top.addWidget(btn("📊  ייצוא לאקסל", self.export, "primary"))
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table)

    def today(self):
        self.span(0)

    def span(self, days_back):
        self.d_from.setDate(QDate.currentDate().addDays(-days_back))
        self.d_to.setDate(QDate.currentDate())

    def _range(self):
        a, b = self.d_from.date(), self.d_to.date().addDays(1)
        return (time.mktime((a.year(), a.month(), a.day(), 0, 0, 0, 0, 0, -1)),
                time.mktime((b.year(), b.month(), b.day(), 0, 0, 0, 0, 0, -1)))

    @staticmethod
    def _day(day):
        return f"{day[8:10]}/{day[5:7]}/{day[:4]}"

    def data(self):
        """(כותרות, שורות) של התצוגה הנוכחית."""
        t0, t1 = self._range()
        db, v = self.app.db, self.view.currentIndex()

        def hm(t):
            return time.strftime("%H:%M", time.localtime(t))

        if v == 1:
            rows = []
            for name, first, last in db.attendance(t0, t1):
                rows.append((name, time.strftime("%d/%m/%Y", time.localtime(first)), time.strftime("%H:%M:%S", time.localtime(first)),
                             time.strftime("%H:%M:%S", time.localtime(last)), fmt_time(last - first)))
            return ["שם", "תאריך", "נראה לראשונה", "נראה לאחרונה", "משך"], rows
        if v == 3:
            return ["תאריך", "שם"], [(self._day(d), n) for d, n in db.absent(t0, t1)]
        days = db.daily_summary(t0, t1, self.app.settings["work_start"])

        def late(d):
            return "" if d["late"] is None else ("בזמן" if d["late"] == 0 else f"{d['late']} דק׳")

        if v == 0:
            return (["שם", "תאריך", "הגעה", "עזיבה", "זמן נוכחות בפועל", "כניסות", "איחור"],
                    [(d["name"], self._day(d["day"]), hm(d["first"]), hm(d["last"]), fmt_time(d["total"]), str(d["visits"]), late(d)) for d in days])
        per = {}
        for d in days:
            p = per.setdefault(d["pid"], {"name": d["name"], "days": 0, "total": 0.0, "late": 0, "first": []})
            p["days"] += 1
            p["total"] += d["total"]
            p["late"] += 1 if d["late"] else 0
            lt = time.localtime(d["first"])
            p["first"].append(lt.tm_hour * 60 + lt.tm_min)
        rows = []
        for p in sorted(per.values(), key=lambda x: x["name"]):
            avg = int(sum(p["first"]) / len(p["first"]))
            rows.append((p["name"], str(p["days"]), fmt_time(p["total"]), f"{avg // 60:02d}:{avg % 60:02d}", str(p["late"])))
        return ["שם", "ימי נוכחות", "סך זמן נוכחות", "שעת הגעה ממוצעת", "מספר איחורים"], rows

    def rows(self):
        return self.data()[1]

    def refresh(self, *_):
        headers, rows = self.data()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(v))
        names = {r[1] if self.view.currentIndex() == 3 else r[0] for r in rows}
        self.summary.setText(f"{len(rows)} שורות · {len(names)} אנשים")

    def export(self):
        headers, rows = self.data()
        export_xlsx(self, headers, rows, f"נוכחות - {self.view.currentText()}.xlsx")


# ======================================================================
class AssistantTab(QWidget):
    QUICK = ["סכם לי את היום", "מי נעדר היום?", "מה קורה עכשיו מול המצלמה?", "מי איחר השבוע?", "היו אנשים לא מוכרים לאחרונה?"]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.thread = None
        self.history = []
        self.chat = QTextBrowser()
        self.chat.setStyleSheet("font-size: 15px; background: #111c33; border-radius: 10px; padding: 8px;")
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("שאל כל שאלה בעברית — על הנוכחות, על האנשים, על מה שהמצלמה רואה…")
        self.inp.setMinimumHeight(40)
        self.inp.returnPressed.connect(self.send)
        self.send_btn = btn("שלח", self.send, "primary")
        quick = QHBoxLayout()
        for q in self.QUICK:
            quick.addWidget(btn(q, lambda _=False, q=q: self.send(q)))
        quick.addStretch()
        row = QHBoxLayout()
        row.addWidget(self.inp, 1)
        row.addWidget(self.send_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(label("עוזר AI", "h1"))
        lay.addWidget(label("העוזר רואה את יומן הנוכחות, רשימת האנשים, הלא-מוכרים, ההערות שה-AI רשם — וגם את תמונת המצלמה כשהיא פועלת. "
                            "השאלות והנתונים נשלחים ל-Gemini של גוגל.", "muted", wrap=True))
        lay.addWidget(self.chat, 1)
        lay.addLayout(quick)
        lay.addLayout(row)

    def _say(self, who, text, color):
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
        self.chat.append(f'<div dir="rtl" style="margin:6px 0"><b style="color:{color}">{who}</b><br>{text}</div>')
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def context(self):
        db, now = self.app.db, time.time()

        def dt(t):
            return time.strftime("%d/%m %H:%M", time.localtime(t))

        L = [f"עכשיו: {time.strftime('%d/%m/%Y %H:%M')}",
             "אנשים רשומים: " + (", ".join(sorted(n + (f" (גיל {db.age(p)}, נולד {db.births[p]})" if p in db.births else "")
                                                 for p, n in db.names.items())) or "אין"),
             f"שעת התחלה לחישוב איחורים: {self.app.settings['work_start'] or 'לא הוגדרה'}", "",
             "נוכחות ב-14 הימים האחרונים (יום | שם | הגעה | עזיבה | זמן בפועל | כניסות | דקות איחור):"]
        for d in db.daily_summary(now - 14 * 86400, now + 1, self.app.settings["work_start"])[:300]:
            L.append(f"{d['day']} | {d['name']} | {time.strftime('%H:%M', time.localtime(d['first']))} | {time.strftime('%H:%M', time.localtime(d['last']))}"
                     f" | {fmt_time(d['total'])} | {d['visits']} | {'' if d['late'] is None else d['late']}")
        L += ["", "אנשים לא מוכרים שנקלטו (זמן | תיאור):"]
        L += [f"{dt(ts)} | {note or 'אין תיאור'}" for _, ts, _, _, note in db.unknown_events(30)]
        L += ["", "הערות שה-AI רשם מהמצלמה ב-24 השעות האחרונות (זמן | מי זוהה | תיאור):"]
        L += [f"{dt(ts)} | {people} | {text}" for ts, kind, people, text in db.ai_notes(now - 86400, 50) if kind == "scene"]
        return "\n".join(L)

    def send(self, text=None):
        q = (text if isinstance(text, str) else self.inp.text()).strip()
        if not q or self.thread:
            return
        if not self.app.ai.available:
            self._say("מערכת", "לא הוגדר מפתח Gemini. הוסף מפתח בלשונית ההגדרות.", "#f59e0b")
            return
        self.inp.clear()
        self._say("אתה", q, "#38bdf8")
        images, live = [], ""
        w = self.app.live_tab.worker
        if w is not None and w.last_frame is not None:
            images = [w.last_frame.copy()]
            seen = [lb["title"] + (f" ({lb['sub']})" if lb["sub"] else "") for lb in sorted(w._labels(), key=lambda lb: -lb["bbox"][0])]
            live = "\n\nהמצלמה פועלת כעת ומצורפת תמונה ממנה. התוכנה מזהה בה (מימין לשמאל): " + ("; ".join(seen) or "אף אחד")
        hist = "\n".join(f"{'משתמש' if i % 2 == 0 else 'עוזר'}: {t}" for i, t in enumerate(self.history[-6:]))
        prompt = f"נתוני התוכנה:\n{self.context()}{live}\n\nשיחה עד כה:\n{hist}\n\nשאלת המשתמש: {q}"
        self.history.append(q)
        self.send_btn.setEnabled(False)
        self.send_btn.setText("חושב…")
        self.thread = FuncThread(lambda: self.app.ai.ask(prompt, images, ai.SYSTEM, max_tokens=1500))
        self.thread.done.connect(self.on_answer)
        self.thread.start()

    def on_answer(self, res):
        self.thread = None
        self.send_btn.setEnabled(True)
        self.send_btn.setText("שלח")
        if isinstance(res, Exception):
            self.history.pop()
            self._say("מערכת", f"לא התקבלה תשובה: {res}", "#ef4444")
            return
        self.history.append(res)
        self._say("🤖 עוזר", res, "#22c55e")


# ======================================================================
class SettingsTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        st = app.settings
        form = QFormLayout()
        form.setVerticalSpacing(14)

        self.thr = QSlider(Qt.Orientation.Horizontal)
        self.thr.setRange(25, 60)
        self.thr.setValue(int(st["threshold"] * 100))
        self.thr_lbl = label("")
        self.thr.valueChanged.connect(self._thr)
        row = QHBoxLayout()
        row.addWidget(self.thr, 1)
        row.addWidget(self.thr_lbl)
        form.addRow("רמת הקפדה בזיהוי", row)
        form.addRow("", label("נמוך = מזהה בקלות אך עלול לטעות · גבוה = מזהה רק כשבטוח. ברירת המחדל (40) מתאימה לרוב.", "muted", wrap=True))

        cam = QSpinBox()
        cam.setRange(0, 9)
        cam.setValue(int(st["camera"]))
        cam.valueChanged.connect(lambda v: self._set("camera", v))
        form.addRow("מספר מצלמה (0 = המובנית)", cam)

        for key, text in (("mirror", "תצוגת מראה (כמו בסלפי)"), ("show_age", "הצג גיל ומין משוערים"),
                          ("show_emotion", "הצג הבעת פנים"), ("antispoof", "הגנה מזיוף (תמונה/מסך מול המצלמה)"),
                          ("alert_unknown", "שמור והתרע על אדם לא מוכר"), ("alert_sound", "צליל בהתרעה"),
                          ("attendance", "רשום יומן נוכחות"),
                          ("auto_learn", "למידה אוטומטית (הזיהוי משתפר לבד עם הזמן)"),
                          ("ai_enabled", "בינה מלאכותית Gemini (שולח תמונות מהמצלמה לענן של גוגל)")):
            cb = QCheckBox(text)
            cb.setChecked(bool(st[key]))
            cb.toggled.connect(lambda v, k=key: self._set(k, v))
            form.addRow("", cb)

        gap = QSpinBox()
        gap.setRange(1, 240)
        gap.setValue(int(st["attendance_gap_min"]))
        gap.valueChanged.connect(lambda v: self._set("attendance_gap_min", v))
        form.addRow("נוכחות: דקות היעדרות שפותחות רשומה חדשה", gap)

        mf = QSpinBox()
        mf.setRange(30, 300)
        mf.setValue(int(st["min_face"]))
        mf.valueChanged.connect(lambda v: self._set("min_face", v))
        form.addRow("גודל פנים מינימלי לזיהוי חי (פיקסלים)", mf)

        vs = QDoubleSpinBox()
        vs.setRange(0.2, 10)
        vs.setSingleStep(0.5)
        vs.setValue(float(st["video_step"]))
        vs.valueChanged.connect(lambda v: self._set("video_step", v))
        form.addRow("סריקת וידאו: דגימה כל כמה שניות", vs)

        ws = QLineEdit(st["work_start"])
        ws.setPlaceholderText("08:30")
        ws.setFixedWidth(130)
        ws.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ws.textChanged.connect(lambda v: self._set("work_start", v.strip()))
        form.addRow("נוכחות: שעת התחלה לחישוב איחורים (ריק = בלי)", ws)

        ai_iv = QSpinBox()
        ai_iv.setRange(10, 600)
        ai_iv.setValue(int(st["ai_interval"]))
        ai_iv.valueChanged.connect(lambda v: self._set("ai_interval", v))
        form.addRow("AI: תיאור אוטומטי של המצלמה כל כמה שניות", ai_iv)
        krow = QHBoxLayout()
        self.keys_lbl = label("")
        krow.addWidget(btn("🔑  מפתחות Gemini…", self.edit_keys))
        krow.addWidget(self.keys_lbl)
        krow.addStretch()
        form.addRow("AI: מפתחות API", krow)
        self._keys_status()

        for sb in (cam, gap, mf, vs, ai_iv):
            sb.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sb.setFixedWidth(130)
        self.info = label("", "card", wrap=True)
        box = QWidget()
        box.setLayout(form)
        box.setMaximumWidth(760)
        lay = QVBoxLayout(self)
        lay.addWidget(box)
        lay.addWidget(self.info)
        lay.addStretch()
        self._thr(self.thr.value())

    def _keys_status(self):
        n = len(self.app.ai.keys)
        self.keys_lbl.setText(f"{n} מפתחות פעילים" if n else "אין מפתח — ה-AI כבוי")

    def edit_keys(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("מפתחות Gemini")
        dlg.resize(560, 420)
        ed = QPlainTextEdit("\n".join(self.app.ai.keys))
        ed.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v = QVBoxLayout(dlg)
        v.addWidget(label("מפתח API אחד בכל שורה (מ-Google AI Studio, חינם). אפשר כמה — התוכנה מתחלפת ביניהם.", "muted", wrap=True))
        v.addWidget(ed)
        v.addWidget(bb)
        if dlg.exec():
            ai.save_keys(ed.toPlainText())
            self.app.ai.reload()
            self._keys_status()

    def _thr(self, v):
        self.thr_lbl.setText(str(v))
        self._set("threshold", v / 100)

    def _set(self, key, value):
        self.app.settings[key] = value
        self.app.settings.save()
