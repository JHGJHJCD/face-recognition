"""בדיקת גלילה בממשק: פותח את החלון, עובר למסך, גולל בכוח ומצלם. שימוש: probe_scroll.py <תיקיית פלט>"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.argv.append("--debug")
from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import main as m  # noqa: E402

out = sys.argv[1]
app = QApplication(sys.argv)
app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
be = m.Backend()
srv, url = m.start_server(be)
win = m.Window(be, url)
be.window = win
win.resize(1200, 700)
win.show()
js = win.view.page().runJavaScript
steps = [("settings", "document.querySelector('#page').scrollTop = 99999; [document.querySelector('#page').scrollHeight, document.querySelector('#page').clientHeight]"),
         ("people", "var s=document.querySelector('#p-grid').parentElement; s.scrollTop=99999; [s.scrollHeight, s.clientHeight]"),
         ("attendance", "var s=document.querySelector('.table-wrap'); s.scrollTop=99999; [s.scrollHeight, s.clientHeight]")]


def run(i=0):
    if i >= len(steps):
        win.close()
        return
    page, code = steps[i]
    js(f"location.hash='{page}'")

    def after():
        js(code, lambda v: print(page, "scrollHeight/clientHeight:", v))
        QTimer.singleShot(400, lambda: (win.grab().save(os.path.join(out, f"scroll_{page}.png")), run(i + 1)))
    QTimer.singleShot(1500, after)


def wait():
    if be.engine is None:
        QTimer.singleShot(500, wait)
    else:
        QTimer.singleShot(2500, run)


wait()
app.exec()
srv.shutdown()
