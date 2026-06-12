#!/usr/bin/env python3
"""Test voice report flow: API key → voice upload → status poll."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


def _generate_sample_wav(path: Path) -> bool:
    """Create a minimal WAV using ffmpeg (speech-like tone as placeholder)."""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=2",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _tts_wav(path: Path, text: str) -> bool:
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.save_to_file(text, str(path))
        engine.runAndWait()
        return path.is_file() and path.stat().st_size > 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent voice endpoints")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default="", help="Existing API key (generated if empty)")
    parser.add_argument(
        "--audio",
        default="",
        help="Path to audio file (mp3/wav/m4a/ogg). Generated if missing.",
    )
    parser.add_argument(
        "--prompt-text",
        default=(
            "Создай отчёт по Google Sheets "
            "https://docs.google.com/spreadsheets/d/example/edit "
            "с круговой диаграммой и отправь на test@example.com"
        ),
        help="Text for TTS sample (if pyttsx3 available)",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"=== ReportAgent voice test ({base}) ===\n")

    with httpx.Client(timeout=120.0) as client:
        api_key = args.api_key
        if not api_key:
            print("1. Generate API key")
            resp = client.post(f"{base}/api/keys/generate", json={"email": "voice-test@example.com"})
            if resp.status_code not in (200, 201):
                print(f"   Failed: {resp.status_code} {resp.text}")
                return 1
            api_key = resp.json()["api_key"]
            print(f"   api_key: ****{api_key[-4:]}\n")
        else:
            print(f"1. Using provided API key ****{api_key[-4:]}\n")

        headers = {"X-API-Key": api_key}

        audio_path = Path(args.audio) if args.audio else None
        temp_dir: tempfile.TemporaryDirectory[str] | None = None

        if audio_path is None or not audio_path.is_file():
            print("2. Prepare test audio")
            temp_dir = tempfile.TemporaryDirectory()
            candidate = Path(temp_dir.name) / "voice_test.wav"
            if _tts_wav(candidate, args.prompt_text):
                audio_path = candidate
                print(f"   Created TTS wav: {audio_path}")
            elif _generate_sample_wav(candidate):
                audio_path = candidate
                print(f"   Created ffmpeg tone wav: {audio_path}")
                print("   NOTE: tone-only audio may not produce useful intent — pass --audio with real speech")
            else:
                print("   ERROR: provide --audio FILE or install ffmpeg/pyttsx3 for auto sample")
                return 1
            print()

        assert audio_path is not None

        print("3. POST /voice/generate_report")
        with audio_path.open("rb") as f:
            resp = client.post(
                f"{base}/voice/generate_report",
                headers=headers,
                files={"audio": (audio_path.name, f, "audio/wav")},
            )

        print(f"   Status: {resp.status_code}")
        if resp.status_code == 501:
            print("   Voice disabled — set OPENAI_API_KEY and VOICE_ENABLED=true in .env")
            print(f"   Body: {resp.text}")
            return 1
        if resp.status_code not in (200, 202):
            print(f"   Error: {resp.text}")
            return 1

        payload = resp.json()
        task_id = payload.get("task_id")
        status = payload.get("status")
        print(f"   task_id: {task_id}")
        print(f"   status: {status}")
        print(f"   transcript: {payload.get('transcript', '')[:120]}...")
        if status == "needs_clarification":
            print(f"   clarification: {payload.get('clarification_question')}")
            print("\n   Use POST /voice/clarify with task_id and answer to continue.")
            return 0

        print("\n4. Poll task status")
        for i in range(12):
            time.sleep(5)
            tr = client.get(f"{base}/tasks/{task_id}", headers=headers)
            if tr.status_code != 200:
                print(f"   poll {i+1}: HTTP {tr.status_code}")
                continue
            data = tr.json()
            st = data.get("status")
            print(f"   poll {i+1}: {st}")
            if st in ("SUCCESS", "FAILURE", "NEEDS_CLARIFICATION"):
                print(f"   result: {data}")
                break

    if temp_dir:
        temp_dir.cleanup()

    print("\nVoice test finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
