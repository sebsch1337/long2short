"""Final assembly: base video + transparent graphics layer + sound effects -> short-form MP4 (one lossy encode).

usage (via l2s.py compose): compose.py clips/clipNN/hf_config.json <overlay.mov> <out.mp4>

Sound cues in hf_config.json "sfx":
  {"sound": "pop", "at": 12.3, "volume": 0.4}   # sound = file name in hf/assets/sfx without .mp3
  "at" is the moment the sound should HIT; the cue starts earlier by the sound's own peak offset.
  (legacy: {"file": "assets/sfx/x.mp3", "start": 12.2})
"""
import json, os, subprocess, sys
import numpy as np

cfg = json.load(open(sys.argv[1])); ov, out = sys.argv[2], sys.argv[3]
d = os.path.dirname(os.path.abspath(sys.argv[1])); base = f"{d}/base.mov" if os.path.exists(f"{d}/base.mov") else f"{d}/base.mp4"
proj = cfg["project"]; DUR = cfg["duration"]

def peak(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(float)
    env = [np.sqrt(np.mean(a[i:i + 400] ** 2)) for i in range(0, max(len(a) - 400, 1), 400)]
    return float(np.argmax(env)) * 0.05

cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", base, "-i", ov]
# "cover": [[start, end], ...] blurs a horizontal band (default y 1660-1880, set "cover_band") where the
# source has burned-in subtitles, so they don't clash with our captions
cov = cfg.get("cover", [])
if cov:
    y0, y1 = cfg.get("cover_band", [1660, 1880]); en = "+".join(f"between(t,{a},{b})" for a, b in cov)
    fc = [f"[0:v]split[b0][b1];[b1]crop=1080:{y1 - y0}:0:{y0},format=yuv444p,boxblur=28:3,eq=brightness=-0.06[bl];"
          f"[b0][bl]overlay=0:{y0}:enable='{en}'[bv];[bv][1:v]overlay=0:0:format=auto:shortest=1,format=yuv420p[v]"]
else:
    fc = ["[0:v][1:v]overlay=0:0:format=auto:shortest=1,format=yuv420p[v]"]
mix = ["[0:a]"]
for i, c in enumerate(cfg.get("sfx", [])):
    f = os.path.join(proj, c["file"]) if "file" in c else os.path.join(proj, "assets", "sfx", c["sound"] + ".mp3")
    start = c["start"] if "start" in c else c["at"] - peak(f)
    cmd += ["-i", f]
    ms = int(round(max(0, start) * 1000))
    fc.append(f"[{i+2}:a]aresample=48000,volume={c.get('volume', 0.35)},adelay={ms}|{ms}[s{i}]")
    mix.append(f"[s{i}]")
fc.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,atrim=0:{DUR},afade=t=out:st={DUR - 0.08:.3f}:d=0.08,alimiter=limit=0.89:level=false[a]")
cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-t", f"{DUR}",
        "-c:v", "libx264", "-preset", "medium", "-b:v", "12M", "-maxrate", "16M", "-bufsize", "24M", "-g", "60",
        "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
subprocess.run(cmd, check=True); print("ok", out)
