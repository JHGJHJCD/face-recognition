"""זיהוי פנים — הזיהוי עצמו רץ מקומית; רק רכיב ה-AI (Gemini, ניתן לכיבוי) שולח תמונות לענן."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import Qt, QThread, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QStackedWidget, QTabWidget  # noqa: E402

from core.db import Database, Settings  # noqa: E402
from core.ai import GeminiClient  # noqa: E402
from ui.tabs import AssistantTab, AttendanceTab, LiveTab, PeopleTab, PhotosTab, SettingsTab, VideoTab  # noqa: E402
from ui.widgets import STYLE, FuncThread  # noqa: E402

MODEL_TITLES = {"glintr100": "ArcFace R100 · Glint360K", "w600k_r50": "ArcFace R50 · WebFace600K"}


class Loader(QThread):
    ready = pyqtSignal(object)

    def run(self):
        try:
            from core.engine import FaceEngine
            self.ready.emit(FaceEngine())
        except Exception as e:
            self.ready.emit(e)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("זיהוי פנים")
        self.resize(1360, 860)
        self.settings = Settings()
        self.engine = self.db = None
        self._rematch = None
        self.stack = QStackedWidget()
        self.splash = QLabel("טוען את מנועי הזיהוי…\n\nבהפעלה הראשונה זה לוקח כדקה־שתיים (התאמה חד־פעמית למחשב).\nבפעמים הבאות — שניות ספורות.")
        self.splash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.splash.setStyleSheet("font-size: 20px; color: #94a3b8;")
        self.stack.addWidget(self.splash)
        self.setCentralWidget(self.stack)
        self.loader = Loader()
        self.loader.ready.connect(self.on_ready)
        self.loader.start()

    def on_ready(self, engine):
        if isinstance(engine, Exception):
            self.splash.setText(f"טעינת המודלים נכשלה:\n{engine}")
            return
        self.engine = engine
        self.db = Database(engine.rec_name)
        self.ai = GeminiClient()
        self.tabs = QTabWidget()
        self.live_tab, self.people_tab, self.photos_tab = LiveTab(self), PeopleTab(self), PhotosTab(self)
        self.video_tab, self.attendance_tab, self.settings_tab = VideoTab(self), AttendanceTab(self), SettingsTab(self)
        self.assistant_tab = AssistantTab(self)
        for w, t in ((self.live_tab, "🎥  זיהוי חי"), (self.people_tab, "👤  אנשים"), (self.photos_tab, "🖼  מיון תמונות"),
                     (self.video_tab, "🎬  סריקת וידאו"), (self.attendance_tab, "📋  יומן נוכחות"), (self.assistant_tab, "🤖  עוזר AI"), (self.settings_tab, "⚙  הגדרות")):
            self.tabs.addTab(w, t)
        self.stack.addWidget(self.tabs)
        self.stack.setCurrentWidget(self.tabs)
        self.people_tab.refresh()
        self.photos_tab.refresh()
        self.attendance_tab.refresh()
        dev = "מאיץ גרפי (Intel GPU)" if engine.device == "GPU" else "מעבד"
        info = (f"מנוע זהות: {MODEL_TITLES.get(engine.rec_name, engine.rec_name)} · איתור: SCRFD-10G · הבעות: HSEmotion · "
                f"הגנה מזיוף: MiniFASNet ×2 · רץ על: {dev} · "
                + ("AI: Gemini בענן (פעיל)" if self.settings["ai_enabled"] and self.ai.available else "הכול מקומי, בלי אינטרנט"))
        self.statusBar().showMessage(info)
        self.settings_tab.info.setText(info)

    def after_gallery_change(self):
        """אחרי הוספת/מחיקת אדם — התאמה מחדש של התמונות שכבר נסרקו (בלי לסרוק שוב)."""
        if self._rematch is not None or self.db.photo_stats()[1] == 0:
            return
        self._rematch = FuncThread(self.db.rematch_photos, self.settings["threshold"])
        self._rematch.done.connect(self._rematched)
        self._rematch.start()

    def _rematched(self, _):
        self._rematch = None
        self.photos_tab.refresh()

    def closeEvent(self, e):
        if self.engine:
            self.live_tab.stop()
            for w in (self.photos_tab.worker, self.video_tab.worker):
                if w:
                    w.stop_flag = True
                    w.wait(5000)
        e.accept()


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    if "--camera" in sys.argv:  # לבדיקות: הפעלת מצלמה אוטומטית
        win.loader.ready.connect(lambda _: win.live_tab.toggle())
    if "--shot" in sys.argv:    # לבדיקות: צילום כל לשונית לקובץ ויציאה
        from PyQt6.QtCore import QTimer
        out = sys.argv[sys.argv.index("--shot") + 1]

        def shoot(i=0):
            if i:
                win.grab().save(os.path.join(out, f"tab{i - 1}.png"))
            if i >= win.tabs.count():
                win.close()
                return
            win.tabs.setCurrentIndex(i)
            QTimer.singleShot(8000 if i == 0 else 700, lambda: shoot(i + 1))

        win.loader.ready.connect(lambda _: QTimer.singleShot(500, shoot))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
