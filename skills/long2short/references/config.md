# clips/clipNN/hf_config.json

Written by you after `align`; `l2s.py build` fills in `project`, `mode`, `words` and `duration`.

```json
{
  "drop": [5, 181, 182],
  "replace": {"21": "Airbnb,"},
  "split": {"87": ["over", "there"]},
  "merge": [[107, 108]],
  "emphasis": ["tiny", "house", "nobody", "20000", "euro", "crazy"],
  "hook": {"lines": ["Tiny house in Norway", "for 20 000 € 🤯"], "accent": ["norway", "20", "000"],
           "start": 0.0, "end": 3.1},
  "stickers": [
    {"text": "12 m² = 20 000 €", "emoji": "💸", "start": 16.1, "end": 19.2},
    {"text": "Built in 3 weeks", "emoji": "🔨", "start": 38.0, "end": 40.8}
  ],
  "sfx": [
    {"sound": "pop", "at": 0.0, "volume": 0.45},
    {"sound": "whoosh", "at": 3.15, "volume": 0.4},
    {"sound": "kaching", "at": 16.2, "volume": 0.4},
    {"sound": "impact", "at": 36.9, "volume": 0.22}
  ]
}
```

- `drop / replace / split / merge` index into `words_aligned.json` (the numbers `l2s.py words`
  printed). Prefer fixing text in `words_raw.json` **before** `align` – then timing matches the
  corrected words. Use `drop` for unintelligible passages and for words that leak in from before
  the segment start.
- All times are clip times in seconds (0 = first frame of the clip). Get them from
  `words_aligned.json` (`start` of the word) – e.g. sticker 0.1 s before the word, sound `at` the word.
- Sounds available: `pop`, `whoosh`, `impact`, `kaching` (CC0, downloaded by `setup` to
  `~/.cache/long2short/assets/sfx`, copied into each clip's `hf/assets/sfx`). To add one, put an
  `.mp3` into the clip's `hf/assets/sfx/` or add it to `SOUNDS` in `l2s.py` (download at setup).
- Hook and sticker text sizes adapt to the frame width automatically.
- `phrases` – whole-sentence captions without word highlighting, e.g. a translation of
  foreign-language dialogue: `[{"text": "Wie heißt du?", "start": 46.6, "end": 49.9}]`. Word
  captions inside a phrase window are dropped automatically. Take the timing from the speech
  (the transcript usually contains the foreign words with times).
- `cover` – time ranges where the source has **burned-in subtitles**; a blurred band hides them so
  they don't clash with our captions: `[[10.0, 44.3]]`. Band position: `cover_band` (default
  `[1660, 1880]` px in the 1080×1920 output).

# clips/clipNN/spec.json (written by `plan`, edit only to fix a crop)

```json
{"segments": [{"start": 50.5, "end": 131.0, "astart": 50.5,
               "keys": [[50.5, 0.42, 0.40], [52.0, 0.48, 0.41]],
               "cuts": [57.06, 67.2], "bounds": [56.42, 57.06, 67.2]}]}
```
`keys` = [source time, crop centre x (0–1), subject y]; `cuts` = boundaries where the crop may
jump. To override a stretch, edit its keys and run `l2s.py cut NN` again.
