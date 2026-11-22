"""Forced alignment of a known word list to audio (torchaudio MMS_FA, CTC).

usage: .venv/bin/python force_align.py clips/clipNN [clips/clipMM ...]
       (per clip: audio16k.wav + words_raw.json -> words_aligned.json; the model loads once for all clips)
words_in: [{id,text,start,end}]  (timings only used as fallback for unalignable tokens)
"""
import json, re, sys
import torch, torchaudio
from torchaudio.pipelines import MMS_FA as bundle

ONES = ["null", "ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf",
        "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn"]
TENS = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig", "neunzig"]

def de_int(n):
    """German number words (0..999999) – spoken form for aligning digits in the transcript"""
    if n < 20: return "eins" if n == 1 else ONES[n]
    if n < 100: return (ONES[n % 10] + "und" if n % 10 else "") + TENS[n // 10]
    if n < 1000: return ONES[n // 100] + "hundert" + (de_int(n % 100) if n % 100 else "")
    return de_int(n // 1000).replace("eins", "ein") + "tausend" + (de_int(n % 1000) if n % 1000 else "")

def spell(t):
    """'17' -> siebzehn, '3,33' -> drei komma dreiunddreißig ; other languages: extend here"""
    m = re.fullmatch(r"(\d+)(?:[,.](\d+))?", t.replace(".", "") if re.fullmatch(r"\d{1,3}(\.\d{3})+", t) else t)
    if not m or int(m.group(1)) > 999999: return None
    out = de_int(int(m.group(1)))
    if m.group(2): out += "komma" + de_int(int(m.group(2)))
    return out

def norm(t):
    t = t.lower().strip(".,!?:;\"'()…–-")
    sp = spell(t)
    if sp: t = sp
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = re.sub(r"[^a-z']", "", t)
    return t

import wave, numpy as np
model = bundle.get_model(with_star=False)
tokenizer, aligner = bundle.get_tokenizer(), bundle.get_aligner()

def align(wavpath, inpath, outpath):
    _w = wave.open(wavpath); sr = _w.getframerate()
    wav = torch.from_numpy(np.frombuffer(_w.readframes(_w.getnframes()), dtype=np.int16).astype(np.float32) / 32768).unsqueeze(0)
    assert sr == bundle.sample_rate, sr
    words = json.load(open(inpath))
    toks = [norm(w["text"]) for w in words]
    keep = [i for i, t in enumerate(toks) if t]
    with torch.inference_mode():
        emission, _ = model(wav)
    spans = aligner(emission[0], tokenizer([toks[i] for i in keep]))
    ratio = wav.size(1) / emission.size(1) / sr
    out = [dict(w) for w in words]
    for i, sp in zip(keep, spans):
        out[i]["start"] = round(sp[0].start * ratio, 3)
        out[i]["end"] = round(sp[-1].end * ratio, 3)
        out[i]["score"] = round(sum(s.score * len(s) for s in sp) / sum(len(s) for s in sp), 3)
    json.dump(out, open(outpath, "w"), ensure_ascii=False, indent=0)
    print(f"{outpath}: aligned {len(keep)}/{len(words)}")

for d in sys.argv[1:]:
    align(f"{d}/audio16k.wav", f"{d}/words_raw.json", f"{d}/words_aligned.json")
