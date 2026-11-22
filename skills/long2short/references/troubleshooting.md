# Root causes already found (and how the scripts handle them)

| Symptom | Root cause | Handling |
|---|---|---|
| Captions lag the voice by 0.3–1 s | Whisper word timestamps (esp. whisper.cpp) drift | Text from Whisper, **timing from forced alignment** (torchaudio MMS_FA). Never caption from raw Whisper times. |
| A few frames of the neighbouring shot at a clip/segment start or end | Segment edges came from word times, not shot changes | `cut` trims the picture to a scene change ≤ 0.6 s inside the edge and holds the first/last frame of the wanted shot; audio untouched. |
| Crop drifts into the old shot just before a cut | Smoothing ran across a real cut | Every cut-like boundary (phase correlation < 0.10) is a barrier: no smoothing across it. |
| Crop jumps back and forth on a camera pan / "false cut" | Scene detector reports pans as cuts | Phase-correlation test; pans keep a continuous crop path. |
| Picture "wobbles like under water" | Crop chased intermittent detections at the frame edge while the camera itself swung; wide-angle edge distortion | Crop holds still while the source camera moves fast; targets near the edge ignored; target must persist ~1 s; window stays inside 25–75 % of the width. |
| Small object (drone) not followed | Face/body detection can't see it; generic saliency picks masts/roofs | `plan --seed T:CX:CY` → snaps to the local-contrast blob and tracks it with Apple Vision. Read positions from the grid on the review sheet (misread positions = lost track). |
| Sticker text runs off the frame | Fixed font size | Hook/sticker font size computed from text length (max 860 px). |
| "Squashed" picture | Zoom punch-out | Zoom removed (do not reintroduce). |
| Green blur background | boxblur on hardware-decoded pixel format | Letterbox layout removed altogether. |
| Render ignores the font | Web font still loading | Font shipped as a local file with `@font-face`, `font-display: block`. |
| `numpy`/`whisper` broken after installing packages | A pip install upgraded global NumPy | Install extras only into the long2short venv (`l2s.py setup`), never globally. |

## Useful checks (only when something is reported wrong)
- Frame at a time: `ffmpeg -ss T -i out.mp4 -frames:v 1 -vf scale=270:-2 f.jpg`
- Crop path around a time: `clips/clipNN/crop<i>.cmd` (per-frame x of segment i, times relative to its start)
- Loudness: `ffmpeg -i out.mp4 -af loudnorm=print_format=summary -f null -`
