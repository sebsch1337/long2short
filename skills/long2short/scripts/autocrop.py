"""Propose a 9:16 crop plan for one clip automatically.

usage (via l2s.py plan): autocrop.py clips/clipNN "A-B[,C-D...]" [--teaser VSTART VEND ASTART] [--seed T:CX:CY ...]
  --seed: rough position of an object (drone, robot) at source time T -> tracked with Apple Vision
  ranges are absolute source seconds; segments are joined in order (optional teaser first)

 - subject per frame (Apple Vision): largest face > upper body; objects only via --seed tracking
 - a detected scene boundary becomes a hard crop cut only if it looks like a cut (phase
   correlation) AND the subject jumps; pans stay smooth
 - camera: median filter, dead zone, speed limit, never past the wide-angle edges
 - writes spec.json (keys [t, cx, cy], cuts, fit) and spec.review.jpg; prints ANOMALIES only
   when something deserves a look (token saving: no anomaly -> no need to open the sheet)
"""
import json, os, subprocess, sys, tempfile, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import project, swift_bin, crop_w
PRJ = project(".")          # run with the project folder as cwd
WORK = str(PRJ["_dir"])
PROXY = os.path.join(WORK, "proxy.mp4"); SRC = PRJ["src"]
FPS = 5.0
CW = crop_w(PRJ) / PRJ["width"]
LO, HI = 0.25, 0.75             # outer wide-angle zone warps when the window moves across it
DEAD, VMAX = 0.07, 0.22
PEAK_CUT, JUMP_CUT = 0.10, 0.15
WIDE = 0.42                # salient region wider than this (fraction of width) does not fit 9:16
HOLD_MIN = 1.5             # person-less stretch this long -> reported (seed an object or keep centre)
EDGE_T = 0.12              # targets this close to the frame edge are half out of shot -> ignored
SWING = 0.035              # global image shift per 0.2 s above this = the camera itself swings -> crop holds still

def frames(a, b, d):
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a}", "-to", f"{b}", "-i", PROXY,
                    "-vf", f"fps={FPS}", "-q:v", "3", os.path.join(d, "f%05d.jpg")], check=True)
    return sorted(os.listdir(d))

def vision(d):
    binp = swift_bin("vision_track")
    out = subprocess.run([binp, d], capture_output=True, text=True, check=True).stdout
    return {j["file"]: j for j in map(json.loads, out.splitlines())}

def grab(t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", PROXY, "-frames:v", "1",
                          "-vf", "scale=160:90", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(90, 160, 3).astype(float)

def phase_peak(t):
    a, b = grab(t - 0.12).mean(2), grab(t + 0.08).mean(2)
    a = (a - a.mean()) / (a.std() + 1e-6); b = (b - b.mean()) / (b.std() + 1e-6)
    w = np.hanning(90)[:, None] * np.hanning(160)[None]
    F = np.fft.fft2(a * w) * np.conj(np.fft.fft2(b * w))
    return float(np.fft.ifft2(F / (np.abs(F) + 1e-9)).real.max())

def target(det):
    """-> (cx, cy, kind)"""
    if det and det["faces"]:
        f = max(det["faces"], key=lambda r: r[2] * r[3]); return f[0] + f[2] / 2, f[1] + f[3] / 2, "face"
    if det and det["humans"]:
        h = max(det["humans"], key=lambda r: r[2] * r[3]); return h[0] + h[2] / 2, h[1] + h[3] * 0.25, "body"
    # generic saliency proved unreliable (picked masts/roofs) -> objects only via --seed tracking
    return None, None, "none"

def rdp(pts, eps):
    """Ramer-Douglas-Peucker on (t, x) points – x tolerance eps"""
    if len(pts) < 3: return pts
    (t0, x0), (t1, x1) = pts[0], pts[-1]
    d = [abs(x - (x0 + (x1 - x0) * (t - t0) / max(t1 - t0, 1e-9))) for t, x in pts[1:-1]]
    k = int(np.argmax(d)) + 1
    if d[k - 1] <= eps: return [pts[0], pts[-1]]
    return rdp(pts[:k + 1], eps)[:-1] + rdp(pts[k:], eps)

def follow(xs):
    known = [x for x in xs if x is not None]
    cam = float(np.median(known[:8])) if known else 0.5
    out = []
    for x in xs:
        if x is not None and abs(x - cam) > DEAD:
            cam += np.sign(x - cam) * min(abs(x - cam) - DEAD * 0.5, VMAX / FPS)
        cam = min(HI, max(LO, cam)); out.append(cam)
    return out

def medfilt(v, r=3):
    out = []
    for k in range(len(v)):
        span = v[max(0, k - r):k + r + 1]; win = [x for x in span if x is not None]
        out.append(float(np.median(win)) if len(win) >= max(1, len(span) // 2) else None)
    return out

def refine_seed(path, cx, cy, r=0.10):
    """snap a rough seed to the strongest local-contrast blob within +-r (e.g. a drone against the sky)"""
    from PIL import ImageFilter
    im = Image.open(path).convert("L"); W, H = im.size
    a = np.asarray(im, float); bg = np.asarray(im.filter(ImageFilter.MedianFilter(21)), float)
    c = np.abs(bg - a)
    x0, x1 = int(max(0, cx - r) * W), int(min(1, cx + r) * W); y0, y1 = int(max(0, cy - r * 1.6) * H), int(min(1, cy + r * 1.6) * H)
    sub = c[y0:y1, x0:x1]; y, x = np.unravel_index(sub.argmax(), sub.shape)
    return (x + x0) / W, (y + y0) / H

def track(tmp, fl, ts, seed_t, cx, cy):
    """follow an object (seeded once) with Apple Vision's tracker -> {frame index: (cx, cy)}"""
    i0 = int(np.argmin([abs(t - seed_t) for t in ts]))
    cx, cy = refine_seed(os.path.join(tmp, fl[i0]), cx, cy)
    binp = swift_bin("vision_follow")
    out = subprocess.run([binp, tmp, str(i0), f"{cx - 0.025}", f"{cy - 0.04}", "0.05", "0.08"],
                         capture_output=True, text=True).stdout
    return {j["i"]: (j["cx"], j["cy"]) for j in map(json.loads, out.splitlines())}

def swing(tmp, fl):
    """per frame: does the source camera itself move fast? (phase-correlation shift to the previous frame)"""
    out, prev = [False], None
    for f in fl:
        g = np.asarray(Image.open(os.path.join(tmp, f)).convert("L").resize((160, 90)), float)
        g = (g - g.mean()) / (g.std() + 1e-6)
        if prev is not None:
            w = np.hanning(90)[:, None] * np.hanning(160)[None]
            F = np.fft.fft2(prev * w) * np.conj(np.fft.fft2(g * w)); r = np.fft.ifft2(F / (np.abs(F) + 1e-9)).real
            dy, dx = np.unravel_index(r.argmax(), r.shape)
            dx = dx - 160 if dx > 80 else dx; dy = dy - 90 if dy > 45 else dy
            out.append(max(abs(dx) / 160, abs(dy) / 90) > SWING or r.max() < 0.06)
        prev = g
    return out

def plan(a, b, scenes, tmp, seeds=()):
    for f in os.listdir(tmp): os.remove(os.path.join(tmp, f))
    fl = frames(a, b, tmp); det = vision(tmp)
    ts = [a + i / FPS for i in range(len(fl))]
    raw = [target(det.get(f)) for f in fl]
    for st, sx, sy in seeds:                       # objects (drone, robot, car): seeded tracking
        if a <= st < b:
            for i, (ox, oy) in track(tmp, fl, ts, st, sx, sy).items():
                if raw[i][2] not in ("face",): raw[i] = (ox, oy, "object")
    # ignore half-out-of-shot targets and everything while the source camera swings (prevents the
    # crop from hunting back and forth on top of the camera's own motion = "underwater" wobble)
    sw = swing(tmp, fl)
    raw = [(None, None, "none") if (r[0] is not None and (r[0] < EDGE_T or r[0] > 1 - EDGE_T)) or sw[i] else r
           for i, r in enumerate(raw)]
    xs = [r[0] for r in raw]; kinds = [r[2] for r in raw]
    bounds = [s["s"] for s in scenes if a + 0.3 < s["s"] < b - 0.3]
    # every cut-LIKE boundary is a barrier: no smoothing across it, position may jump there.
    # (smoothing across a real cut made the crop drift into the old shot before the cut)
    cuts = [t for t in bounds if phase_peak(t) < PEAK_CUT]
    anomalies = []
    snap = lambda t: min(bounds, key=lambda x: abs(x - t)) if bounds and min(abs(x - t) for x in bounds) <= 0.4 else t
    edges = [a] + cuts + [b + 1]
    keys, fit, cams = [], [], [0.5] * len(ts)          # fit stays empty: letterbox layout removed
    for s0, s1 in zip(edges, edges[1:]):
        idx = [i for i, t in enumerate(ts) if s0 <= t < s1]
        if not idx: continue
        # person-less stretches: crop holds (or follows a seeded object); report them so an object can be seeded
        person = [kinds[i] in ("face", "body", "object") for i in idx]
        k = 0
        while k < len(idx):
            if person[k]: k += 1; continue
            j = k
            while j < len(idx) and not person[j]: j += 1
            if (j - k) / FPS >= HOLD_MIN:
                anomalies.append(f"{ts[idx[k]]:.1f}-{ts[idx[j - 1]]:.1f}s: no person -> crop holds; object worth following? re-run with --seed T:CX:CY")
            k = j
        for i in idx:
            if kinds[i] not in ("face", "body", "object"): xs[i] = None
        cam = follow(medfilt([xs[i] for i in idx], 5))   # +-1 s persistence before the crop reacts
        cys = medfilt([raw[i][1] for i in idx], 5); cy0 = next((c for c in cys if c is not None), 0.42)
        cyf = [c if c is not None else cy0 for c in cys]
        # keep only the keys that matter (Ramer-Douglas-Peucker, 1.5 % of the width): the camera then
        # makes a few deliberate moves and holds in between, like a hand-set path, instead of hunting
        pts = [(max(s0, a), cam[0])] + [(ts[idx[k]], cam[k]) for k in range(1, len(idx))] + [(min(s1, b) - 0.001, cam[-1])]
        for t, x in rdp(pts, 0.015):
            k = min(range(len(idx)), key=lambda q: abs(ts[idx[q]] - t))
            keys.append([round(t, 3), round(x, 3), round(cyf[k], 3)])
        for i, c in zip(idx, cam): cams[i] = c
        fast = (np.abs(np.diff(cam)) > VMAX / FPS * 0.9) if len(cam) > 1 else np.array([False])
        run = best = 0
        for f in fast: run = run + 1 if f else 0; best = max(best, run)
        if best > FPS * 2.0:
            anomalies.append(f"{s0:.1f}-{min(s1, b):.1f}s: crop pans at its speed limit for long (fast/unsteady subject)")
    return dict(keys=keys, cuts=cuts, fit=fit, bounds=bounds), anomalies, (fl, ts, cams, raw, fit)

def sheet(parts, path):
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 14)
    tiles = []
    for d, (fl, ts, cams, raw, fit) in parts:
        for i in range(0, len(fl), int(FPS * 1.5)):
            im = Image.open(os.path.join(d, fl[i])).convert("RGB").resize((320, 180)); dr = ImageDraw.Draw(im)
            if any(f0 <= ts[i] < f1 for f0, f1 in fit):
                dr.rectangle([0, 0, 319, 179], outline=(0, 200, 255), width=4); lab = "FIT"
            else:
                x0 = (cams[i] - CW / 2) * 320; dr.rectangle([x0, 0, x0 + CW * 320, 179], outline=(255, 220, 0), width=3); lab = ""
            for g in range(1, 10):
                dr.line([g * 32, 0, g * 32, 179], fill=(0, 255, 255)); dr.line([0, g * 18, 319, g * 18], fill=(0, 255, 255))
                dr.text((g * 32 + 1, 168), str(g), fill=(0, 255, 255)); dr.text((1, g * 18 - 7), str(g), fill=(0, 255, 255))
            if raw[i][0] is not None:
                cyy = (raw[i][1] if raw[i][1] is not None else 0.5) * 180
                dr.ellipse([raw[i][0] * 320 - 4, cyy - 4, raw[i][0] * 320 + 4, cyy + 4], fill=(255, 0, 80))
            dr.rectangle([0, 0, 110, 16], fill=0); dr.text((2, 0), f"{ts[i]:.1f} {lab}", fill=(255, 230, 0), font=font)
            tiles.append(im)
    cols = 6; rows = (len(tiles) + cols - 1) // cols
    sh = Image.new("RGB", (320 * cols, 180 * rows))
    for k, im in enumerate(tiles): sh.paste(im, ((k % cols) * 320, (k // cols) * 180))
    sh.save(path, quality=80)

if __name__ == "__main__":
    d = sys.argv[1]; os.makedirs(d, exist_ok=True)
    ranges = [tuple(map(float, r.split("-"))) for r in sys.argv[2].split(",")]
    scenes = json.load(open(os.path.join(WORK, "scenes.json")))
    jobs = []
    if "--teaser" in sys.argv:
        k = sys.argv.index("--teaser"); vs, ve, ast = map(float, sys.argv[k + 1:k + 4]); jobs.append((vs, ve, ast))
    jobs += [(a, b, None) for a, b in ranges]
    seeds = [tuple(map(float, sys.argv[k + 1].split(":"))) for k, v in enumerate(sys.argv) if v == "--seed"]
    segs, allanom, parts, tmps = [], [], [], []
    try:
        for a, b, ast in jobs:
            tmp = tempfile.mkdtemp(); tmps.append(tmp)
            p, an, vis = plan(a, b, scenes, tmp, seeds)
            seg = {"start": a, "end": b, **p}
            if ast is not None: seg["astart"] = ast
            segs.append(seg); allanom += an; parts.append((tmp, vis))
        sheet(parts, os.path.join(d, "spec.review.jpg"))
    finally:
        for t in tmps: shutil.rmtree(t, ignore_errors=True)
    json.dump({"src": SRC, "out": f"{d}/base.mov", "segments": segs}, open(os.path.join(d, "spec.json"), "w"))
    print(f"segments {len(segs)}, cuts {sum(len(s['cuts']) for s in segs)}, fit {[f for s in segs for f in s['fit']]}")
    print("ANOMALIES:" if allanom else "no anomalies", *allanom, sep="\n  ")
