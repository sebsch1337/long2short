"""Cut segments from the 4K source into one 1080x1920 clip (single 9:16 window, no zoom, no letterbox).

usage: cropcut.py clips/clipNN/spec.json
spec: {src, out, segments:[{start, end, astart?, keys:[[t_abs, cx, cy?],...], cuts:[t_abs,...]}]}

Clean edges: if a scene change lies within 0.6 s inside a segment's start or end, the picture is
trimmed to that scene change and the gap is filled by holding the first/last frame of the wanted
shot (audio stays untouched) -> no frames of the neighbouring shot ever leak in.
Output: ProRes 422 HQ via VideoToolbox (.mov) or x264 (.mp4); audio -14 LUFS.
"""
import json, os, subprocess, sys
import numpy as np

spec = json.load(open(sys.argv[1])); D = os.path.dirname(os.path.abspath(sys.argv[1]))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import project, fps, crop_w
PRJ = project(".")
SCENES = [s["s"] for s in json.load(open(PRJ["_dir"] / "scenes.json"))]
W, H = PRJ["width"], PRJ["height"]; CW = crop_w(PRJ); FR = fps(PRJ)
EDGE = 0.6

def path(seg, col):
    """dense per-frame value: linear between keys, hard jumps at cuts, gaussian (0.25 s) inside each stretch"""
    s0, s1 = seg["start"], seg["end"]; keys = sorted(seg["keys"]); cuts = sorted(seg.get("cuts", []))
    n = int(np.ceil((s1 - s0) * FR)) + 2; t = s0 + np.arange(n) / FR
    kt = np.array([k[0] for k in keys]); kv = np.array([k[col] for k in keys])
    v = np.empty(n); edges = [s0 - 1] + cuts + [s1 + 1]
    for e0, e1 in zip(edges, edges[1:]):
        m = (t >= e0) & (t < e1)
        if not m.any(): continue
        km = (kt >= e0 - 1e-6) & (kt < e1)
        if km.sum() == 0:
            prev = kv[kt < e0]; v[m] = prev[-1] if len(prev) else kv[0]; continue
        xs = np.interp(t[m], kt[km], kv[km])
        sig = 0.25 * FR; r = int(3 * sig); g = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2); g /= g.sum()
        v[m] = np.convolve(np.pad(xs, r, mode="edge"), g, mode="valid")
    return t - s0, v

cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
fc, n = [], len(spec["segments"])
for i, seg in enumerate(spec["segments"]):
    s0, s1 = seg["start"], seg["end"]
    head = [b for b in SCENES if s0 < b <= s0 + EDGE]; tail = [b for b in SCENES if s1 - EDGE <= b < s1]
    v0 = max(head) if head else s0; v1 = min(tail) if tail else s1
    cmd += ["-hwaccel", "videotoolbox", "-ss", f"{v0}", "-to", f"{v1}", "-i", PRJ["src"]]
    cmd += ["-ss", f"{seg.get('astart', s0)}", "-t", f"{s1 - s0}", "-i", PRJ["src"]]
    tt, cx = path(seg, 1)
    wx = np.clip(cx * W - CW / 2, 0, W - CW)
    cf = os.path.join(D, f"crop{i}.cmd")
    with open(cf, "w") as fh:            # times relative to the trimmed picture start v0
        for a, x in zip(tt, wx):
            if a >= v0 - s0 - 1e-6: fh.write(f"{a - (v0 - s0):.4f} crop@w{i} x {x:.1f};\n")
    pad = []
    if v0 > s0: pad.append(f"start_mode=clone:start_duration={v0 - s0:.4f}")
    if v1 < s1: pad.append(f"stop_mode=clone:stop_duration={s1 - v1:.4f}")
    tp = f",tpad={':'.join(pad)}" if pad else ""
    x0 = wx[min(len(wx) - 1, int(round((v0 - s0) * FR)))]
    fc.append(f"[{2*i}:v]fps={PRJ.get('fps', '30000/1001')},sendcmd=f='{cf}',crop@w{i}={CW}:{H}:{x0:.1f}:0,scale=1080:1920:flags=lanczos{tp},"
              f"trim=duration={s1 - s0:.4f},setpts=PTS-STARTPTS,setsar=1[v{i}]")
    fc.append(f"[{2*i+1}:a]aresample=48000,afade=t=in:d=0.03,afade=t=out:st={s1 - s0 - 0.04:.3f}:d=0.04[a{i}]")
    if head or tail: print(f"segment {i}: picture trimmed to scene changes {v0:.2f}-{v1:.2f} (held {v0 - s0:.2f}s / {s1 - v1:.2f}s)")
fc.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a0]")
fc.append("[a0]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]"]
if spec["out"].endswith(".mov"):
    cmd += ["-c:v", "prores_videotoolbox", "-profile:v", "hq", "-pix_fmt", "p210le", "-c:a", "pcm_s16le", spec["out"]]
else:
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", spec["out"]]
subprocess.run(cmd, check=True); print("ok", spec["out"])
