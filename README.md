# long2short ✂️📱

A Claude Code plugin/skill that turns a long landscape video into **ready-to-post vertical clips**
for TikTok, Instagram Reels and YouTube Shorts – locally on your Mac.

- 🧠 **Claude picks the moments** – from the transcript *and* from contact sheets, so strong
  visual moments without speech are found too. Every clip is self-contained, with a hook that
  gives a first-time viewer the context.
- 🎯 **9:16 reframing with tracking** – Apple Vision follows faces and people; drones, robots or
  cars can be tracked from a single seed point. Pans stay smooth, cuts stay clean.
- 💬 **Word-synced captions** – text from Whisper, timing from forced alignment (on the syllable),
  rendered with HyperFrames: bold, centred in the lower third, active word highlighted.
- 🪧 **Hook title + info stickers**, 🔊 **subtle CC0 sound effects**, −14 LUFS.
- ⚡ ~3 min of compute per 70-s clip on an M2 (ProRes via VideoToolbox, graphics rendered as a
  transparent layer, a single final encode).

## Requirements
macOS (Apple Silicon recommended) · Claude Code · Python 3.10+ · `brew install ffmpeg node whisper-cpp`
· a whisper.cpp model (e.g. `ggml-medium-q5_0.bin` in `~/models/whisper/`) · Xcode command line tools
(`xcode-select --install`).

## Install
**As a plugin (recommended):**
```
/plugin marketplace add sebsch1337/long2short
/plugin install long2short@long2short
```
**Or as a personal skill:** clone the repo and link the skill folder:
```bash
git clone https://github.com/sebsch1337/long2short.git
ln -s "$PWD/long2short/skills/long2short" ~/.claude/skills/long2short
```
### First-time setup
Start Claude Code and say **"set up long2short"** – Claude runs the skill's `l2s.py setup` and
`l2s.py doctor` from wherever the skill is installed (plugins live under `~/.claude/plugins/…`,
not in `~/.claude/skills`). With the personal-skill install you can also run it yourself:
```bash
python3 ~/.claude/skills/long2short/scripts/l2s.py setup
```
The repo ships **only instructions and code**. `setup` downloads everything else into
`~/.cache/long2short` (nothing global is touched): a private Python venv with torch/torchaudio
for forced alignment, four CC0 sound effects from Freesound, the Montserrat font (OFL) from
Google Fonts, a whisper.cpp model if you have none, and it compiles the Apple Vision helpers.
Check with `l2s.py doctor`.

## Use
In Claude Code, in the folder with your video:
> make TikTok clips from video.mp4 – the most clickable moments, 60–90 s, with captions

Claude picks up the skill from the request by itself. To call it explicitly, use the slash command:
`/long2short` (personal skill) or `/long2short:long2short` (plugin – plugin skills are prefixed
with the plugin name).

Claude runs `l2s.py init`, proposes a shortlist, and builds each clip
(`plan → words → align → finish`). Results land in `clips/` next to your video.

Manual CLI: `python3 <skill folder>/scripts/l2s.py --help`

## Licenses
Code MIT. Downloaded at setup (not part of this repo): Montserrat (SIL OFL 1.1), sound effects (CC0,
credits written to `~/.cache/long2short/assets/sfx/CREDITS.md`).
Only clip videos you own or have permission to use.
