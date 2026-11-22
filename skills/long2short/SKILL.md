---
name: long2short
description: Turn a long landscape video (vlog, travel video, interview, podcast, talk) into ready-to-post vertical 9:16 short-form clips for TikTok, Instagram Reels and YouTube Shorts – picks the strongest moments (including visual moments without speech), reframes them around the subject with Apple Vision tracking, adds word-synced animated captions, a hook title, info stickers and sound effects, and renders 1080x1920 MP4s. Use this skill whenever the user wants clips, shorts, reels, TikToks, highlights, "the best moments", monetizable short videos, Hochformat/Kurzvideos or vertical crops from a video file, or asks to caption or reframe footage for social media – even if they don't name the skill.
---

# long2short

You are the editor: you pick the moments, write hooks and stickers, and judge the crop. The
scripts do the heavy lifting (transcription, scene detection, tracking, cutting, rendering) and
run locally. Everything goes through one CLI:

```
python3 <skill>/scripts/l2s.py [-p PROJECT] <command> ...
```

`<skill>` is this skill's folder. A *project* folder (default `<video folder>/long2short`) holds
`project.json`, the proxy, transcript, scene list and one folder per clip (`clips/clipNN/`).
Finished clips go to `project.json → out` (default `<video folder>/clips`).

Requirements: macOS (Apple Vision for tracking, VideoToolbox for fast ProRes), ffmpeg, Node (npx
HyperFrames), Xcode command line tools (swiftc), whisper-cli + a ggml model (or python whisper).
Caption timing (forced alignment) works for Latin-script languages; numbers are spelled out for German in `force_align.py` – extend `spell()` for other languages.
Nothing is bundled with this skill except instructions and code. First time on a machine run
`l2s.py setup` – it downloads everything else into `~/.cache/long2short`: a private Python
env (torch/torchaudio for forced alignment), the CC0 sound effects, the caption font (Montserrat,
OFL) and, if none is installed, a whisper.cpp model; it also compiles the Apple Vision helpers.
Then `l2s.py doctor`. Run `setup` again whenever `doctor` reports something missing. If something is missing, show the user the exact install command.

## 1. Prepare the video (once per video)

```
l2s.py init "/path/video.mp4" --lang de
```
Creates proxy, 16 kHz audio, word transcript (`transcript.txt` with time codes), `scenes.json`
and contact sheets (`sheets/`, one frame per scene with time codes). Long videos take minutes –
run it in the background and tell the user.

Add recurring transcription errors (names, brands) to `project.json → glossary`
(`{"Air bee and bee": "Airbnb"}`); they are fixed automatically when words are mapped onto a clip.

## 2. Pick the moments (your judgment)

Read `references/editorial.md` before choosing. In short: read the whole `transcript.txt`, look
at every contact sheet (that is how you find strong moments **without speech** – a machine at
work, an animal, a big reveal), then write a shortlist for the user: number, working title / hook, source
ranges, length, why it works. Default length 60–90 s (TikTok's Creator Rewards only pays for
videos over one minute) unless the user wants something else. Wait for the user's go before
rendering a batch when they asked to review picks; otherwise continue.

**Every clip must stand alone.** A viewer sees this person and topic for the first time: the
first 3 seconds (hook text + opening line) must say where we are and what this is about
(e.g. "In Lisbon …"), and the clip must not lean on other parts of the video ("after this trip",
"as I said", "the second one"). Start after such phrases or drop them.

## 3. Build each clip

```
l2s.py -p P plan  NN "A-B[,C-D]" [--teaser VS VE AS] [--seed T:CX:CY]
l2s.py -p P words NN                # prints the words with indices – fix text in words_raw.json
l2s.py -p P align NN [MM ...]       # forced alignment: exact word timing (model loads once for all clips)
#   write clips/clipNN/hf_config.json  (see references/config.md)
l2s.py -p P finish NN "NN_short-title"   # cut -> graphics -> render -> compose
```

- **Ranges** are absolute source seconds. Cut at sentence boundaries; use the word times in
  `words.json`. Segments are joined in order; a `--teaser` (2–3 s payoff shot shown first, with
  audio from `AS`) makes a strong cold open.
- **Crop review costs tokens – only look when told to.** `plan` prints `no anomalies` or
  a list of ANOMALIES. Only then open `clips/clipNN/spec.review.jpg` (yellow box = 9:16 window,
  red dot = tracked subject, cyan grid in 0.1 steps).
- **Objects** (drone, robot, car) are not found automatically: for a stretch reported as
  "no person", read the object's position from the grid and re-run `plan` with
  `--seed T:CX:CY` (source time, x, y in 0–1). It snaps to the object and tracks it.
- **Text fixes before alignment.** Correct mis-heard words in `words_raw.json`; if a passage is
  unintelligible, drop it from captions (`drop` in hf_config) rather than guessing.
- Run `align` once for several clips to save time.

## 4. Deliver

Report a short table: clip, length, file path, hook, and a ready-to-post caption with hashtags.
Don't re-check renders frame by frame when the user said they will review themselves.
Intermediate files are large (~2 GB per clip in `clips/clipNN/`); offer to delete them after the
user approved the results.

## Fixed style (approved – do not change without being asked)

- Captions: Montserrat Black, uppercase, white with black outline, 1–3 words, active word yellow
  `#FFD400` with a short pop, key words on a yellow pill; **centred horizontally and vertically in
  the lower third**; appear 0.12 s before the word.
- Hook: black pills at the top, accent words yellow, first ~3 s. Info stickers: yellow pill +
  emoji at the top, auto-sized to the frame width.
- Sound: 5–7 subtle effects per clip (pop, whoosh, impact, ka-ching; CC0, downloaded by setup), no music
  (music is added in the app). Loudness −14 LUFS, true peak −1 dBTP.
- Crop: one 9:16 window, smooth tracking. **No zoom punch-ins and no letterboxed/blurred
  "fit" layout** – both were tried and rejected (zoom-out looked like squashing).

When something looks wrong, read `references/troubleshooting.md` – it lists the root causes
already found (scene-edge leaks, wobble, caption lag, …) and how the scripts handle them.
