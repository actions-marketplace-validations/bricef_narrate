# Writing a narrate script that works

How to plan, write and adapt a script so the video is clear when heard once, at speaking pace,
next to a picture. Read this when writing from a brief or turning existing material into a video.

## Plan before writing

Write a scene plan first, as a list, then the script. For each scene:
- its job (one idea);
- what's on screen;
- roughly how many words.

The plan keeps the video to length and makes gaps visible: a scene with nothing to show, or a
picture with nothing to say about it.

**Budget words, not scenes.** narrate speaks about 150 words a minute, plus about half a second
between paragraphs.

| Target | Narration |
| --- | --- |
| 30 s | 60–70 words |
| 60 s | 130–150 words |
| 90 s | 200–230 words |
| 3 min | 400–450 words |

Then confirm with `narrate check script.md --timing --tts kokoro`, which gives the real estimate
per scene.

**A shape that works for most short videos:**
1. **Hook (1 scene):** what this is and why the viewer should care, in one or two sentences.
2. **Body (3–7 scenes):** one point each, in an order that builds; each scene's picture shows
   what its words say.
3. **Close (1 scene):** the takeaway, or what to do next (a URL, a command, a call to action).

Scenes of 5–15 seconds keep the picture changing. Split a longer scene into two over related
pictures, or put two or three pictures in one scene: they take turns, sharing its time.

## Write for the ear

- **Short sentences**, one idea each. A listener can't re-read.
- **Spoken style:** contractions, plain words, active voice. Read it aloud in your head; if you'd
  run out of breath, split it.
- **One or two sentences per paragraph.** Each paragraph is one subtitle, and a pause follows it.
- **Say what the picture can't**, and don't describe what the viewer can already see ("as you can
  see in this diagram…"). Point instead: "The request goes through three services."
- **Numbers as people say them:** "about three thousand", not "2,947"; "twenty twenty-six" is
  read fine from "2026"; percentages and units are read correctly.
- **Lists:** two or three items read well. A longer list belongs on a slide, with narration that
  sums it up.
- **Code, commands, URLs:** show them on a slide or in the picture, and say what they do. Read
  only short ones: "run narrate build" is fine; a 60-character command isn't.
- **Pronunciation:**
  - Write names and acronyms plainly first; most are read right.
  - After the Kokoro draft, `narrate hear script.mp4 --script script.md` lists the words that came
    out wrong.
  - Fix only those, inside `<speak>`, with a respelling: `<sub alias="quiet tube">quietube</sub>`, or
    spaced capitals for an acronym said letter by letter (`<sub alias="Y T D L P">yt-dlp</sub>`).
    The subtitles keep the written word, where `[…]{ipa}` would show the phonetic symbols instead.
    `<phoneme>` with IPA is a last resort; voices follow it unevenly. Hear it again after each fix.
- **Markdown in narration:** `*emphasis*` changes the delivery and is never shown. Other
  formatting (links, headings, lists) doesn't belong in narration: put it on a slide.
- **Pauses** let something land: `(pause: 1)` after a reveal, or at the end of a scene to hold the
  picture.

## Choose what's on screen

Every scene needs something to look at that supports its words. In order of preference:
1. **The user's own material:** screenshots, photos, clips and recordings in the folder. Look
   (`ls`, open the pictures) before planning; they decide the story more than you do.
2. **A slide** (```` ```md ````) for a title, a key number, a quote, a short list, or code.
   Slides over a picture get a darkened backdrop, so text stays readable.
3. **A Mermaid diagram** (`render:mermaid`) for structure: processes, architectures, sequences,
   timelines, comparisons, hierarchies. Keep them small enough to read at video size: about 4–8
   nodes. Split big ones across scenes.
4. **A web capture** (`render:web`) of a live page: a product site, a GitHub issue, a doc.
5. **An animated HTML scene** (see `html-scenes.md`) when things should appear in step with the
   words: a title sequence, numbers counting up, a diagram that builds, a before/after.
6. **A stand-in for a picture that doesn't exist yet** (a screenshot of an app, a photo):
   - a `render:placeholder` card, labelled precisely ("Screenshot: the billing page with the new
     tax field"), when the user will supply the picture before the video is used; list each one
     when you deliver;
   - a drawn illustration (an HTML scene mock-up, a diagram) when the video should work as it is,
     labelled "Illustration" if it could pass for the real thing. Never present it as a
     screenshot, and draw only what the source material describes.

**Don't invent files.** A script that references a picture that doesn't exist fails
`narrate check`. Use a placeholder instead.

**Callouts** draw the eye to part of a busy screenshot. Their coordinates are video pixels after
the picture is fitted: for `cover` and a picture with the video's shape, picture coordinates
scaled to the video size.

**Motion:** a gentle `zoom` or `pan` keeps a still picture alive in a long scene. It needs a
picture bigger than the video. Don't animate every picture; vary it.

## Turn existing material into a video

A README, blog post, design doc or outline is written to be read, at the reader's own pace,
with headings and links. A video is heard once, in order, at speaking pace. Adapting it is
mostly cutting.

1. **Find the point.** In one sentence: what should a viewer know or do after watching? Everything
   in the script serves that sentence.
2. **Pick the few things that carry it:** usually three to five. Leave out installation details,
   edge cases, history and caveats, unless the video's purpose is exactly those. Link to the
   document for the rest in the closing scene.
3. **Reorder for listening.** Lead with the problem and the payoff, not background. Documents often
   put "what it is" before "why it matters"; videos work better the other way round.
4. **Rewrite, don't paste.** Turn headings into spoken transitions ("Here's how it works."), bullet
   lists into one sentence plus a slide, and long paragraphs into two short spoken ones.
5. **Reuse the material's assets:** its screenshots, diagrams (re-draw ASCII or image diagrams as
   Mermaid), code samples (as code slides) and its exact product names and terms.
6. **Keep facts exact.** Don't add claims, numbers or features the source doesn't have. If the
   source is ambiguous, keep the narration general rather than guessing.

## Check your own work

Before calling a script done:
- `narrate check --timing` shows no errors, and the total meets the brief.
- Every scene has a visual that matches its words.
- No paragraph runs over about 35 words.
- The contact sheet (`narrate frames … --script …`) shows readable text, nothing important cropped,
  and slides that fit.
- The build's notes hold no surprises, such as a voice matched to an unexpected one, or something
  ignored.
