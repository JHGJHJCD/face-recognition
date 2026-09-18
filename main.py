"""זיהוי פנים — חלון רגיל שבתוכו ממשק בעיצוב אינטרנט (QtWebEngine). המנועים ב-core/ לא השתנו.

  main.py                 הפעלה רגילה
  main.py --classic       הממשק הישן (PyQt רגיל) — גיבוי
  main.py --shot <תיקייה>  בדיקה: מצלם כל מסך ל-PNG ויוצא   ·   --camera מפעיל מצלמה אוטומטית
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
if sys.stderr is None:      # pythonw — אין קונסולה
    sys.stdout = sys.stderr = open(os.devnull, "w")

if "--classic" in sys.argv:
    import main_classic
    main_classic.main()
    sys.exit()

import traceback  # noqa: E402

CRASH_LOG = os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ROOT, "crash_log.txt")


def _crash(e):
    """ב-EXE אין קונסולה — שגיאת הפעלה נכתבת לקובץ ליד התוכנה."""
    try:
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n===== {__import__('time').strftime('%Y-%m-%d %H:%M:%S')} =====\n{e}\n{traceback.format_exc()}")
    except OSError:
        pass


try:
    from PyQt6.QtCore import Qt, QTimer, QUrl  # noqa: E402
    from PyQt6.QtGui import QColor, QIcon  # noqa: E402
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings  # noqa: E402
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
    from PyQt6.QtWidgets import QApplication, QMainWindow  # noqa: E402

    from webui.backend import Backend, start_server  # noqa: E402
except Exception as _e:  # noqa: E402
    _crash(_e)
    raise

ICON = os.path.join(getattr(sys, "_MEIPASS", ROOT), "icon.ico")   # ב-EXE הסמל נארז פנימה
PAGES = ["live", "people", "photos", "video", "attendance", "assistant", "data", "settings"]


class Page(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, msg, line, src):
        if "--shot" in sys.argv or "--debug" in sys.argv:
            print(f"[js] {msg} ({line})")


class Window(QMainWindow):
    def __init__(self, backend, url):
        super().__init__()
        self.backend = backend
        self.setWindowTitle("זיהוי פנים")
        if os.path.exists(ICON):
            self.setWindowIcon(QIcon(ICON))
        self.resize(1440, 900)
        self.view = QWebEngineView()
        self.view.setPage(Page(self.view))
        self.view.page().setBackgroundColor(QColor("#0a0f1e"))
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        self.setCentralWidget(self.view)
        self.view.load(QUrl(url))

    def closeEvent(self, e):
        self.backend.shutdown()
        e.accept()


def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    backend = Backend()
    server, url = start_server(backend)
    win = Window(backend, url)
    backend.window = win
    win.show()

    if "--shot" in sys.argv:
        out = sys.argv[sys.argv.index("--shot") + 1]
        js = win.view.page().runJavaScript

        def shoot(i=0):
            if i:
                win.grab().save(os.path.join(out, f"web_{i - 1}_{PAGES[i - 1]}.png"))
            if i >= len(PAGES):
                win.close()
                return
            js(f"location.hash='{PAGES[i]}'")
            QTimer.singleShot(9000 if (i == 0 and "--camera" in sys.argv) else 1500, lambda: shoot(i + 1))

        def wait_ready():
            if backend.engine is None:
                QTimer.singleShot(500, wait_ready)
                return
            if "--camera" in sys.argv:
                backend._camera_on()
            QTimer.singleShot(2500, shoot)

        wait_ready()
    elif "--camera" in sys.argv:
        def cam():
            if backend.engine is None:
                QTimer.singleShot(500, cam)
            else:
                backend._camera_on()
        cam()
    code = app.exec()
    server.shutdown()
    sys.exit(code)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        _crash(e)
        raise
