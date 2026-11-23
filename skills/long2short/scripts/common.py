"""Shared paths and helpers for long2short.

A *project* is a folder (default: ``<video folder>/long2short``) with ``project.json``:
    {"src": "/abs/video.mp4", "lang": "de", "width": 3840, "height": 2160,
     "fps": "30000/1001", "out": "/abs/output/folder", "glossary": {"Air bee and bee": "Airbnb"}}
All commands run with the project folder as working directory (``l2s.py -p <project> ...``).
"""
import json, os, subprocess, sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("L2S_CACHE", Path.home() / ".cache" / "long2short"))
ASSETS = CACHE / "assets"          # downloaded by `l2s.py setup` – nothing is shipped with the skill
VENV_PY = CACHE / "venv" / "bin" / "python"
BIN = CACHE / "bin"


def project(path="."):
    p = Path(path).resolve()
    f = p / "project.json"
    if not f.exists():
        sys.exit(f"no project.json in {p} – run: l2s.py init <video>")
    cfg = json.loads(f.read_text())
    cfg["_dir"] = p
    return cfg


def fps(cfg):
    a, _, b = str(cfg.get("fps", "30000/1001")).partition("/")
    return float(a) / float(b or 1)


def crop_w(cfg):
    """width of a full-height 9:16 window in source pixels (even)"""
    return int(round(cfg["height"] * 9 / 16 / 2) * 2)


def swift_bin(name):
    """compile scripts/<name>.swift once into the cache (macOS / Apple Vision)"""
    out = BIN / name
    src = SKILL / "scripts" / f"{name}.swift"
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        BIN.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", "-O", str(src), "-o", str(out)], check=True)
    return str(out)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def decode_args(src):
    """ffmpeg input options for decoding the source: VideoToolbox when the chip can decode the codec
    (H.264/HEVC/VP9/ProRes, AV1 on M3+), otherwise software – dav1d for AV1, which YouTube often serves."""
    hw = subprocess.run(["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", "-t", "0.5", "-i", str(src), "-an", "-f", "null", "-"],
                        capture_output=True, text=True)
    if hw.returncode == 0 and not hw.stderr.strip():
        return ["-hwaccel", "videotoolbox"]
    codec = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                                     "-of", "csv=p=0", str(src)], text=True).strip()
    decs = subprocess.run(["ffmpeg", "-hide_banner", "-decoders"], capture_output=True, text=True).stdout
    return ["-c:v", "libdav1d"] if codec == "av1" and " libdav1d " in decs else []


def duration(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(path)]).decode())
