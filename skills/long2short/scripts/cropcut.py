"""Cut segments from the 4K source into one 1080x1920 clip (single 9:16 window, no zoom, no letterbox).

usage: cropcut.py clips/clipNN/spec.json
spec: {src, out, segments:[{start, end, astart?, keys:[[t_abs, cx, cy?],...], cuts:[t_abs,...]}]}

Clean edges: if a scene change lies within 0.6 s inside a segment's start or end, the picture is
trimmed to that scene change and the gap is filled by holding the first/last frame of the wanted
shot (audio stays untouched) -> no frames of the neighbouring shot ever leak in.
Sub-pixel window placement (OpenCV) -> smooth pans. Output: ProRes 422 HQ via VideoToolbox (.mov)
or x264 (.mp4); audio -14 LUFS.
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

# ---- rendering ---------------------------------------------------------------------------------
# The 9:16 window is cut with SUB-PIXEL precision per frame (OpenCV warpAffine, Lanczos) instead of
# ffmpeg's crop filter: crop can only move in whole (even) pixels and its per-frame commands can land a
# frame late – both make slow pans judder. Frames are decoded once (VideoToolbox), transformed in
# Python and piped into the encoder; audio is processed separately and muxed losslessly.
import cv2

S = 1080 / CW                                   # scale from source window to output (window height -> 1920)
segs = spec["segments"]; tmpv = spec["out"] + ".video.mov"; tmpa = spec["out"] + ".audio.wav"

def reader(v0, v1):
    return subprocess.Popen(["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", "-ss", f"{v0}", "-to", f"{v1}", "-i", PRJ["src"],
                             "-vf", f"fps={PRJ.get('fps', '30000/1001')}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                            stdout=subprocess.PIPE, bufsize=W * H * 3 * 2)

venc = ["-c:v", "prores_videotoolbox", "-profile:v", "hq", "-pix_fmt", "p210le"] if spec["out"].endswith(".mov") else \
       ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-g", "30", "-pix_fmt", "yuv420p"]
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1080x1920",
                        "-r", str(PRJ.get("fps", "30000/1001")), "-i", "-", *venc, tmpv], stdin=subprocess.PIPE)
FB = W * H * 3
for i, seg in enumerate(segs):
    s0, s1 = seg["start"], seg["end"]
    head = [b for b in SCENES if s0 < b <= s0 + EDGE]; tail = [b for b in SCENES if s1 - EDGE <= b < s1]
    v0 = max(head) if head else s0; v1 = min(tail) if tail else s1      # never show the neighbouring shot
    tt, cx = path(seg, 1)
    wx = np.clip(cx * W - CW / 2, 0, W - CW)
    nout = int(round((s1 - s0) * FR))
    r = reader(v0, v1); cur, k = None, -1
    for j in range(nout):
        t = s0 + j / FR
        want = int(round((min(max(t, v0), v1 - 1 / FR) - v0) * FR))   # frame index inside [v0, v1) (holds at the edges)
        while k < want:
            buf = r.stdout.read(FB)
            if len(buf) < FB: break                                     # stream ended: keep the last frame
            cur = np.frombuffer(buf, np.uint8).reshape(H, W, 3); k += 1
        x = float(wx[min(j, len(wx) - 1)])
        M = np.float32([[S, 0, -x * S], [0, S, 0]])
        enc.stdin.write(cv2.warpAffine(cur, M, (1080, 1920), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE).tobytes())
    r.stdout.close(); r.wait()
    if head or tail: print(f"segment {i}: picture trimmed to scene changes {v0:.2f}-{v1:.2f} (held {v0 - s0:.2f}s / {s1 - v1:.2f}s)")
enc.stdin.close(); enc.wait()

# audio: same segments (J-cut via astart), short fades at the joins, loudness -14 LUFS
cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
fc = []
for i, seg in enumerate(segs):
    L = seg["end"] - seg["start"]
    cmd += ["-ss", f"{seg.get('astart', seg['start'])}", "-t", f"{L}", "-i", PRJ["src"]]
    fc.append(f"[{i}:a]aresample=48000,afade=t=in:d=0.03,afade=t=out:st={L - 0.04:.3f}:d=0.04[a{i}]")
fc.append("".join(f"[a{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
subprocess.run(cmd + ["-filter_complex", ";".join(fc), "-map", "[a]", "-c:a", "pcm_s16le", tmpa], check=True)
acodec = ["-c:a", "pcm_s16le"] if spec["out"].endswith(".mov") else ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmpv, "-i", tmpa, "-map", "0:v", "-map", "1:a", "-c:v", "copy", *acodec, "-shortest", spec["out"]], check=True)
os.remove(tmpv); os.remove(tmpa)
print("ok", spec["out"])
