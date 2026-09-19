# -*- mode: python ; coding: utf-8 -*-
# התוכנה עצמה כתיקייה פרוסה (onedir): python -m PyInstaller --noconfirm --clean זיהוי_פנים.spec → dist\FaceIDApp\ → נארז ל-distpp.zip
# קובץ ההפעלה הקטן שמפיצים נבנה בנפרד מ-launcher.spec. למה לא EXE יחיד: נפרס מחדש 78 שנ' בכל הפעלה (נמדד 19/9/2026).
# המודלים (~380MB) לא בפנים — יורדים בהפעלה הראשונה מ-Release "models-v1" לתיקיית models\ ליד FaceID.exe.
from PyInstaller.utils.hooks import collect_all

ov_datas, ov_bins, ov_hidden = collect_all("openvino")
UNUSED = ("jax", "paddle", "pytorch", "tensorflow", "gguf", "npu", "_debug", ".lib")   # פרונטאנדים/פלאגינים שלא בשימוש — חוסך ~100MB
ov_bins = [b for b in ov_bins if not any(u in b[0].lower() for u in UNUSED)]
ov_datas = [d for d in ov_datas if not any(u in d[0].lower() for u in UNUSED)]
ov_hidden = None   # לא מייבאים הכול — רק מה ש-import openvino מושך

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=ov_bins,
    datas=[("webui/static", "webui/static"), ("icon.ico", "."), *ov_datas],
    hiddenimports=["core.engine", "core.db", "core.live", "core.jobs", "core.ai", "core.reports", "core.updater", "core.utils",
                   "webui.backend", "version", "openpyxl", "openpyxl.cell._writer", "et_xmlfile", "truststore",
                   "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebChannel", "PyQt6.QtNetwork"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["onnxruntime", "PyQt6.QtMultimedia", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtSql", "PyQt6.QtTest",
              "PyQt6.QtDesigner", "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtPositioning", "PyQt6.QtSensors", "PyQt6.QtSerialPort",
              "PySide6", "PyQt5", "tkinter", "unittest", "pydoc", "matplotlib", "scipy", "pandas", "PIL", "ui", "main_classic",
              # openvino מייבא-בניסיון פרונטאנדים של torch/tensorflow/jax/paddle — לא צריך אותם (מודלי onnx בלבד), חוסך ~450MB
              "torch", "torchvision", "torchaudio", "transformers", "tokenizers", "huggingface_hub", "hf_xet", "safetensors", "tensorflow",
              "jax", "jaxlib", "paddle", "cryptography", "pydantic", "pydantic_core", "lxml", "openvino.frontend.pytorch", "openvino.frontend.tensorflow",
              "openvino.frontend.jax", "openvino.frontend.paddle", "openvino.tools", "openvino_telemetry", "sympy", "networkx", "yaml", "requests"],
    noarchive=False,
    optimize=0,
)
# כלי-פיתוח של Chromium (devtools) לא נחוצים בתוכנה — ~85MB
a.datas = [d for d in a.datas if "devtools" not in d[0].lower()]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FaceIDApp",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=["icon.ico"],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FaceIDApp")
