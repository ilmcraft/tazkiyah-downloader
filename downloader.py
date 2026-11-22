"""YouTube video/playlist downloading on top of yt-dlp, with no GUI code.

`Downloader` keeps one job at a time: a list of items downloaded one after another
into a folder, with per-item state the UI polls through `snapshot()`.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.utils import DownloadCancelled, sanitize_filename

QUALITIES = ("best", "1080", "720", "480", "360")
AUDIO_FORMATS = ("mp3", "m4a")
BROWSERS = ("firefox", "chrome", "edge", "brave", "safari")


class _QuietLogger:
    """Keeps yt-dlp from writing to stdout/stderr, which do not exist in a windowed build."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


# ---------- bundled tools ----------

def _bundle_dirs() -> list[Path]:
    """Folders that may hold ffmpeg/deno shipped with the app (PyInstaller build or a local bin/)."""
    dirs = []
    if getattr(sys, "_MEIPASS", None):
        dirs.append(Path(sys._MEIPASS) / "bin")
    dirs.append(Path(sys.executable).resolve().parent / "bin")
    dirs.append(Path(__file__).resolve().parent / "bin")
    return [d for d in dirs if d.is_dir()]


def setup_tools() -> dict:
    """Put bundled tools on PATH and report which ones are usable."""
    extra = [str(d) for d in _bundle_dirs()]
    # Apps opened from Finder don't inherit the shell PATH, so Homebrew's tools are invisible.
    if sys.platform == "darwin":
        extra += [p for p in ("/opt/homebrew/bin", "/usr/local/bin") if os.path.isdir(p)]
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH", "")])
    return {"ffmpeg": shutil.which("ffmpeg"), "deno": shutil.which("deno")}


# ---------- link parsing ----------

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_link(text: str) -> dict:
    """Pull the video id and playlist id out of any YouTube link form."""
    text = (text or "").strip()
    if not text:
        return {}
    if _ID.match(text):
        return {"video": text}
    if not re.match(r"^https?://", text):
        text = "https://" + text
    u = urlparse(text)
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.").removeprefix("music.")
    q = parse_qs(u.query)
    out = {}
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
        if _ID.match(vid):
            out["video"] = vid
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        if "v" in q and _ID.match(q["v"][0]):
            out["video"] = q["v"][0]
        parts = [p for p in u.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v") and _ID.match(parts[1]):
            out["video"] = parts[1]
        if parts and (parts[0].startswith("@") or parts[0] in ("channel", "c", "user")):
            out["channel"] = text
    else:
        return {}
    lid = q.get("list", [None])[0]
    # RD… lists are YouTube "mixes": endless and personalised, not real playlists.
    if lid and not lid.startswith("RD"):
        out["playlist"] = lid
    return out


# ---------- job state ----------

@dataclass
class Item:
    id: str
    title: str
    duration: int | None = None
    index: int = 0
    state: str = "queued"     # queued | downloading | waiting | processing | done | skipped | error | cancelled
    progress: float = 0.0     # 0..1 for the current file
    part: str = ""            # "ভিডিও" / "অডিও" while both streams are fetched
    speed: float | None = None
    eta: int | None = None
    size: int | None = None
    error: str = ""
    file: str = ""


@dataclass
class Job:
    items: list[Item]
    folder: str
    mode: str
    quality: str
    audio_format: str
    numbered: bool
    cookies: str = ""
    running: bool = True
    started: float = field(default_factory=time.time)


class Downloader:
    def __init__(self):
        self.tools = setup_tools()
        self.job: Job | None = None
        self._cancel = threading.Event()
        self._skip = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ----- looking up a link -----

    def inspect(self, link: str, cookies: str = "") -> dict:
        p = parse_link(link)
        if not p:
            raise ValueError("এটি ইউটিউবের ভিডিও বা প্লেলিস্ট লিংক মনে হচ্ছে না।")
        if "channel" in p and "video" not in p and "playlist" not in p:
            url = p["channel"].rstrip("/")
            if not re.search(r"/(videos|streams|shorts|playlists)$", url):
                url += "/videos"
        elif "playlist" in p:
            url = f"https://www.youtube.com/playlist?list={p['playlist']}"
        else:
            url = f"https://www.youtube.com/watch?v={p['video']}"

        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "logger": _QuietLogger(),
                "extract_flat": "in_playlist", "noplaylist": False}
        if cookies in BROWSERS:
            opts["cookiesfrombrowser"] = (cookies,)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
            entries = []
            for e in info.get("entries") or []:
                if not e or not e.get("id"):
                    continue
                title = e.get("title") or ""
                # Deleted/private videos still appear in playlists with a placeholder title.
                if title in ("[Deleted video]", "[Private video]"):
                    continue
                entries.append({"id": e["id"], "title": title, "duration": _int(e.get("duration"))})
            if not entries:
                raise ValueError("এই প্লেলিস্টে ডাউনলোড করার মতো কোনো ভিডিও পাওয়া যায়নি।")
            return {
                "kind": "playlist",
                "title": info.get("title") or "প্লেলিস্ট",
                "uploader": info.get("uploader") or info.get("channel") or "",
                "entries": entries,
                "videoId": p.get("video"),   # the link pointed at one video inside the playlist
            }
        return {
            "kind": "video",
            "title": info.get("title") or info["id"],
            "uploader": info.get("uploader") or info.get("channel") or "",
            "entries": [{"id": info["id"], "title": info.get("title") or info["id"],
                         "duration": _int(info.get("duration"))}],
        }

    # ----- running a job -----

    def start(self, entries: list[dict], folder: str, mode: str = "video", quality: str = "720",
              audio_format: str = "mp3", subfolder: str = "", numbered: bool = False,
              cookies: str = "") -> None:
        if self.busy():
            raise RuntimeError("আগের ডাউনলোড এখনো চলছে।")
        if mode not in ("video", "audio") or quality not in QUALITIES or audio_format not in AUDIO_FORMATS:
            raise ValueError("ভুল সেটিং।")
        if not entries:
            raise ValueError("কোনো ভিডিও বাছাই করা হয়নি।")
        target = Path(folder).expanduser()
        if subfolder:
            target = target / _safe_name(subfolder)
        target.mkdir(parents=True, exist_ok=True)
        items = [Item(id=e["id"], title=e.get("title") or e["id"], duration=_int(e.get("duration")),
                      index=_int(e.get("index")) or i + 1)
                 for i, e in enumerate(entries)]
        self._cancel.clear()
        self._skip.clear()
        self.job = Job(items=items, folder=str(target), mode=mode, quality=quality,
                       audio_format=audio_format, numbered=numbered,
                       cookies=cookies if cookies in BROWSERS else "")
        self._thread = threading.Thread(target=self._run, args=(self.job,), daemon=True)
        self._thread.start()

    def retry_failed(self) -> int:
        job = self.job
        if not job or self.busy():
            return 0
        n = 0
        for it in job.items:
            if it.state in ("error", "cancelled"):
                it.state, it.error, it.progress = "queued", "", 0.0
                n += 1
        if n:
            self._cancel.clear()
            self._skip.clear()
            job.running = True
            self._thread = threading.Thread(target=self._run, args=(job,), daemon=True)
            self._thread.start()
        return n

    def cancel(self) -> None:
        self._cancel.set()

    def skip_current(self) -> None:
        self._skip.set()

    def busy(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def snapshot(self) -> dict | None:
        job = self.job
        if not job:
            return None
        with self._lock:
            items = [dict(vars(it)) for it in job.items]
        counts = {}
        for it in items:
            counts[it["state"]] = counts.get(it["state"], 0) + 1
        return {"running": self.busy(), "folder": job.folder, "mode": job.mode,
                "items": items, "counts": counts, "total": len(items)}

    def _run(self, job: Job) -> None:
        try:
            for it in job.items:
                if it.state != "queued":
                    continue
                if self._cancel.is_set():
                    it.state = "cancelled"
                    continue
                self._skip.clear()
                if any(x.state == "done" for x in job.items) and self._wait(2):
                    if self._cancel.is_set():
                        it.state = "cancelled"
                        continue
                    self._skip.clear()
                self._download_one(job, it)
        finally:
            job.running = False

    def _download_one(self, job: Job, it: Item) -> None:
        has_ffmpeg = bool(self.tools.get("ffmpeg"))
        prefix = f"{it.index:03d} - " if job.numbered else ""
        opts = {
            "quiet": True, "no_warnings": True, "noprogress": True, "logger": _QuietLogger(),
            "noplaylist": True,
            "paths": {"home": job.folder, "temp": job.folder},
            "outtmpl": {"default": prefix + "%(title).110s.%(ext)s"},
            "windowsfilenames": True,
            "trim_file_name": 180,
            "continuedl": True,
            "retries": 10, "fragment_retries": 10,
            "concurrent_fragment_downloads": 4,
            "progress_hooks": [lambda d: self._on_progress(it, d)],
            "postprocessor_hooks": [lambda d: self._on_post(it, d)],
            "postprocessors": [],
        }
        if job.mode == "audio":
            if job.audio_format == "mp3" and has_ffmpeg:
                opts["format"] = "ba/b"
                opts["postprocessors"].append(
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"})
            else:
                opts["format"] = "ba[ext=m4a]/ba/b"
                if has_ffmpeg:
                    opts["postprocessors"].append({"key": "FFmpegExtractAudio", "preferredcodec": "m4a"})
        else:
            if has_ffmpeg:
                opts["format"] = "bv*+ba/b"
                opts["merge_output_format"] = "mp4"
                # Prefer H.264/AAC so the file plays on any phone, TV or old laptop.
                sort = ["vcodec:h264", "acodec:aac", "ext:mp4:m4a"]
                if job.quality != "best":
                    sort.insert(0, f"res:{job.quality}")
                opts["format_sort"] = sort
            else:
                # Without ffmpeg only single-file (video+audio together) formats can be saved.
                h = "" if job.quality == "best" else f"[height<={job.quality}]"
                opts["format"] = f"b{h}[ext=mp4]/b{h}/b"
        if has_ffmpeg:
            opts["postprocessors"].append({"key": "FFmpegMetadata", "add_metadata": True})
        if job.cookies:
            opts["cookiesfrombrowser"] = (job.cookies,)

        url = f"https://www.youtube.com/watch?v={it.id}"
        for attempt in range(3):
            it.state, it.progress, it.error = "downloading", 0.0, ""
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    path = _final_path(info)
                    if path:
                        it.file = path
                        try:
                            it.size = os.path.getsize(path)
                        except OSError:
                            pass
                it.state, it.progress = "done", 1.0
                return
            except DownloadCancelled:
                it.state = "cancelled" if self._cancel.is_set() else "skipped"
                _clean_partials(job.folder)
                return
            except Exception as e:  # yt-dlp raises many kinds; show the reason, keep going.
                it.state, it.error = "error", _friendly_error(e)
                # YouTube's "are you a bot" check usually clears after a short pause.
                if "bot" not in str(e).lower() or attempt == 2:
                    return
                it.state, it.error = "waiting", "ইউটিউব একটু থামতে বলছে, কিছুক্ষণ পরে আবার চেষ্টা হবে…"
                if self._wait(30 * (attempt + 1)):
                    it.state, it.error = "cancelled", ""
                    return
            finally:
                it.speed = it.eta = None
                it.part = ""

    def _wait(self, seconds: int) -> bool:
        """Sleep, waking early on cancel/skip. True if the user stopped it."""
        end = time.time() + seconds
        while time.time() < end:
            if self._cancel.is_set() or self._skip.is_set():
                return True
            time.sleep(0.5)
        return False

    def _on_progress(self, it: Item, d: dict) -> None:
        if self._cancel.is_set() or self._skip.is_set():
            raise DownloadCancelled()
        with self._lock:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes") or 0
                it.progress = min(done / total, 1.0) if total else 0.0
                it.speed, it.eta = d.get("speed"), _int(d.get("eta"))
                it.size = total
                fmt = (d.get("info_dict") or {})
                if fmt.get("vcodec") not in (None, "none") and fmt.get("acodec") in (None, "none"):
                    it.part = "ভিডিও"
                elif fmt.get("acodec") not in (None, "none") and fmt.get("vcodec") in (None, "none"):
                    it.part = "অডিও"
                else:
                    it.part = ""
            elif d.get("status") == "finished":
                it.progress = 1.0

    def _on_post(self, it: Item, d: dict) -> None:
        if d.get("status") == "started":
            with self._lock:
                it.state, it.speed, it.eta, it.part = "processing", None, None, ""


# ---------- helpers ----------

def _int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_name(name: str) -> str:
    name = sanitize_filename(name, restricted=False).strip(" .")
    return name[:120] or "YouTube"


def _final_path(info: dict) -> str:
    for r in info.get("requested_downloads") or []:
        if r.get("filepath"):
            return r["filepath"]
    return info.get("filepath") or info.get("_filename") or ""


def _clean_partials(folder: str) -> None:
    # A cancelled download leaves .part/.ytdl files; keep them (resume) unless they are fragments.
    for p in Path(folder).glob("*.part-Frag*"):
        try:
            p.unlink()
        except OSError:
            pass


def _friendly_error(e: Exception) -> str:
    msg = str(e)
    msg = re.sub(r"\x1b\[[0-9;]*m", "", msg).replace("ERROR: ", "")
    msg = re.sub(r"^\[youtube\] [A-Za-z0-9_-]{11}: ", "", msg)
    low = msg.lower()
    if "private video" in low:
        return "ভিডিওটি প্রাইভেট।"
    if "video unavailable" in low or "has been removed" in low:
        return "ভিডিওটি আর পাওয়া যায় না।"
    if "sign in to confirm your age" in low:
        return "বয়স-সীমাবদ্ধ ভিডিও, লগইন ছাড়া ডাউনলোড করা যায় না।"
    if "sign in to confirm" in low and "bot" in low:
        return "ইউটিউব সাময়িকভাবে আটকে দিয়েছে। কিছুক্ষণ পরে আবার চেষ্টা করুন।"
    if "members-only" in low or "join this channel" in low:
        return "শুধু চ্যানেল-মেম্বারদের ভিডিও।"
    if "live event will begin" in low or "is a live" in low or "premieres in" in low:
        return "লাইভ বা প্রিমিয়ার এখনো শুরু হয়নি।"
    if any(s in low for s in ("getaddrinfo", "timed out", "connection", "network is unreachable", "urlopen error")):
        return "ইন্টারনেট সংযোগে সমস্যা।"
    if "no space left" in low:
        return "ডিস্কে জায়গা নেই।"
    return msg[:300]
