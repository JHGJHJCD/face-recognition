"""רכיבי ממשק משותפים: תצוגת וידאו עם שכבת זיהוי, עיצוב, כלי עזר."""
from PyQt6.QtCore import QRectF, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget

COLORS = {"known": QColor("#22c55e"), "unknown": QColor("#f59e0b"), "spoof": QColor("#ef4444"), "pending": QColor("#38bdf8")}

STYLE = """
* { font-family: 'Segoe UI'; font-size: 14px; }
QMainWindow, QWidget { background: #0f172a; color: #e2e8f0; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #94a3b8; padding: 12px 22px; font-size: 15px; font-weight: 600; border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 3px solid #38bdf8; }
QTabBar::tab:hover { color: #e2e8f0; }
QPushButton { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 9px 16px; color: #e2e8f0; }
QPushButton:hover { background: #273449; border-color: #475569; }
QPushButton:disabled { color: #64748b; background: #172033; }
QPushButton#primary { background: #0ea5e9; border: none; color: white; font-weight: 700; }
QPushButton#primary:hover { background: #0284c7; }
QPushButton#danger { background: #7f1d1d; border: none; color: #fecaca; }
QPushButton#danger:hover { background: #991b1b; }
QListWidget, QTableWidget, QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {
    background: #111c33; border: 1px solid #1e293b; border-radius: 8px; padding: 4px; }
QListWidget::item { border-radius: 8px; padding: 4px; }
QListWidget::item:selected { background: #0c4a6e; color: white; }
QListWidget::item:hover { background: #1e293b; }
QHeaderView::section { background: #1e293b; color: #cbd5e1; border: none; padding: 8px; font-weight: 600; }
QTableWidget { gridline-color: #1e293b; }
QProgressBar { background: #1e293b; border: none; border-radius: 6px; height: 12px; text-align: center; color: white; font-size: 11px; }
QProgressBar::chunk { background: #0ea5e9; border-radius: 6px; }
QLabel#h1 { font-size: 18px; font-weight: 700; color: white; }
QLabel#muted { color: #94a3b8; }
QLabel#card { background: #111c33; border: 1px solid #1e293b; border-radius: 10px; padding: 10px; }
QCheckBox { spacing: 10px; padding: 4px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #475569; border-radius: 5px; background: #111c33; }
QCheckBox::indicator:checked { background: #0ea5e9; border-color: #0ea5e9; }
QSpinBox, QDoubleSpinBox { padding: 6px 10px; min-height: 22px; }
QSlider::groove:horizontal { height: 6px; background: #1e293b; border-radius: 3px; }
QSlider::handle:horizontal { background: #38bdf8; width: 18px; margin: -6px 0; border-radius: 9px; }
QStatusBar { color: #94a3b8; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #334155; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


def pixmap_from_jpg(data, size=None):
    pm = QPixmap()
    if data:
        pm.loadFromData(bytes(data))
    if size and not pm.isNull():
        pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    return pm


def bgr_to_qimage(frame):
    h, w = frame.shape[:2]
    return QImage(frame.data, w, h, 3 * w, QImage.Format.Format_BGR888).copy()


class FuncThread(QThread):
    """מריץ פונקציה ברקע ומחזיר את התוצאה."""
    done = pyqtSignal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.done.emit(self.fn(*self.args))
        except Exception as e:
            self.done.emit(e)


class ThumbList(QListWidget):
    """רשימת תמונות ממוזערות עם כיתוב."""

    def __init__(self, icon=96, grid=True):
        super().__init__()
        self.icon = icon
        self.setIconSize(QSize(icon, icon))
        if grid:
            self.setViewMode(QListWidget.ViewMode.IconMode)
            self.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.setMovement(QListWidget.Movement.Static)
            self.setGridSize(QSize(icon + 28, icon + 44))
            self.setWordWrap(True)
        self.setSpacing(4)

    def add(self, text, jpg, data=None):
        it = QListWidgetItem(QIcon(pixmap_from_jpg(jpg, self.icon)), text)
        it.setData(Qt.ItemDataRole.UserRole, data)
        if self.viewMode() == QListWidget.ViewMode.IconMode:
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.addItem(it)
        return it

    def current_data(self):
        it = self.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


class VideoWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.image = None
        self.labels = []
        self.message = "המצלמה כבויה"
        self.setMinimumSize(640, 400)

    def set_frame(self, frame, labels):
        self.image = bgr_to_qimage(frame) if frame is not None else None
        self.labels = labels or []
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#020617"))
        if self.image is None:
            p.setPen(QColor("#64748b"))
            p.setFont(QFont("Segoe UI", 18))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        iw, ih = self.image.width(), self.image.height()
        s = min(self.width() / iw, self.height() / ih)
        ox, oy = (self.width() - iw * s) / 2, (self.height() - ih * s) / 2
        p.drawImage(QRectF(ox, oy, iw * s, ih * s), self.image)
        p.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        title_font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        sub_font = QFont("Segoe UI", 10)
        for lb in self.labels:
            color = COLORS[lb["state"]]
            x1, y1, x2, y2 = [float(v) for v in lb["bbox"]]
            r = QRectF(ox + x1 * s, oy + y1 * s, (x2 - x1) * s, (y2 - y1) * s)
            self._corners(p, r, color)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 200))
            for kx, ky in lb["kps"]:
                p.drawEllipse(QRectF(ox + kx * s - 2, oy + ky * s - 2, 4, 4))
            self._pill(p, lb["title"], title_font, r.center().x(), r.top() - 8, color, QColor("white"), above=True)
            if lb["sub"]:
                self._pill(p, lb["sub"], sub_font, r.center().x(), r.bottom() + 8, QColor(15, 23, 42, 210), QColor("#e2e8f0"), above=False)

    @staticmethod
    def _corners(p, r, color):
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 90), 1.5))
        p.drawRoundedRect(r, 10, 10)
        pen = QPen(color, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        L = min(r.width(), r.height()) * 0.22
        for cx, cy, dx, dy in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1), (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.drawLine(int(cx), int(cy), int(cx + dx * L), int(cy))
            p.drawLine(int(cx), int(cy), int(cx), int(cy + dy * L))

    @staticmethod
    def _pill(p, text, font, cx, y, bg, fg, above):
        p.setFont(font)
        fm = QFontMetrics(font)
        w, h = fm.horizontalAdvance(text) + 20, fm.height() + 8
        rect = QRectF(cx - w / 2, y - h if above else y, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, h / 2, h / 2)
        p.setPen(fg)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
