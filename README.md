# Delightful Fright: Shorts Pipeline 🕯️

Write a story → push it → get a finished vertical horror Short (narration, visuals,
captions, sound design) plus ready-to-paste upload text. Costs $0.

## The team

| Role | Who | Cost |
|---|---|---|
| CEO / Head Writer | **You**: pick the stories, approve every upload | – |
| Chief of Staff | Claude: drafts scripts with you, maintains this code | your existing plan |
| Narrator | [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) TTS (open-source, runs locally) | free |
| Creative Director | [Pexels](https://www.pexels.com/api/) stock video, your own art in `assets/`, or generated scenes | free |
| Sound Designer | `pipeline/audio.py`: drone, booms and echo generated in code, so there's no licensing risk | free |
| Editor + Captions | FFmpeg: grade, push-ins, word-pop captions | free |
| Render Farm | GitHub Actions (2,000 free minutes/month on private repos; ~3–5 min per Short) | free |

## Make a Short

1. Copy `stories/never-answer-the-third-knock.yaml` to `stories/your-story.yaml` and edit it.
2. Commit and push to `main`. The **Render Shorts** action runs automatically.
3. Open **Actions → latest run → Artifacts → shorts**, then download the zip.
4. Inside are `your-story.mp4` and `upload.txt` (title, description and tags). Watch the video, then upload it.

You can also re-render any story from **Actions → Render Shorts → Run workflow**.

### Writing tips that matter for Shorts
- **Hook in the first line.** The first 2 seconds decide whether people swipe away.
- **Aim for 35–55 seconds.** The render warns you if you go over 60.
- **One idea per line.** Each line gets its own shot.
- **End on a twist that loops.** Make the last line make people rewatch the first.
- Use `*asterisks*` for red emphasis words, `impact: true` for a boom, and `pause: 0.8` for dramatic silence.

## One-time setup

1. **Free Pexels key** (strongly recommended, for real footage): sign up at https://www.pexels.com/api/, then add it to the
   repo under **Settings → Secrets and variables → Actions → New repository secret**, named `PEXELS_API_KEY`.
   Without it, you get generated foggy-forest backgrounds.
2. That's it. Actions installs everything else.

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
