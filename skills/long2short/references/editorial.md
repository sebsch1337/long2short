# Picking moments, hooks and stickers

## What makes a clip work
Short-form viewers decide in about one second whether to stay, and watch muted more often than not.
A good clip has:
- **Hook** – the first 1–3 s promise something: a surprising claim, a visual payoff, a question.
  A cold open (`--teaser`: the 2–3 s payoff shot first) works well when the best image comes late.
- **Self-contained story** – setup → development → payoff inside the clip. No "as I said",
  "after this ride", "the second one" – start after such phrases or cut them.
- **Context for a first-time viewer** – the hook text and/or first sentence say *where* and *what*
  ("Night market in Bangkok", "In Lisbon …"). Never assume the viewer saw another clip or the long video.
- **Payoff before the swipe** – end on the punchline / reaction / result, not on a trailing
  sentence. 60–90 s by default (TikTok Creator Rewards needs > 60 s); shorter only on request.

## Finding candidates
1. Read the full `transcript.txt` (time codes per sentence). Mark claims, surprises, numbers,
   strong opinions (comments!), humour, reactions ("wow", laughter), price reveals.
2. Look at every contact sheet in `sheets/`. Mark shots that are strong **without speech**:
   machines doing things, drones, crowds, reveals. Check the transcript around them.
3. Combine: a clip can splice two ranges of the same topic (keep the order logical).
4. Rank by expected watch-through: visual novelty × emotion × clarity. Typical yield: one clip
   per 1.5–2 minutes of strong material.

Before cutting, check boundaries in `words.json`: start on the first word of a sentence, end on
the last word of the payoff. Leave out greetings and transitions to the next location.

## Foreign-language dialogue and burned-in subtitles
Look for subtitles already burned into the source (contact sheets show them at the bottom). If the
original translates a dialogue, reuse that translation as `phrases` (timed to the speech) and
`cover` the burned-in band – otherwise viewers see two competing subtitle lines, and the
original ones are usually cut off by the 9:16 crop anyway.

## Hook text (top, first ~3 s)
- 2 short lines, max ~22 characters each, uppercase in the render. Line 1 = topic/place,
  line 2 = the twist. Accent 1–2 words in yellow. One emoji at most.
- Must establish context on its own: "TINY HOUSE IN NORWAY" / "FOR 20 000 € 🤯",
  "STREET FOOD IN BANGKOK" / "1 € PER PLATE".
- Write in the video's language.

## Info stickers (top, ~3 s each)
- 2–3 per clip, at the moment the fact is said or shown: prices ("3 KM = 2 €"), names
  ("OLD TOWN MARKET"), numbers ("OPEN 24/7"). Short – they auto-shrink, but
  ≤ 24 characters reads best. One emoji in front.
- Don't cover the hook; leave ≥ 3 s between stickers.

## Emphasis words (yellow pill in captions)
8–15 per clip: names, numbers, prices, the emotional words ("crazy", "nobody"). Not
filler words. Matching is case-insensitive on the word without punctuation.

## Sound cues
5–7 per clip, placed with `"at"` = the moment it should hit:
- `pop` (0.45) hook appears at 0.0; (0.4) each sticker
- `whoosh` (0.4) on the teaser→story cut and on segment joins; on "it drives off" moments
- `kaching` (0.4) on a price
- `impact` (0.22) on the punchline / a strong statement
Less is more – never two cues within 1 s.

## Posting caption (deliver with each clip)
One or two sentences in the video's language with the hook idea + a question to drive comments,
then 4–6 hashtags (topic, place, #fyp-style tag).
