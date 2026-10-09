# PyInstaller spec for mdConverter.
# Build with:  pyinstaller --noconfirm mdConverter.spec   (or run build.bat)
#
# MarkItDown and its parsers load data files and native libraries at runtime
# (Magika's model, tkdnd's DLLs, CustomTkinter's themes), so those packages are
# collected in full rather than relying on import analysis alone.

from PyInstaller.utils.hooks import collect_all

datas = [("assets/icon.ico", "assets")]
binaries = []
hiddenimports = []

for package in (
    "markitdown",
    "magika",
    "customtkinter",
    "tkinterdnd2",
    "pdfminer",
    "mammoth",
    "pptx",
    "openpyxl",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Large libraries that MarkItDown does not need for a desktop build.
    excludes=["matplotlib", "IPython", "pytest", "notebook", "jupyter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mdConverter",
    icon="assets/icon.ico",
    console=False,          # windowed app: no console window for end users
    upx=False,
)

# One-folder build: starts much faster than --onefile because nothing has to be
# unpacked to a temp directory on every launch. Ship the whole dist/mdConverter folder.
coll = COLLECT(exe, a.binaries, a.datas, name="mdConverter", upx=False)
