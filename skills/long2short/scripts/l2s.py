#!/usr/bin/env python3
"""long2short – turn a landscape video into captioned 9:16 short-form clips.

  l2s.py setup                          one-time: venv for forced alignment, compile Vision helpers
  l2s.py doctor                         check tools
  l2s.py init  <video> [--lang de] [--project DIR] [--whisper-model PATH]
                                          proxy, 16 kHz audio, word transcript, scene list, contact sheets
  l2s.py -p DIR plan  NN "A-B[,C-D]" [--teaser VS VE AS] [--seed T:CX:CY ...]
                                          automatic crop plan (Apple Vision) -> clips/NN/spec.json (+ review sheet)
  l2s.py -p DIR words NN                map transcript onto the clip, apply glossary -> words_raw.json
  l2s.py -p DIR align NN [NN ...]       forced alignment (MMS_FA) -> words_aligned.json
  l2s.py -p DIR cut   NN                4K -> 1080x1920 base.mov
  l2s.py -p DIR build NN                HyperFrames graphics project from clips/NN/hf_config.json
  l2s.py -p DIR render NN               transparent graphics layer -> overlay.mov
  l2s.py -p DIR compose NN NAME         base + overlay + sound effects -> <out>/NAME.mp4
  l2s.py -p DIR finish NN NAME          cut + build + render + compose
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SKILL, ASSETS, CACHE, VENV_PY, project, run, duration, swift_bin  # noqa: E402

S = SKILL / "scripts"
WHISPER_MODEL_DIRS = [Path.home() / "models" / "whisper", Path.home() / ".cache" / "whisper.cpp",
                      Path("/opt/homebrew/share/whisper-cpp"), Path.home() / ".cache" / "long2short" / "models"]


# ---------------------------------------------------------------- setup / doctor
# Everything the pipeline needs is downloaded here at install time – the skill itself ships only
# instructions and code. All sounds are CC0 (no attribution needed), the font is SIL OFL 1.1.
SOUNDS = {  # name: (download url, title, creator, page)
    "pop": ("https://cdn.freesound.org/previews/401/401542_2331641-hq.mp3", "Pop Sound", "ConarB13", "https://freesound.org/people/ConarB13/sounds/401542"),
    "whoosh": ("https://cdn.freesound.org/previews/60/60026_71257-hq.mp3", "Swosh swoosh whoosh air sound", "qubodup", "https://freesound.org/people/qubodup/sounds/60026"),
    "impact": ("https://cdn.freesound.org/previews/512/512389_3997858-hq.mp3", "Bass Impact - Ki_01", "Kievinay", "https://freesound.org/people/Kievinay/sounds/512389"),
    "kaching": ("https://cdn.freesound.org/previews/728/728224_15719741-hq.mp3", "cash register chching", "disman", "https://freesound.org/people/disman/sounds/728224"),
}
TRIM = {"impact": 2.2}   # seconds kept (long tail faded out)
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf"
FONT_LICENSE = "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/OFL.txt"
WHISPER_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium-q5_0.bin"


def fetch(url, dest):
    import urllib.request
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "long2short-setup"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def cmd_setup(a):
    # 1) private Python env for forced alignment + image work (never touches the global Python)
    if not VENV_PY.exists():
        run([sys.executable, "-m", "venv", str(CACHE / "venv")])
    run([str(VENV_PY), "-m", "pip", "install", "-q", "--upgrade", "pip"])
    run([str(VENV_PY), "-m", "pip", "install", "-q", "torch", "torchaudio", "numpy", "pillow", "opencv-python-headless"])
    # 2) Apple Vision helpers
    for n in ("vision_track", "vision_follow"):
        print("compiled", swift_bin(n))
    # 3) sound effects (CC0) and caption font (OFL)
    sfx = ASSETS / "sfx"; credits = ["# Sound effects – CC0 (public domain, no attribution required)"]
    for name, (url, title, creator, page) in SOUNDS.items():
        dest = sfx / f"{name}.mp3"
        if not dest.exists():
            tmp = sfx / f"_{name}.mp3"; fetch(url, tmp)
            if name in TRIM:
                t = TRIM[name]
                run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-t", str(t), "-af", f"afade=t=out:st={t - 0.6}:d=0.6", str(dest)]); tmp.unlink()
            else:
                tmp.rename(dest)
        credits.append(f"- {name}.mp3 – \"{title}\" by {creator} – {page}")
    (sfx / "CREDITS.md").write_text("\n".join(credits) + "\n")
    font = ASSETS / "fonts" / "montserrat-var.ttf"
    if not font.exists():
        fetch(FONT_URL, font); fetch(FONT_LICENSE, font.parent / "OFL.txt")
    # 4) a whisper.cpp model if none is installed
    if shutil.which("whisper-cli") and not find_model(None) and not a.no_model:
        print("downloading whisper model (~540 MB) ..."); fetch(WHISPER_URL, CACHE / "models" / "ggml-medium-q5_0.bin")
    print("setup done – run: l2s.py doctor")


def cmd_doctor(a):
    ok = True
    def chk(name, good, hint):
        nonlocal ok
        print(("  ok  " if good else "  --  ") + name + ("" if good else f"   -> {hint}"))
        ok &= bool(good)
    chk("ffmpeg/ffprobe", shutil.which("ffmpeg") and shutil.which("ffprobe"), "brew install ffmpeg")
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout if shutil.which("ffmpeg") else ""
    chk("ProRes via VideoToolbox", "prores_videotoolbox" in enc, "macOS + recent ffmpeg (falls back to x264 if .mp4 is used)")
    chk("swiftc (Apple Vision tracking, macOS)", shutil.which("swiftc"), "xcode-select --install")
    chk("node/npx (HyperFrames)", shutil.which("npx"), "brew install node")
    chk("whisper (whisper-cli or python whisper)", shutil.which("whisper-cli") or shutil.which("whisper"), "brew install whisper-cpp  (+ a ggml model) or pip install openai-whisper")
    chk("forced-alignment venv", VENV_PY.exists(), "l2s.py setup")
    chk("sounds + font downloaded", (ASSETS / "fonts" / "montserrat-var.ttf").exists() and len(list((ASSETS / "sfx").glob("*.mp3"))) >= 4, "l2s.py setup")
    chk("whisper.cpp model", find_model(None) or not shutil.which("whisper-cli"), "l2s.py setup (downloads ggml-medium-q5_0)")
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------- init
def find_model(explicit):
    if explicit: return explicit
    if os.environ.get("L2S_WHISPER_MODEL"): return os.environ["L2S_WHISPER_MODEL"]
    for d in WHISPER_MODEL_DIRS:
        if d.exists():
            ms = sorted(d.glob("ggml-*.bin"), key=lambda p: ("large" not in p.name, "medium" not in p.name, p.name))
            if ms: return str(ms[0])
    return None


def transcribe(audio, lang, out_json, model):
    """word-level transcript -> [{w, s, e}] ; timing only rough, final timing comes from forced alignment"""
    if shutil.which("whisper-cli") and model:
        base = str(out_json).replace(".json", "_wc")
        run(["whisper-cli", "-m", model, "-f", str(audio), "-l", lang, "-t", str(os.cpu_count() or 4),
             "-ml", "1", "-sow", "-oj", "-of", base], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        d = json.load(open(base + ".json"))
        w = [{"w": s["text"].strip(), "s": s["offsets"]["from"] / 1000, "e": s["offsets"]["to"] / 1000}
             for s in d["transcription"] if s["text"].strip()]
    else:
        py = str(VENV_PY) if VENV_PY.exists() else sys.executable
        code = ("import whisper,json,sys;m=whisper.load_model('medium');r=m.transcribe(sys.argv[1],language=sys.argv[2],word_timestamps=True);"
                "json.dump([{'w':x['word'].strip(),'s':x['start'],'e':x['end']} for s in r['segments'] for x in s['words']],open(sys.argv[3],'w'),ensure_ascii=False)")
        run([py, "-c", code, str(audio), lang, str(out_json)]); return
    json.dump(w, open(out_json, "w"), ensure_ascii=False)


def scenes(proxy, out_json, thr=0.15, min_len=0.5):  # 0.15 ≈ PySceneDetect ContentDetector(27) on a 640 px proxy
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(proxy), "-vf", f"select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    ts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    total = duration(proxy); b = [0.0]
    for t in ts:
        if t - b[-1] >= min_len: b.append(t)
    b.append(total)
    json.dump([{"i": i, "s": round(x, 3), "e": round(y, 3)} for i, (x, y) in enumerate(zip(b, b[1:]))], open(out_json, "w"))
    return len(b) - 1


def sheets(P):
    """one frame per scene, 4x5 tiles with time codes -> sheets/ (for spotting visual moments without speech)"""
    from PIL import Image, ImageDraw, ImageFont
    import io
    sc = json.load(open(P / "scenes.json")); (P / "sheets").mkdir(exist_ok=True)
    try: font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 18)
    except OSError: font = ImageFont.load_default()
    tiles = []
    for x in sc:
        png = subprocess.run(["ffmpeg", "-v", "error", "-ss", str((x["s"] + x["e"]) / 2), "-i", str(P / "proxy.mp4"), "-frames:v", "1",
                              "-vf", "scale=384:216", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
        im = Image.open(io.BytesIO(png)).convert("RGB"); d = ImageDraw.Draw(im)
        lab = f"#{x['i']} {int(x['s']//60):02d}:{x['s']%60:04.1f}-{int(x['e']//60):02d}:{x['e']%60:04.1f}"
        d.rectangle([0, 0, len(lab) * 10 + 8, 24], fill=(0, 0, 0)); d.text((4, 2), lab, fill=(255, 230, 0), font=font); tiles.append(im)
    for k in range(0, len(tiles), 20):
        sh = Image.new("RGB", (384 * 4, 216 * 5))
        for j, im in enumerate(tiles[k:k + 20]): sh.paste(im, ((j % 4) * 384, (j // 4) * 216))
        sh.save(P / "sheets" / f"sheet_{k // 20:02d}.jpg", quality=82)
    return (len(tiles) + 19) // 20


def cmd_init(a):
    src = Path(a.video).resolve()
    P = Path(a.pdir).resolve() if a.pdir else src.parent / "long2short"
    P.mkdir(parents=True, exist_ok=True)
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                                "stream=width,height,r_frame_rate", "-of", "json", str(src)]))["streams"][0]
    cfg = {"src": str(src), "lang": a.lang, "width": probe["width"], "height": probe["height"], "fps": probe["r_frame_rate"],
           "out": str(Path(a.out).resolve() if a.out else src.parent / "clips"), "glossary": {}}
    old = P / "project.json"
    if old.exists(): cfg["glossary"] = json.loads(old.read_text()).get("glossary", {})
    json.dump(cfg, open(old, "w"), indent=1, ensure_ascii=False)
    if not (P / "audio16k.wav").exists():
        run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(P / "audio16k.wav")])
    if not (P / "proxy.mp4").exists():
        run(["ffmpeg", "-v", "error", "-y", "-hwaccel", "videotoolbox", "-i", str(src), "-vf", "scale=640:-2",
             "-c:v", "h264_videotoolbox", "-b:v", "1500k", "-an", str(P / "proxy.mp4")])
    if not (P / "words.json").exists():
        transcribe(P / "audio16k.wav", a.lang, P / "words.json", find_model(a.whisper_model))
    n = scenes(P / "proxy.mp4", P / "scenes.json")
    k = sheets(P)
    w = json.load(open(P / "words.json"))
    lines, cur, t0 = [], [], None
    for x in w:
        if t0 is None: t0 = x["s"]
        cur.append(x["w"])
        if re.search(r"[.!?]$", x["w"]) or len(cur) > 30:
            lines.append(f"[{int(t0//60):02d}:{t0%60:05.2f}] " + " ".join(cur)); cur, t0 = [], None
    if cur: lines.append(f"[{int(t0//60):02d}:{t0%60:05.2f}] " + " ".join(cur))
    (P / "transcript.txt").write_text("\n".join(lines))
    print(f"project {P}\n  {cfg['width']}x{cfg['height']} {cfg['fps']} fps, {duration(src):.0f} s\n  {len(w)} words -> transcript.txt\n  {n} scenes -> scenes.json, {k} contact sheets -> sheets/")


# ---------------------------------------------------------------- per clip
def cdir(P, n):
    d = P["_dir"] / "clips" / f"clip{int(n):02d}"; d.mkdir(parents=True, exist_ok=True); return d


def py(script, *args, cwd):
    # the setup venv has numpy + pillow; fall back to the current interpreter
    run([str(VENV_PY) if VENV_PY.exists() else sys.executable, str(S / script), *map(str, args)], cwd=cwd)


def cmd_plan(a):
    P = project(a.project); d = cdir(P, a.clip)
    extra = []
    if a.teaser: extra += ["--teaser", *a.teaser]
    for s in a.seed or []: extra += ["--seed", s]
    py("autocrop.py", d, a.ranges, *extra, cwd=P["_dir"])


def cmd_words(a):
    P = project(a.project); d = cdir(P, a.clip); spec = json.load(open(d / "spec.json"))
    W = json.load(open(P["_dir"] / "words.json")); gl = P.get("glossary", {})
    out, off = [], 0.0
    for seg in spec["segments"]:
        L = seg["end"] - seg["start"]; s0 = seg.get("astart", seg["start"]); s1 = s0 + L
        for x in W:
            if s0 - 0.02 <= x["s"] < s1 and x["e"] <= s1 + 0.3:
                out.append({"text": gl.get(x["w"], gl.get(x["w"].strip(".,!?"), x["w"])) if gl else x["w"],
                            "start": round(x["s"] - s0 + off, 3), "end": round(min(x["e"], s1) - s0 + off, 3)})
        off += L
    for i, o in enumerate(out): o["id"] = f"w{i}"
    json.dump(out, open(d / "words_raw.json", "w"), ensure_ascii=False, indent=0)
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for seg in spec["segments"]:
        cmd += ["-ss", str(seg.get("astart", seg["start"])), "-t", str(seg["end"] - seg["start"]), "-i", P["src"]]
    n = len(spec["segments"])
    cmd += ["-filter_complex", "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1,aresample=16000,pan=mono|c0=0.5*c0+0.5*c1[a]",
            "-map", "[a]", "-c:a", "pcm_s16le", str(d / "audio16k.wav")]
    run(cmd)
    print(len(out), "words:", " ".join(f"[{i}]{o['text']}" for i, o in enumerate(out)))


def cmd_align(a):
    P = project(a.project)
    if not VENV_PY.exists(): sys.exit("run: l2s.py setup")
    run([str(VENV_PY), str(S / "force_align.py"), *[str(cdir(P, n)) for n in a.clips]], cwd=P["_dir"])


def cmd_cut(a):
    P = project(a.project); py("cropcut.py", cdir(P, a.clip) / "spec.json", cwd=P["_dir"])


def hf_dir(P, n):
    h = cdir(P, n) / "hf"
    if not (h / "hyperframes.json").exists():
        (h / "assets").mkdir(parents=True, exist_ok=True)
        json.dump({"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                   "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
                   "media": {"autoProxy": True}}, open(h / "hyperframes.json", "w"), indent=1)
        if not (ASSETS / "fonts" / "montserrat-var.ttf").exists(): sys.exit("fonts/sounds missing – run: l2s.py setup")
        json.dump({"id": f"clip{int(n):02d}", "name": f"clip{int(n):02d}"}, open(h / "meta.json", "w"))
        json.dump({"name": f"clip{int(n):02d}", "private": True, "type": "module"}, open(h / "package.json", "w"))
    if not (h / "assets" / "fonts").exists() or not (h / "assets" / "sfx").exists():
        shutil.copytree(ASSETS / "fonts", h / "assets" / "fonts", dirs_exist_ok=True)
        shutil.copytree(ASSETS / "sfx", h / "assets" / "sfx", dirs_exist_ok=True)
    return h


def cmd_build(a):
    P = project(a.project); d = cdir(P, a.clip); h = hf_dir(P, a.clip)
    cfgp = d / "hf_config.json"; cfg = json.load(open(cfgp))
    cfg.update({"project": str(h), "mode": "overlay", "words": str(d / "words_aligned.json")})
    cfg.setdefault("duration", round(duration(d / "base.mov") - 0.03, 2))
    json.dump(cfg, open(cfgp, "w"), ensure_ascii=False, indent=1)
    py("build_hf.py", cfgp, cwd=P["_dir"])


def cmd_render(a):
    P = project(a.project); d = cdir(P, a.clip)
    run(["npx", "-y", "hyperframes", "render", "--format", "mov", "--prores-profile", "4444", "--quiet",
         "-o", str(d / "overlay.mov")], cwd=hf_dir(P, a.clip), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("ok", d / "overlay.mov")


def cmd_compose(a):
    P = project(a.project); d = cdir(P, a.clip); Path(P["out"]).mkdir(parents=True, exist_ok=True)
    py("compose.py", d / "hf_config.json", d / "overlay.mov", Path(P["out"]) / f"{a.name}.mp4", cwd=P["_dir"])


def cmd_finish(a):
    for f in (cmd_cut, cmd_build, cmd_render, cmd_compose): f(a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--project", default=".")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("setup").add_argument("--no-model", action="store_true", help="skip the whisper.cpp model download")
    sp.add_parser("doctor")
    x = sp.add_parser("init"); x.add_argument("video"); x.add_argument("--lang", default="de"); x.add_argument("--out")
    x.add_argument("--whisper-model"); x.add_argument("--dir", dest="pdir", help="project folder (default: <video folder>/long2short)")
    x = sp.add_parser("plan"); x.add_argument("clip"); x.add_argument("ranges"); x.add_argument("--teaser", nargs=3); x.add_argument("--seed", action="append")
    for c in ("words", "cut", "build", "render"):
        sp.add_parser(c).add_argument("clip")
    x = sp.add_parser("align"); x.add_argument("clips", nargs="+")
    for c in ("compose", "finish"):
        x = sp.add_parser(c); x.add_argument("clip"); x.add_argument("name")
    a = ap.parse_args()
    {"setup": cmd_setup, "doctor": cmd_doctor, "init": cmd_init, "plan": cmd_plan, "words": cmd_words, "align": cmd_align,
     "cut": cmd_cut, "build": cmd_build, "render": cmd_render, "compose": cmd_compose, "finish": cmd_finish}[a.cmd](a)


if __name__ == "__main__":
    main()
