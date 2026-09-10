# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for Clippings Manager.

Builds a folder application rather than a single file. A one-file build of a Qt
application unpacks a few hundred megabytes to a temporary folder on every launch,
which for a tool opened each morning means a ten second wait before anything
appears. The folder build starts immediately. Both are produced by build.py.

Three things this has to get right:

*   **The JSON config travels with the app.** divisions.json and newspapers.json are
    read relative to the package, so they are shipped in the same relative place.
    User edits are written to the app-data folder instead, so an update never
    overwrites the newspaper list.
*   **pywin32's COM plumbing is imported at runtime**, not at the top of a module,
    so PyInstaller cannot see it. Reading a WhatsApp drag depends on it.
*   **Unused Qt modules are dropped.** PySide6 installs 640MB; the app needs a
    fraction of it.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

import os

datas = [
    # Which build this is. Written by build.py just before packaging, so the
    # window, the executable's properties and every exported report can say so.
    ("clippings_manager/_buildstamp.json", "clippings_manager"),
    ("clippings_manager/config/*.json", "clippings_manager/config"),
    # The two weights the app actually sets, and the licence, which the SIL
    # Open Font License requires to travel with them. The other thirty-six
    # files in that folder are the widths and weights nothing asks for.
    # Named exactly, not globbed: "*-Regular.ttf" also matches the Condensed,
    # SemiCondensed and ExtraCondensed widths, which nothing loads.
    ("clippings_manager/assets/fonts/NotoSansDevanagari-Regular.ttf",
     "clippings_manager/assets/fonts"),
    ("clippings_manager/assets/fonts/NotoSansDevanagari-Bold.ttf",
     "clippings_manager/assets/fonts"),
    ("clippings_manager/assets/fonts/OFL.txt", "clippings_manager/assets/fonts"),
    ("clippings_manager/assets/icon/*", "clippings_manager/assets/icon"),
    # What the duplicate check reads headlines with. Hindi first, because these
    # are Hindi newspapers. Apache 2.0, so it travels with the application - and
    # it must, or the machine it lands on would need Tesseract installed and the
    # whole thing would stop working with the network unplugged.
    ("clippings_manager/assets/tessdata/*.traineddata",
     "clippings_manager/assets/tessdata"),
]

hiddenimports = [
    # Resolved only when a drag arrives, so nothing references them statically.
    "pythoncom",
    "pywintypes",
    "win32com",
    "win32com.server",
    "win32com.server.policy",
    "win32com.server.util",
    "win32clipboard",
    "win32con",
    # Pillow decodes whichever format a division happens to send.
    "PIL._tkinter_finder",
]
hiddenimports += collect_submodules("docx")

# The OCR engine that reads headlines off cuttings, so the app can tell that the
# same story arrived twice. Named as a hidden import it is NOT enough: naming it
# collected the loose .dll and .pyd files but not the package itself, and
# tesserocr's __init__ does "from .tesserocr import *" - so the packaged
# application imported nothing, reported no engine, and would have done no
# duplicate checking at all while looking perfectly healthy. collect_all takes
# the package, its cysignals sub-package and every one of the eleven libraries
# they load between them.
_ocr_datas, _ocr_binaries, _ocr_hidden = collect_all("tesserocr")
datas += _ocr_datas
hiddenimports += _ocr_hidden

# Qt ships far more than a desktop tool needs, and every megabyte is a megabyte the
# PR department has to copy onto the office machine.
excludes = [
    # win32ui is the only thing in the bundle that needs the MFC runtime
    # (mfc140u.dll), which a clean Windows install does not have. Nothing here
    # imports it - PyInstaller collects it with the rest of pywin32 - and with
    # it gone every remaining dependency is a core Windows component. That is
    # what lets the folder be copied to any Windows 10 or 11 machine and run
    # with nothing installed first.
    "win32ui", "win32uiole", "pythonwin",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtWebSockets",
    "PySide6.QtWebChannel", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSensors", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtHelp", "PySide6.QtDesigner", "PySide6.QtUiTools",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    # Never used, and each drags in a large dependency tree.
    "tkinter", "matplotlib", "scipy", "pandas", "numpy.f2py",
    "torch", "torchaudio", "transformers", "gradio", "IPython", "notebook",
    "pytest", "setuptools._distutils",
]

analysis = Analysis(
    ["clippings_manager/main.py"],
    pathex=["."],
    binaries=_ocr_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Clippings Manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Cut from the artwork by tools/make_icon.py. Windows reads the .ico for the
    # taskbar, the title bar and Explorer, so all seven sizes live in the one file.
    icon="clippings_manager/assets/icon/icon.ico",
    # Written by build.py from the same stamp the window shows, so Explorer's
    # Properties pane and the running application always agree about the build.
    version=("packaging/version_info.txt"
             if os.path.exists("packaging/version_info.txt") else None),
)

COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Clippings Manager",
)
