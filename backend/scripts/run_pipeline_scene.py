#!/usr/bin/env python3
"""Call the Between Two Hearts API: optional Imagen portraits, video (Veo or placeholder), dialogue mix, compose."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")


def http_post(url: str, body: dict | None = None, *, timeout_s: float = 3900.0) -> dict:
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            detail = json.loads(raw).get("detail", raw)
        except json.JSONDecodeError:
            detail = raw or str(e.reason)
        raise SystemExit(f"HTTP {e.code}: {detail}") from None


def main() -> None:
    ap = argparse.ArgumentParser(description="Run drama pipeline on one scene.")
    ap.add_argument("scene_id", nargs="?", type=int, default=1)
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument(
        "--use-placeholder-video",
        action="store_true",
        help="Solid-color slate instead of Vertex Veo (set ALLOW_PLACEHOLDER_VIDEO=true in .env)",
    )
    ap.add_argument(
        "--portraits",
        action="store_true",
        help="Generate missing Imagen portraits (requires GCP Application Default Credentials)",
    )
    args = ap.parse_args()
    sid = args.scene_id
    b = args.base_url.rstrip("/")

    if args.portraits:
        deck = json.loads(urllib.request.urlopen(b + "/api/characters").read().decode())
        print("=== Portraits · Imagen (Vertex ADC or Gemini API via GEMINI_API_KEY) ===")
        for c in deck:
            if c.get("portrait_url"):
                print(f"[skip {c['name']}] portrait already saved")
                continue
            http_post(f"{b}/api/characters/{c['id']}/generate-portrait")

    vid_ep = "/generate-placeholder-video" if args.use_placeholder_video else "/generate-video"
    print(f"\n=== Video · {vid_ep} ===")
    http_post(f"{b}/api/scenes/{sid}{vid_ep}")

    print("\n=== Dialogue mix · TTS_BACKEND=auto (ElevenLabs or Edge) ===")
    http_post(f"{b}/api/scenes/{sid}/generate-dialogue-audio", {}, timeout_s=900.0)

    print("\n=== Compose final MP4 ===")
    out = http_post(f"{b}/api/scenes/{sid}/compose-final", {}, timeout_s=120.0)

    fv, vv, av = out.get("final_video_url"), out.get("video_url"), out.get("audio_url")
    print("video_url:", vv)
    print("audio_url:", av)
    print("final_video_url:", fv)
    if fv:
        print("\nOpen:", b + fv)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
