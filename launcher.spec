# -*- mode: python ; coding: utf-8 -*-
# FaceID.exe — קובץ ההפעלה הקטן (onefile): python -m PyInstaller --noconfirm --clean launcher.spec → dist\FaceID.exe
a = Analysis(["launcher.py"], pathex=[], binaries=[], datas=[], hiddenimports=["truststore"],
             excludes=["numpy", "cv2", "PyQt6", "openvino", "PIL", "unittest", "pydoc", "sqlite3", "asyncio", "multiprocessing"],
             noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="FaceID", debug=False, strip=False, upx=False, runtime_tmpdir=None,
          console=False, icon=["icon.ico"])
