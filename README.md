# Delightful Fright: Shorts Pipeline 🕯️

Write a story → push it → get a finished vertical horror Short (narration, visuals,
captions, sound design) plus ready-to-paste upload text. Costs $0.

## The team

| Role | Who | Cost |
|---|---|---|
| CEO / Head Writer | **You**: pick the stories, approve every upload | – |
| Chief of Staff | Claude: drafts scripts with you, maintains this code | your existing plan |
| Narrator | [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) TTS, voices can be blended (`bm_george:0.7,am_onyx:0.3`); or [Cartesia](https://cartesia.ai) Sonic (the channel's voices, e.g. Charlotte) with `cartesia_voice` + `CARTESIA_API_KEY`. Never time-stretched; EQ, compression and a small room | free / Cartesia plan |
| Art Director | Gritty painted-realism stills in the channel's look (lamp-lit amber against blue-black shadows), built like the production bible's shot prompts (continuity `anchors` + `scene`, `camera`, `action`, `evidence`) ([Pollinations](https://pollinations.ai) FLUX with [AI Horde](https://aihorde.net) as a free fallback, or Hugging Face FLUX.1-schnell with `HF_TOKEN`); your own art in `assets/`; [Pexels](https://www.pexels.com/api/) footage | free |
| Camera | `pipeline/visuals.py`: smooth push-ins, pans and handheld drift, a faltering light on impacts, the channel's warm low-key grade, film grain | free |
| Composer + Sound Designer | `pipeline/audio.py`: a generated eerie score (beating drone, drifting glass tones, moving air) that ducks under the voice and falls silent before impacts, a house that settles, knocks, creaks, low swells; or your own track | free |
| Editor + Captions | FFmpeg + [faster-whisper](https://github.com/SYSTRAN/faster-whisper): captions timed to each spoken word with the current word lit, title card on the hook, mastered to YouTube's -14 LUFS | free |
| QA | `pipeline/qa.py`: re-listens to every line with speech recognition (complete, in order), checks loudness, true peak, voice over music, the last 10 seconds and black frames; writes `qa.txt` and exports voice/music/effects stems for a listening pass | free |
| Render Farm | GitHub Actions (2,000 free minutes/month on private repos; about 8–12 min per Short) | free |

## Make a Short

1. Copy `stories/never-answer-the-third-knock.yaml` to `stories/your-story.yaml` and edit it.
2. Commit and push to `main`. The **Render Shorts** action runs automatically.
3. Open **Actions → latest run → Artifacts → shorts**, then download the zip.
4. Inside are `your-story.mp4` and `upload.txt` (title, description and tags). Watch the video, then upload it.

You can also re-render any story from **Actions → Render Shorts → Run workflow**.

### Writing tips that matter for Shorts
- **Build the ending first.** Then give the narrator a goal, a concrete anomaly, two escalating
  discoveries, an active choice, and a revelation the story has earned.
- **Hook in the first line**, and **aim for 75–90 seconds** (about 190–230 words, 18–24 lines).
- **One shot per line.** Describe each character once in `anchors` and the place and light in
  `anchors.world`; give each line a `scene` that names who is in it ("the narrator ..."), and,
  when it matters, a `camera`, a single `action`, and the `evidence` that must be visible.
- **Keep the picture consistent with `plates`.** Paint one master per room under `plates:` and
  point each line at one with `plate:`, reframing it with `frame: [x, y, zoom]`. A plate with
  `from: hallway` and `strength: 0.5` is an edit of that master (a hand at the door, a shadow on
  the wall), so the room and the light never change between shots. Keep faces out of frame:
  hands, sleeves and silhouettes stay consistent where AI-painted faces drift.
- Use `*asterisks*` for amber words, `impact: true` for a silence, low swell and faltering light, `sfx: knock` for sound
  effects, and `pause: 0.8` for silence. See the top of the sample story for every option.

### Before you publish
Each render writes `qa.txt` (PASS / FAIL / UNVERIFIED per check) and `stems/` next to the video.
The checks measure; they don't listen, so play the video once at normal speed before uploading,
and look over `contact_sheet.jpg` (one frame per line) for faces or rooms that changed.
If no image source was reachable, shots fall back to a plain fog placeholder and the
"Story shots" check FAILS: re-render where the image service is reachable (GitHub Actions is).

## One-time setup

Nothing is required: AI stills come free from Pollinations. Optional repo secrets
(**Settings → Secrets and variables → Actions → New repository secret**):

- `HF_TOKEN`: a free [Hugging Face token](https://huggingface.co/settings/tokens); stills then come from FLUX.1-schnell, which is faster and more reliable.
- `POLLINATIONS_TOKEN`: a free [Pollinations token](https://auth.pollinations.ai) for higher rate limits.
- `AIHORDE_API_KEY`: optional free [AI Horde key](https://aihorde.net/register). When Pollinations is rate-limited, stills come from AI Horde's volunteer GPUs; anonymous works but queues behind registered users.
- `CARTESIA_API_KEY`: your [Cartesia](https://play.cartesia.ai) key, for stories that set `cartesia_voice`.
- `PEXELS_API_KEY`: a free [Pexels key](https://www.pexels.com/api/), used for lines that have a `visual` search and no `scene`.

Pull requests that touch a story or the pipeline render a preview Short automatically
(**Checks → Render Shorts → Summary → Artifacts**).

### Run on your own computer (optional)
```bash
# needs Python 3.10+ and ffmpeg (Mac: brew install ffmpeg · Windows: winget install ffmpeg)
pip install -r requirements.txt
python -m pipeline.download_models          # one time, ~340 MB
export PEXELS_API_KEY=your_key              # optional
python -m pipeline.render stories/never-answer-the-third-knock.yaml
```

## Rules to protect the channel
- **Use original stories or the public domain** (Poe, Lovecraft, M.R. James, Blackwood, Le Fanu). Don't
  narrate Reddit/Creepypasta posts without the author's written permission.
- **Keep your own input in every video.** YouTube demonetizes "mass-produced, repetitive" content. You
  choosing, editing and approving each story is what makes this a channel and not a content farm.
- **Disclose realistic AI content** with the "Altered or synthetic content" toggle in YouTube Studio.
- Pexels footage is free for commercial use; credit is appreciated but not required.

## Roadmap
- [x] Phase 1: story → finished Short
- [ ] Phase 2: content calendar in Google Sheets and a backlog of public-domain story ideas
- [ ] Phase 3: auto-upload to YouTube as **private/scheduled** for one-click approval
