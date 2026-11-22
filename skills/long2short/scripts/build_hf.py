"""Build a HyperFrames project (index + captions + overlays) for one vertical clip.

usage: build_hf.py clip_config.json

clip_config:
  project   : path of the HyperFrames project dir (already `hyperframes init`-ed)
  video     : asset path inside the project (e.g. assets/clip01.mp4)
  duration  : seconds (ffprobe length of the video)
  words     : path to words_raw.json  [{id,text,start,end}]
  drop      : [word indices to remove]
  replace   : {index: "new text"}             (text fix, same timing)
  split     : {index: ["a","b"]}              (one timed word -> several, time split by length)
  merge     : [[i, j], ...]                   (words i..j -> one word, text joined without space)
  emphasis  : [lower-case word texts (punctuation stripped) to accent]
  hook      : {lines:[...], accent:[words], start, end}
  stickers  : [{text, start, end, emoji?}]
"""
import json, re, sys, os, html, subprocess

cfg = json.load(open(sys.argv[1]))
P = cfg["project"]
W, H = 1080, 1920
DUR = cfg["duration"]

# ---------- words ----------
words = json.load(open(cfg["words"]))
rep = {int(k): v for k, v in cfg.get("replace", {}).items()}
spl = {int(k): v for k, v in cfg.get("split", {}).items()}
mrg = {a: b for a, b in cfg.get("merge", [])}
drop = set(cfg.get("drop", []))
out = []
i = 0
while i < len(words):
    w = dict(words[i])
    if i in drop:
        i += 1; continue
    if i in mrg:
        j = mrg[i]
        w["text"] = "".join(x["text"] for x in words[i:j + 1]); w["end"] = words[j]["end"]
        out.append(w); i = j + 1; continue
    if i in rep:
        w["text"] = rep[i]
    if i in spl:
        parts = spl[i]; tot = sum(len(p) for p in parts); t = w["start"]; d = w["end"] - w["start"]
        for p in parts:
            e = t + d * len(p) / tot
            out.append({"text": p, "start": round(t, 3), "end": round(e, 3)}); t = e
        i += 1; continue
    out.append(w); i += 1
words = [w for w in out if w["text"].strip()]
# "phrases": whole-sentence captions (e.g. translations of foreign-language dialogue) replace the
# word captions inside their time window: [{"text": "...", "start": s, "end": e}, ...]
PHR = sorted(cfg.get("phrases", []), key=lambda p: p["start"])
words = [w for w in words if not any(p["start"] - 0.05 <= w["start"] < p["end"] for p in PHR)]
for k, w in enumerate(words):
    w["id"] = f"w{k}"
    w["end"] = min(w["end"], DUR - 0.05)

def bare(t): return re.sub(r"[^\wäöüß0-9,]", "", t.lower()).strip(",")
EMPH = set(e.lower() for e in cfg.get("emphasis", []))

# ---------- groups: 1-3 words, break on sentence end / pause / length ----------
MAXW, MAXC = 3, 16
groups, cur = [], []
for k, w in enumerate(words):
    if cur:
        prev = words[cur[-1]]
        gap = w["start"] - prev["end"]
        chars = sum(len(words[x]["text"]) + 1 for x in cur) + len(w["text"])
        if (len(cur) >= MAXW or chars > MAXC or gap >= 0.15
                or re.search(r"[.!?]$", prev["text"])
                or (re.search(r"[,:;]$", prev["text"]) and len(cur) >= 2)):
            groups.append(cur); cur = []
    cur.append(k)
if cur: groups.append(cur)
LEAD_GROUP = 0.12   # group appears slightly before its first word
LEAD_WORD = 0.04    # active-word highlight leads the sound a touch
G = []
for gi, g in enumerate(groups):
    s = max(words[g[0]]["start"] - LEAD_GROUP, 0.12, G[-1]["end"] if G else 0)
    nxt = words[groups[gi + 1][0]]["start"] - LEAD_GROUP if gi + 1 < len(groups) else DUR - 0.05
    e = min(words[g[-1]]["end"] + 0.45, nxt)
    e = max(e, words[g[-1]]["end"])
    G.append({"w": g, "start": round(s, 3), "end": round(min(e, DUR - 0.02), 3)})

# ---------- captions sub-composition ----------
cap_html = []
for gi, g in enumerate(G):
    spans = []
    # font size so the whole group fits in 840 px (Montserrat Black caps ~0.74 em/char + word padding)
    chars = sum(len(words[k]["text"]) for k in g["w"]) + 1.6 * (len(g["w"]) - 1)
    size = int(max(58, min(96, 840 / (chars * 0.74 + 0.3 * len(g["w"])))))
    for k in g["w"]:
        w = words[k]
        cls = "cw emph" if bare(w["text"]) in EMPH else "cw"
        spans.append(f'<span class="{cls}" id="cw{k}" style="font-size:{size}px"><span class="cw-bg"></span><span class="cw-t">{html.escape(w["text"].upper())}</span></span>')
    cap_html.append(f'    <div class="cg" id="cg{gi}">{" ".join(spans)}</div>')

for pi, ph in enumerate(PHR):
    toks = ph["text"].split()
    size = int(max(50, min(80, 860 * 2.6 / (max(len(ph["text"]), 1) * 0.72))))
    spans = [f'<span class="cw" style="font-size:{size}px"><span class="cw-t">{html.escape(t.upper())}</span></span>' for t in toks]
    cap_html.append(f'    <div class="cg" id="cp{pi}">{" ".join(spans)}</div>')
TIMING = {"groups": [{"id": f"cg{gi}", "start": g["start"], "end": g["end"], "words": g["w"]} for gi, g in enumerate(G)]
          + [{"id": f"cp{pi}", "start": round(max(0.12, ph["start"]), 3), "end": round(min(ph["end"], DUR - 0.02), 3), "words": []} for pi, ph in enumerate(PHR)],
          "words": [{"start": w["start"], "end": w["end"]} for w in words]}

captions = f"""<template>
  <style>
    @font-face {{ font-family: "Montserrat Local"; src: url("assets/fonts/montserrat-var.ttf") format("truetype"); font-weight: 100 900; font-style: normal; font-display: block; }}
    #root {{ position: absolute; inset: 0; pointer-events: none; }}
    .cg {{
      position: absolute; left: 0; width: 100%; top: 1280px; height: 640px; align-content: center;
      display: flex; flex-wrap: wrap; justify-content: center; align-items: center;
      gap: 10px 26px; padding: 0 110px; opacity: 0; visibility: hidden; overflow: visible;
    }}
    .cw {{
      position: relative; display: inline-block; padding: 4px 14px 8px;
      font-family: "Montserrat Local", "Montserrat", sans-serif; font-weight: 900; font-size: 96px;
      line-height: 1.02; letter-spacing: 0.01em; color: #fff;
      transform-origin: 50% 60%;
    }}
    .cw-t {{
      position: relative; z-index: 1;
      text-shadow: 6.5px 0.0px 0 #000, 6.0px 2.5px 0 #000, 4.6px 4.6px 0 #000, 2.5px 6.0px 0 #000, 0.0px 6.5px 0 #000, -2.5px 6.0px 0 #000, -4.6px 4.6px 0 #000, -6.0px 2.5px 0 #000, -6.5px 0.0px 0 #000, -6.0px -2.5px 0 #000, -4.6px -4.6px 0 #000, -2.5px -6.0px 0 #000, -0.0px -6.5px 0 #000, 2.5px -6.0px 0 #000, 4.6px -4.6px 0 #000, 6.0px -2.5px 0 #000, 0 8px 22px rgba(0,0,0,.6);
    }}
    .cw-bg {{
      position: absolute; inset: 2px 0 0 0; border-radius: 16px; z-index: 0;
      background: #FFD400; opacity: 0; transform: scale(.6);
      box-shadow: 0 10px 28px rgba(0,0,0,.35);
    }}
  </style>
  <div id="root" data-composition-id="captions" data-width="{W}" data-height="{H}" data-layout-allow-overflow>
{chr(10).join(cap_html)}
  </div>
  <script>
    (function () {{
      const D = {json.dumps(TIMING)};
      const tl = gsap.timeline({{ paused: true }});
      const ACC = "#FFD400";
      const LEADW = {LEAD_WORD};
      D.groups.forEach(function (g) {{
        const el = document.getElementById(g.id);
        tl.set(el, {{ visibility: "visible" }}, g.start);
        tl.fromTo(el, {{ opacity: 0, y: 26, scale: 0.92 }}, {{ opacity: 1, y: 0, scale: 1, duration: 0.16, ease: "back.out(2.2)" }}, g.start);
        g.words.forEach(function (k) {{
          const w0 = D.words[k];
          const w = {{ start: Math.max(g.start, w0.start - LEADW), end: w0.end }};
          const we = document.getElementById("cw" + k);
          const t = we.querySelector(".cw-t");
          const emph = we.classList.contains("emph");
          if (emph) {{
            const bg = we.querySelector(".cw-bg");
            tl.fromTo(bg, {{ opacity: 0, scale: 0.6 }}, {{ opacity: 1, scale: 1, duration: 0.14, ease: "back.out(2.5)" }}, w.start);
            tl.fromTo(t, {{ color: "#ffffff" }}, {{ color: "#000000", duration: 0.06 }}, w.start);
            tl.set(t, {{ textShadow: "none" }}, w.start);
            tl.fromTo(we, {{ scale: 1 }}, {{ scale: 1.08, duration: 0.14, ease: "back.out(3)" }}, w.start);
          }} else {{
            tl.fromTo(t, {{ color: "#ffffff" }}, {{ color: ACC, duration: 0.05 }}, w.start);
            tl.fromTo(we, {{ scale: 1 }}, {{ scale: 1.1, duration: 0.12, ease: "back.out(3)" }}, w.start);
            tl.to(we, {{ scale: 1, duration: 0.12, ease: "power2.out" }}, Math.max(w.end, w.start + 0.12));
            tl.to(t, {{ color: "#ffffff", duration: 0.08 }}, Math.max(w.end, w.start + 0.12));
          }}
        }});
        tl.to(el, {{ opacity: 0, duration: 0.1, ease: "power2.in" }}, g.end - 0.1);
        tl.set(el, {{ opacity: 0, visibility: "hidden" }}, g.end);
      }});
      window.__timelines["captions"] = tl;
    }})();
  </script>
</template>
"""

# ---------- overlays (hook + stickers) ----------
hook = cfg.get("hook")
stickers = cfg.get("stickers", [])
ov_html, ov_js = [], []
if hook:
    acc = set(a.lower() for a in hook.get("accent", []))
    lines = []
    for li, line in enumerate(hook["lines"]):
        toks = []
        for tk in line.split(" "):
            c = "hk-acc" if re.sub(r"[^\wäöü]", "", tk.lower()) in acc else ""
            toks.append(f'<span class="{c}">{html.escape(tk)}</span>')
        # width budget 860 px incl. 34 px padding each side; Montserrat Black caps ~0.74 em/char, emoji ~1.1 em
        n_emoji = sum(1 for ch in line if ord(ch) > 0x2600); n_txt = len(line) - n_emoji
        hs = int(max(48, min(86, (860 - 68) / (n_txt * 0.74 + n_emoji * 1.1))))
        lines.append(f'<div class="hk-line" id="hk-l{li}" style="font-size:{hs}px">{" ".join(toks)}</div>')
    ov_html.append(f'    <div class="hk" id="hook">{"".join(lines)}</div>')
    ov_js.append(f"""
      tl.set("#hook", {{ visibility: "visible" }}, {hook['start']});
      tl.fromTo("#hook", {{ opacity: 0, scale: 0.8, rotation: -3 }}, {{ opacity: 1, scale: 1, rotation: -2, duration: 0.28, ease: "back.out(2)" }}, {hook['start']});
      tl.fromTo("#hook .hk-line", {{ y: 30, opacity: 0 }}, {{ y: 0, opacity: 1, duration: 0.22, stagger: 0.12, ease: "power3.out" }}, {hook['start'] + 0.05});
      tl.fromTo("#hook", {{ scale: 1 }}, {{ scale: 1.04, duration: 0.6, yoyo: true, repeat: 3, ease: "sine.inOut" }}, {hook['start'] + 0.4});
      tl.to("#hook", {{ opacity: 0, scale: 0.9, duration: 0.2, ease: "power2.in" }}, {hook['end'] - 0.2});
      tl.set("#hook", {{ visibility: "hidden" }}, {hook['end']});""")
for si, s in enumerate(stickers):
    # width budget: 860 px for emoji (~1.0x its size) + gap + pill (60 px padding); shrink text and emoji together
    ss = int(max(40, min(64, (860 - 18 - 60) / (len(s["text"]) * 0.74 + (1.9 if s.get("emoji") else 0)))))
    ov_html.append(f'    <div class="st" id="st{si}"><span class="st-e" style="font-size:{int(ss * 1.85)}px">{html.escape(s.get("emoji",""))}</span><span class="st-t" style="font-size:{ss}px">{html.escape(s["text"])}</span></div>')
    ov_js.append(f"""
      tl.set("#st{si}", {{ visibility: "visible" }}, {s['start']});
      tl.fromTo("#st{si}", {{ opacity: 0, scale: 0.5, rotation: 6 }}, {{ opacity: 1, scale: 1, rotation: 2, duration: 0.3, ease: "back.out(2.4)" }}, {s['start']});
      tl.fromTo("#st{si} .st-e", {{ rotation: -15 }}, {{ rotation: 12, duration: 0.35, yoyo: true, repeat: 3, ease: "sine.inOut" }}, {s['start'] + 0.3});
      tl.to("#st{si}", {{ opacity: 0, scale: 0.8, duration: 0.18, ease: "power2.in" }}, {s['end'] - 0.18});
      tl.set("#st{si}", {{ visibility: "hidden" }}, {s['end']});""")

overlays = f"""<template>
  <style>
    @font-face {{ font-family: "Montserrat Local"; src: url("assets/fonts/montserrat-var.ttf") format("truetype"); font-weight: 100 900; font-style: normal; font-display: block; }}
    #root {{ position: absolute; inset: 0; pointer-events: none; }}
    .hk {{
      position: absolute; left: 0; width: 100%; top: 250px;
      display: flex; flex-direction: column; align-items: center; gap: 10px;
      opacity: 0; visibility: hidden;
    }}
    .hk-line {{
      background: #000; color: #fff; border-radius: 22px; padding: 14px 34px 18px;
      font-family: "Montserrat Local", "Montserrat", sans-serif; font-weight: 900; font-size: 86px; line-height: 1;
      letter-spacing: -0.01em; text-transform: uppercase; white-space: nowrap; box-shadow: 0 16px 40px rgba(0,0,0,.45);
    }}
    .hk-acc {{ color: #FFD400; }}
    .st {{
      position: absolute; left: 0; width: 100%; top: 300px;
      display: flex; justify-content: center; align-items: center; gap: 18px;
      opacity: 0; visibility: hidden;
    }}
    .st-t, .st-e {{ display: inline-block; }}
    .st-t {{
      background: #FFD400; color: #000; border-radius: 20px; padding: 14px 30px 18px;
      font-family: "Montserrat Local", "Montserrat", sans-serif; font-weight: 900; font-size: 64px; line-height: 1;
      text-transform: uppercase; white-space: nowrap; box-shadow: 0 14px 36px rgba(0,0,0,.4);
    }}
    .st-e {{ font-size: 120px; line-height: 1; }}
  </style>
  <div id="root" data-composition-id="overlays" data-width="{W}" data-height="{H}" data-layout-allow-overflow>
{chr(10).join(ov_html)}
  </div>
  <script>
    (function () {{
      const tl = gsap.timeline({{ paused: true }});{''.join(ov_js)}
      window.__timelines["overlays"] = tl;
    }})();
  </script>
</template>
"""

# ---------- sound effects (root-level <audio>, one per cue) ----------
def _dur(f):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f"{P}/{f}"]).decode())
sfx_tags = []
for i, c in enumerate([] if cfg.get("mode") == "overlay" else cfg.get("sfx", [])):
    f = c.get("file") or f"assets/sfx/{c['sound']}.mp3"
    st = max(0.0, round(c.get("start", c.get("at", 0)), 3)); d = min(_dur(f), DUR - st - 0.02)
    if d <= 0.05: continue
    sfx_tags.append(f'      <audio id="sfx{i}" class="clip" src="{f}" data-start="{st}" data-duration="{d:.3f}" data-track-index="{10 + i}" data-volume="{c.get("volume", 0.35)}" data-fade-out="0.08"></audio>')
SFX_TAGS = "\n".join(sfx_tags)

OVERLAY = cfg.get("mode") == "overlay"   # graphics only on transparent canvas; video + SFX are composited by compose.py
BG = "transparent" if OVERLAY else "#000"
VIDEO_TAG = "" if OVERLAY else f'''      <video id="footage" class="clip" src="{cfg['video']}" data-start="0" data-duration="{DUR}" data-track-index="0" data-has-audio="true" data-volume="1" playsinline></video>'''
if OVERLAY: SFX_TAGS = ""

index = f"""<!doctype html>
<html lang="de">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: {BG}; }}
      #root {{ position: relative; width: 100%; height: 100%; }}
      #footage {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; object-fit: cover; z-index: 1; }}
      #captions {{ z-index: 3; }}
      #overlays {{ z-index: 4; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="{W}" data-height="{H}">
{VIDEO_TAG}
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html"
           data-start="0" data-duration="{DUR}" data-track-index="1" data-track-kind="captions" data-width="{W}" data-height="{H}"></div>
{SFX_TAGS}
      <div id="overlays" data-composition-id="overlays" data-composition-src="compositions/overlays.html"
           data-start="0" data-duration="{DUR}" data-track-index="2" data-track-kind="graphics" data-width="{W}" data-height="{H}"></div>
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""
os.makedirs(f"{P}/compositions", exist_ok=True)
open(f"{P}/index.html", "w").write(index)
open(f"{P}/compositions/captions.html", "w").write(captions)
open(f"{P}/compositions/overlays.html", "w").write(overlays)
json.dump({"words": words, "groups": G}, open(f"{P}/caption_data.json", "w"), ensure_ascii=False, indent=1)
print(f"{len(words)} Wörter, {len(G)} Gruppen")
for g in G[:12]:
    print(g["start"], g["end"], " ".join(words[k]["text"] for k in g["w"]))
