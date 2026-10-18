# Delightful Fright: Shorts Pipeline 🕯️

Write a story → push it → get a finished vertical horror Short (narration, visuals,
captions, sound design) plus ready-to-paste upload text. Costs $0.

## The team

| Role | Who | Cost |
|---|---|---|
| CEO / Head Writer | **You**: pick the stories, approve every upload | – |
| Chief of Staff | Claude: drafts scripts with you, maintains this code | your existing plan |
| Narrator | [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) TTS, voices can be blended (`bm_george:0.7,am_onyx:0.3`), then EQ, compression and a small room | free |
| Art Director | AI cinematic stills from each line's `scene` prompt ([Pollinations](https://pollinations.ai) FLUX, or Hugging Face FLUX.1-schnell with `HF_TOKEN`); your own art in `assets/`; [Pexels](https://www.pexels.com/api/) footage | free |
| Camera | `pipeline/visuals.py`: smooth push-ins, pans and handheld drift, camera shake and a flash on impacts, warm low-key grade, film grain | free |
| Composer + Sound Designer | `pipeline/audio.py`: a generated dark score (drone, pad, sparse piano) that ducks under the voice, risers into booms, knocks, heartbeats, bells; or your own track | free |
| Editor + Captions | FFmpeg + [faster-whisper](https://github.com/SYSTRAN/faster-whisper): captions timed to each spoken word with the current word lit, title card on the hook, mastered to YouTube's -14 LUFS | free |
| Render Farm | GitHub Actions (2,000 free minutes/month on private repos; about 8–12 min per Short) | free |

## Make a Short

1. Copy `stories/never-answer-the-third-knock.yaml` to `stories/your-story.yaml` and edit it.
2. Commit and push to `main`. The **Render Shorts** action runs automatically.
3. Open **Actions → latest run → Artifacts → shorts**, then download the zip.
4. Inside are `your-story.mp4` and `upload.txt` (title, description and tags). Watch the video, then upload it.

You can also re-render any story from **Actions → Render Shorts → Run workflow**.

### Writing tips that matter for Shorts
- **Hook in the first line.** Say the title's promise straight away: the first 2 seconds decide the swipe.
- **Aim for 60–75 seconds** (about 160–190 words, 18–24 lines). Short, plain sentences in first person.
- **One image per line.** Write each `scene` like a film still: subject, place, light ("lit by one oil lamp").
- **Escalate, then twist, then loop.** The last line should send people back to the first.
- Use `*asterisks*` for red words, `impact: true` for a riser + boom + flash, `sfx: knock` for sound
  effects, and `pause: 0.8` for silence. See the top of the sample story for every option.

## One-time setup

Nothing is required: AI stills come free from Pollinations. Optional repo secrets
(**Settings → Secrets and variables → Actions → New repository secret**):

- `HF_TOKEN`: a free [Hugging Face token](https://huggingface.co/settings/tokens); stills then come from FLUX.1-schnell, which is faster and more reliable.
- `POLLINATIONS_TOKEN`: a free [Pollinations token](https://auth.pollinations.ai) for higher rate limits.
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
