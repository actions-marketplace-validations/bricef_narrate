# Make videos with an AI assistant

This guide is for people who don't use the command line. With narrate and an
AI assistant, you can make narrated videos by describing what you want, in
your own words, and watching the drafts. You never type a command.

The work splits like this:

- **You** decide what the video says and shows, supply any pictures, and
  watch each draft.
- **The assistant** writes the script, runs narrate, checks the result, and
  makes the changes you ask for.

The last part of this guide, [For the assistant](#for-the-assistant-setting-up),
is written for the assistant: give it this page, and it can set everything up.

- [What you need](#what-you-need)
- [Set up, once](#set-up-once)
- [Make your first video](#make-your-first-video)
- [Review and change it](#review-and-change-it)
- [Choose a voice, and what it costs](#choose-a-voice-and-what-it-costs)
- [What stays on your computer](#what-stays-on-your-computer)
- [The files in your folder](#the-files-in-your-folder)
- [If something goes wrong](#if-something-goes-wrong)
- [Words you'll hear](#words-youll-hear)
- [For the assistant: setting up](#for-the-assistant-setting-up)

## What you need

- **A computer** (a Mac, or a Linux PC) with about 5 GB of free space, plugged
  in while it builds videos. Windows should work too, but hasn't been tested.
- **Docker Desktop:** a free app that runs narrate. Download it from
  [docker.com](https://www.docker.com/products/docker-desktop/) and install it
  like any other app. Larger organisations may need a paid Docker
  subscription; check Docker's terms.
  - **On a Mac, you can skip Docker:** the assistant can install narrate with
    [Homebrew](https://brew.sh/), a free tool for installing programs.
    On a Mac with an Apple chip, videos then build several times faster.
    Installing Homebrew asks for your Mac's password once.
- **An AI assistant that can work with files and run programs on your
  computer,** such as Claude Code in the Claude desktop app. An assistant that
  only chats in a web page can write a script for you, but it can't build the
  video.
- **This guide and the narrate skill** (the instructions that teach the
  assistant to use narrate). Both are free, in the
  [narrate repository](https://github.com/bricef/narrate) on GitHub, and the
  assistant can download them.
- **Optionally, an ElevenLabs account,** for the most natural voices. It's a
  paid service; narrate's free voices are fine for most drafts.

## Set up, once

1. **Install Docker Desktop and open it.** Wait until it says its engine is
   running. Docker Desktop needs to be open whenever you make videos. To use
   Homebrew on a Mac instead, skip this step, and tell the assistant in step 3.
2. **Make a folder for your videos,** for example `Videos` in your Documents.
   Each video gets its own folder inside it.
3. **Open your assistant in that folder** and give it this page (the file, or
   its link), with:

   ```text
   Please set me up to make videos with narrate. Follow the section
   "For the assistant: setting up" in this guide, and tell me when it's done.
   ```

The assistant downloads narrate (about 420 MB with Docker), installs the
narrate skill, and makes a short test video to show it all works. If your Mac
doesn't have Homebrew yet, the assistant may ask you to paste one command into
the Terminal app and type your Mac's password. The first real video also
downloads a voice (about 350 MB). After that, setting up is done.

## Make your first video

1. **Make a folder for the video,** inside your videos folder, and put in it
   anything the video should use: photos, screenshots, short clips, a logo, or
   the document the video is about. Pictures should be JPG, PNG or GIF; the
   assistant can convert others.
2. **Open your assistant in that folder** and describe the video. Say who it's
   for, roughly how long it should be, what it should cover, and what to use:

   ```text
   Make a narrated video with narrate.
   It's for: new volunteers at our Code Club.
   Length: about two minutes.
   It should explain: how a session runs, from setting up to tidying away.
   Use: the photos in this folder, and the notes in session-plan.docx.
   Voice: a friendly British woman. Use a free voice for now.
   ```

3. **Wait while it works.** The assistant plans the scenes, writes the
   script, checks how long it runs, makes a quick silent preview to check
   the pictures, and then builds a draft with a free voice. It tells you where
   the video is.

**How long a build takes** depends on what's in the video: a few minutes for
pictures and slides, and longer for animated scenes. A four-minute video with
an animation in every scene took about 18 minutes on a recent Mac, with
narrate built for its chip. With the standard download, Macs with Apple chips
currently take several times longer (the assistant's setup covers this).

**Keep the computer awake while it builds.** If it goes to sleep, the build
pauses until it wakes. On a Mac, ask the assistant to keep it awake for the
build; it can do that and let go when the build ends.

You don't have to write the script, but you can read it: it's a plain text
file, `script.md`, and it looks like this. A line of three dashes starts a new
scene, and each paragraph is spoken by the voice:

````markdown
---
voice: Amy
---

![](photo.jpg)

Welcome to Code Club! In the next two minutes, we'll walk through a session.

---

```md
# Before you start
* laptops and chargers
* the sign-in sheet
```

The first ten minutes are for setting up.
````

## Review and change it

Watch the draft, then ask for changes the way you'd ask a colleague. Mention
the time in the video, or describe the scene:

- "At 1:20 the picture changes before she mentions the hall."
- "The third scene is too long. Cut it to two sentences."
- "Use the photo of the sign-in desk instead."
- "Say 'Code Club', not 'code club', and pause before the last sentence."
- "Add subtitles, burned into the picture, for social media."
- "Make a square version for Instagram."

The assistant changes the script and builds again. Only the parts you
changed are recorded again, so small changes are quick.

- **Pronunciation:** ask the assistant to "check the pronunciation". narrate
  listens to the video and lists any word the voice said differently from the
  script.
- **Seeing it all at once:** ask for "a contact sheet": one picture from each
  scene, on one page.
- **Clicking instead of asking:** ask the assistant to "open narrate studio".
  It opens a page in your web browser with the script, a preview of each
  scene, a timeline, and every voice to listen to. You can change the text
  there and press **Save**; tell the assistant when you have.

## Choose a voice, and what it costs

- **Free voices** (Kokoro) run on your computer, cost nothing, and sound
  good. Use them for every draft.
- **ElevenLabs voices** sound more natural, and cost ElevenLabs credits for
  every character spoken. As a guide, a minute of narration is about 1,000
  characters. The assistant tells you how many characters a build will use,
  and asks before spending any. Building again only pays for the parts that
  changed.
- **Choosing:** describe the voice you want ("a calm American man"), or ask
  the assistant to play you a few in narrate studio.
- **Your ElevenLabs key** is like a password. Ask the assistant to make a
  file called `.env` in your video folder and open it for you, then paste the
  key into that file, not into the chat. The chat may be kept in the
  conversation's history.

## What stays on your computer

narrate itself runs on your computer: your pictures, scripts and videos stay
there, and the free voices don't send anything anywhere. Some things do
leave it:

- **The AI assistant** reads the files you work on with it, and sends them to
  its provider to do its work, like anything else you share with it.
- **ElevenLabs** receives the narration's text, if you use its voices.
- **Web pages** shown in the video are fetched from the internet.

## The files in your folder

After a build, the video's folder holds:

- **`script.md`:** the video, as text. Keep it: it's how the video can be
  changed and rebuilt later.
- **Your pictures and clips,** as you left them.
- **`script.mp4`:** the video.
- **`script.jpg`:** a poster: a still from the video, for thumbnails.
- **`script.srt` and `script.vtt`:** subtitles, when the video has them.

To make a new version while keeping the old one, ask the assistant to copy
the folder first.

## If something goes wrong

- **"Can't connect to Docker":** Docker Desktop isn't open. Open it, wait
  until its engine is running, and ask the assistant to try again.
- **A build is very slow:** check that the computer didn't go to sleep, and
  that it's plugged in.
- **Something doesn't look or sound right:** describe it, with the time in
  the video. The assistant can look at the frames and listen to the
  narration itself.
- **An error you don't understand:** ask the assistant to explain it in
  plain words, and what it will do about it.

## Words you'll hear

| Word | What it means |
| --- | --- |
| **Script** | The text file the video is made from: what's said, and what's shown while it's said. |
| **Scene** | One part of the video: a picture or animation, and the words spoken over it. |
| **Build** (or render) | Making the video from the script. |
| **Preview** | A quick, silent build, to check the pictures before recording the voice. |
| **Draft** | A build with a free voice, to watch and review. |
| **Kokoro** | narrate's free voices, which run on your computer. |
| **ElevenLabs** | A paid service with more natural voices. |
| **Credits** | What ElevenLabs charges in, per character spoken. |
| **narrate studio** | narrate's editor, in your web browser. |
| **Docker** | The app that runs narrate on your computer. |
| **Homebrew** | A free tool for installing programs on a Mac: the other way to run narrate on one. |
| **Skill** | Instructions that teach the AI assistant to use narrate. |

## For the assistant: setting up

This part is for the AI assistant. The person you're helping doesn't use the
command line: talk to them in plain words, show them results rather than
commands, and say where each file is.

**Docker or Homebrew:** use Docker, unless the person asked for Homebrew on a
Mac. On a Mac with Apple Silicon (`uname -m` prints `arm64`), suggest
Homebrew: narrate then runs natively, several times faster than the published
image. For Homebrew, do [On a Mac, without Docker](#on-a-mac-without-docker)
in place of steps 1 to 3 below.

1. **Docker:** check that `docker version` reaches the engine. If it can't,
   ask the person to open Docker Desktop (on macOS, `open -a Docker` starts
   it), and wait until it answers.
2. **The image:** `docker pull ghcr.io/bricef/narrate`. It's public, so no
   login is needed.
   - **On Apple Silicon,** add `--platform linux/amd64` to `docker pull` and
     `docker run`: the image is published for x86-64 only, and runs under
     emulation, several times more slowly
     ([#91](https://github.com/bricef/narrate/issues/91)). A native image is
     faster: clone the repository
     (`git clone https://github.com/bricef/narrate.git`), run
     `docker build --platform linux/arm64 --target runtime -t narrate:local .`
     in it (it compiles ffmpeg, so it takes a while), then use `narrate:local`.
3. **How to run narrate,** from the video's folder:

   ```sh
   docker run --rm --user "$(id -u):$(id -g)" -w /work -v "$PWD:/work" \
       -v narrate-cache:/cache ghcr.io/bricef/narrate COMMAND …
   ```

   - **`-w /work`** works around the published image starting in the wrong
     folder ([#88](https://github.com/bricef/narrate/issues/88)).
   - **The cache volume:** while
     [#89](https://github.com/bricef/narrate/issues/89) is open, a new
     `narrate-cache` volume holds folders your user can't write to, and a
     build fails at its very end. Fix it once, before the first build:
     `docker run --rm --user 0 -v narrate-cache:/cache --entrypoint chown ghcr.io/bricef/narrate -R "$(id -u):$(id -g)" /cache`
   - **The studio** needs its port published:
     `-p 127.0.0.1:8787:8787 … studio script.md --host 0.0.0.0`, then open
     <http://127.0.0.1:8787/> for the person.
4. **The skill:** install `skills/narrate` from the repository where your
   agent finds skills. For Claude Code, copy or link it to
   `~/.claude/skills/narrate`, or run `just install-skill` in a checkout.
   Read it before making a video: it covers the whole loop, from the brief to
   the review.
5. **Check it works:** run `doctor`, then build a ten-second script with
   `--tts kokoro` (a slide and two sentences), and show the person the video.
6. **Every build after that:**
   - **Keep the machine awake.** A sleeping Mac pauses the build. On macOS,
     run the build under `caffeinate -s -i`, which lets go when it ends.
   - **Long builds:** tell the person roughly how long a build will take,
     and run long ones in the background.
   - **ElevenLabs:** never use it without asking. Quote the characters from
     `check --timing --tts elevenlabs` first, as the skill says.
   - **The result:** say where the video is, and offer to open it.

### On a Mac, without Docker

These replace steps 1 to 3 above.

1. **Homebrew:** check that `brew --version` works. If it doesn't, ask the
   person to install Homebrew: they paste the command from
   [brew.sh](https://brew.sh/) into the Terminal app and type their Mac's
   password, which you can't do for them. Say that it can take a few minutes.
2. **narrate:** follow the README's macOS steps
   ([From source](../README.md#from-source)). Clone the repository into a
   folder of its own, such as `~/narrate`, not the videos folder. Homebrew's
   `ffmpeg-full` is the one narrate needs: the plain `ffmpeg` lacks the
   subtitle and pitch filters.
3. **How to run narrate,** from the video's folder:
   `uv run --project ~/narrate narrate COMMAND …`. The studio needs no
   published port: `studio script.md --open` opens it in the person's
   browser.

For narrate's full documentation, see [Writing scripts](writing-scripts.md)
and [Building videos](building.md).
