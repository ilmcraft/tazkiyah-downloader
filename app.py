"""তাযকিয়া ডাউনলোডার — a desktop window (pywebview) around downloader.Downloader."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import webview
import yt_dlp.version

from downloader import AUDIO_FORMATS, BROWSERS, QUALITIES, Downloader, _friendly_error

APP_NAME = "Tazkiyah Downloader"
APP_VERSION = "1.0.0"


def _resource(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / rel


def _config_path() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME / "settings.json"


def _default_folder() -> str:
    downloads = Path.home() / "Downloads"
    return str((downloads if downloads.is_dir() else Path.home()) / "Tazkiyah")


def _open_path(path: str) -> None:
    if platform.system() == "Windows":
        os.startfile(path)  # noqa: S606 — opening the user's own folder
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class Api:
    """Every public method here is callable from the page as window.pywebview.api.<name>()."""

    def __init__(self):
        self._dl = Downloader()
        self._window = None
        self._settings = self._load_settings()

    # ----- settings -----

    def _load_settings(self) -> dict:
        s = {"folder": _default_folder(), "mode": "video", "quality": "720",
             "audioFormat": "mp3", "numbered": True, "theme": "system", "cookies": ""}
        try:
            s.update(json.loads(_config_path().read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        return s

    def get_state(self) -> dict:
        return {
            "settings": self._settings,
            "tools": {k: bool(v) for k, v in self._dl.tools.items()},
            "version": APP_VERSION,
            "ytdlp": yt_dlp.version.__version__,
            "browsers": list(BROWSERS),
            "job": self._dl.snapshot(),
        }

    def save_settings(self, patch: dict) -> dict:
        allowed = {"folder", "mode", "quality", "audioFormat", "numbered", "theme", "cookies"}
        self._settings.update({k: v for k, v in (patch or {}).items() if k in allowed})
        try:
            p = _config_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._settings, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return self._settings

    # ----- actions -----

    def inspect(self, link: str) -> dict:
        try:
            return {"ok": True, "data": self._dl.inspect(link, self._settings.get("cookies") or "")}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:  # network errors, unsupported links, YouTube changes
            return {"ok": False, "error": _friendly_error(e)}

    def start(self, req: dict) -> dict:
        try:
            s = self._settings
            mode = req.get("mode", s["mode"])
            quality = str(req.get("quality", s["quality"]))
            audio_format = req.get("audioFormat", s["audioFormat"])
            if quality not in QUALITIES or audio_format not in AUDIO_FORMATS:
                raise ValueError("ভুল সেটিং।")
            self.save_settings({"mode": mode, "quality": quality, "audioFormat": audio_format,
                                "numbered": bool(req.get("numbered"))})
            self._dl.start(req["entries"], s["folder"], mode=mode, quality=quality,
                           audio_format=audio_format, subfolder=req.get("subfolder") or "",
                           numbered=bool(req.get("numbered")), cookies=s.get("cookies") or "")
            return {"ok": True}
        except (ValueError, RuntimeError, OSError) as e:
            return {"ok": False, "error": str(e)}

    def status(self):
        return self._dl.snapshot()

    def cancel(self) -> None:
        self._dl.cancel()

    def skip_current(self) -> None:
        self._dl.skip_current()

    def retry_failed(self) -> int:
        return self._dl.retry_failed()

    def pick_folder(self):
        win = self._window
        start = self._settings.get("folder") or str(Path.home())
        if not Path(start).is_dir():
            start = str(Path.home())
        res = win.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
        if res:
            folder = res[0] if isinstance(res, (list, tuple)) else res
            self.save_settings({"folder": folder})
            return folder
        return None

    def open_folder(self, path: str | None = None) -> None:
        target = path or (self._dl.job.folder if self._dl.job else self._settings["folder"])
        p = Path(target)
        if p.is_file():
            p = p.parent
        p.mkdir(parents=True, exist_ok=True)
        _open_path(str(p))

    def paste(self) -> str:
        """Clipboard text, for the 'paste' button (navigator.clipboard is unreliable in webviews)."""
        try:
            if platform.system() == "Darwin":
                return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3).stdout
            if platform.system() == "Windows":
                return subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError):
            pass
        return ""

    def confirm_quit(self) -> bool:
        return not self._dl.busy()


def selftest(link: str, out: str) -> int:
    """Headless check used by CI on the frozen build: look up a link, download it as audio."""
    import time
    from downloader import Downloader
    d = Downloader()
    report = {"tools": d.tools}
    try:
        info = d.inspect(link)
        report["lookup"] = {"kind": info["kind"], "title": info["title"], "count": len(info["entries"])}
        entry = min(info["entries"], key=lambda e: e.get("duration") or 10**9)
        d.start([entry], out, mode="audio", audio_format="mp3" if d.tools.get("ffmpeg") else "m4a")
        while d.busy():
            time.sleep(1)
        it = d.snapshot()["items"][0]
        report["download"] = {k: it[k] for k in ("state", "error", "file", "size")}
        ok = it["state"] == "done" and (it["size"] or 0) > 10_000
    except Exception as e:
        report["error"] = repr(e)
        ok = False
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "selftest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1


def main() -> None:
    if len(sys.argv) >= 4 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2], sys.argv[3]))
    api = Api()
    window = webview.create_window(
        "তাযকিয়া ডাউনলোডার", url=str(_resource("ui/index.html")), js_api=api,
        width=980, height=760, min_size=(420, 560), background_color="#0A0A0A",
        text_select=True,
    )
    api._window = window

    def on_closing():
        if api._dl.busy():
            ok = window.create_confirmation_dialog(
                "ডাউনলোড চলছে", "ডাউনলোড এখনো চলছে। বন্ধ করলে বাকিগুলো থেমে যাবে। বন্ধ করবেন?")
            if not ok:
                return False
            api._dl.cancel()
        return True

    window.events.closing += on_closing
    webview.start(debug=bool(os.environ.get("TAZKIYAH_DEBUG")))


if __name__ == "__main__":
    main()
