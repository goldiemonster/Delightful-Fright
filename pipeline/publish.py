"""Post a finished Short to the Delightful Fright YouTube channel.

    python -m pipeline.publish out/<slug>/<slug>.mp4 stories/<story>.yaml

The render calls this as its last step when run with --publish. It needs three secrets from a
Google Cloud OAuth client with the YouTube Data API enabled (see README):
YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN. Title, description, tags and
privacy come from the story's `youtube:` block. A video is posted once: the result is written to
published.json next to it, and a second run skips it.
"""
import json
import os
import sys
from pathlib import Path

import requests
import yaml

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SECRETS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


def _access_token() -> str:
    r = requests.post(TOKEN_URL, data={
        "client_id": os.environ["YOUTUBE_CLIENT_ID"],
        "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def metadata(story: dict) -> dict:
    yt = story.get("youtube", {})
    description = yt.get("description", "").strip()
    if "#shorts" not in description.lower():
        description += "\n\n#shorts"
    return {
        "snippet": {
            "title": yt.get("title", f"{story['title']} | Delightful Fright")[:100],
            "description": description[:5000],
            "tags": yt.get("tags", []),
            "categoryId": str(yt.get("category", 24)),  # 24 = Entertainment
        },
        "status": {
            "privacyStatus": yt.get("privacy", "public"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # the "Altered or synthetic content" disclosure: AI art and voice
        },
    }


def publish(video: Path, story: dict) -> str | None:
    """Upload `video`; return its YouTube URL, or None when posting isn't set up."""
    record = video.parent / "published.json"
    if record.exists():
        url = json.loads(record.read_text())["url"]
        print(f"  already posted: {url}")
        return url
    missing = [s for s in SECRETS if not os.environ.get(s)]
    if missing:
        print(f"  ! not posted: set {', '.join(missing)} to post to YouTube (see README)")
        return None
    token = _access_token()
    meta = metadata(story)
    start = requests.post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                   "X-Upload-Content-Type": "video/mp4",
                                   "X-Upload-Content-Length": str(video.stat().st_size)},
                          json=meta, timeout=60)
    start.raise_for_status()
    with video.open("rb") as f:
        done = requests.put(start.headers["Location"], data=f, timeout=1800,
                            headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"})
    done.raise_for_status()
    vid = done.json()["id"]
    url = f"https://youtube.com/shorts/{vid}"
    record.write_text(json.dumps({"id": vid, "url": url, "privacy": meta["status"]["privacyStatus"]}, indent=2))
    print(f"  posted ({meta['status']['privacyStatus']}): {url}")
    return url


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    publish(Path(sys.argv[1]), yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8")))
