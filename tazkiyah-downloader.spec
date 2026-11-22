# PyInstaller build: `pyinstaller tazkiyah-downloader.spec`
# Put ffmpeg / deno executables in ./bin first to ship them inside the app.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

bins = [(str(p), "bin") for p in Path("bin").glob("*") if p.is_file()] if Path("bin").is_dir() else []
datas = [("ui", "ui")] + collect_data_files("yt_dlp_ejs") + collect_data_files("webview")
hidden = collect_submodules("yt_dlp.extractor") + collect_submodules("yt_dlp_ejs")

a = Analysis(["app.py"], binaries=bins, datas=datas, hiddenimports=hidden, excludes=["tkinter"])
pyz = PYZ(a.pure)
icon = "assets/icon.ico" if sys.platform == "win32" else "assets/icon.icns"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TazkiyahDownloader",
          console=False, icon=icon, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="TazkiyahDownloader", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="Tazkiyah Downloader.app", icon=icon,
                 bundle_identifier="io.github.ilmcraft.tazkiyah.downloader",
                 info_plist={"CFBundleShortVersionString": "1.0.0", "NSHighResolutionCapable": True})
