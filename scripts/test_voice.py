#!/usr/bin/env python3
"""Test voice report flow: API key → voice upload → status poll.

Works without httpx (uses urllib from stdlib).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://localhost:8000"


class HttpClient:
    """Minimal HTTP client (stdlib only)."""

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout

    def post_json(self, url: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode()
        hdrs = {"Content-Type": "application/json", **(headers or {})}
        req = Request(url, data=data, headers=hdrs, method="POST")
        return self._json_response(req)

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> tuple[int, dict]:
        req = Request(url, headers=headers or {}, method="GET")
        return self._json_response(req)

    def post_multipart(
        self,
        url: str,
        fields: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict]:
        boundary = f"----ReportAgent{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            body.extend(f"{value}\r\n".encode())
        for name, (filename, content, mime) in files.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
            )
            body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
            body.extend(content)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())

        hdrs = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            **(headers or {}),
        }
        req = Request(url, data=bytes(body), headers=hdrs, method="POST")
        return self._json_response(req)

    def _json_response(self, req: Request) -> tuple[int, dict]:
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                return exc.code, json.loads(raw) if raw else {"detail": raw}
            except json.JSONDecodeError:
                return exc.code, {"detail": raw}
        except URLError as exc:
            raise RuntimeError(f"Request failed: {exc}") from exc


def _generate_sample_wav(path: Path) -> bool:
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                "-ar", "16000", "-ac", "1", str(path),
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


def _resolve_audio(path_arg: str, prompt_text: str) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if path_arg:
        p = Path(path_arg).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Audio file not found: {p}")
        return p, None

    temp_dir = tempfile.TemporaryDirectory()
    candidate = Path(temp_dir.name) / "voice_test.wav"
    if _tts_wav(candidate, prompt_text) or _generate_sample_wav(candidate):
        return candidate, temp_dir
    temp_dir.cleanup()
    raise FileNotFoundError("No audio file; install ffmpeg or pass --audio /path/to/file.wav")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent voice endpoints")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default="", help="ReportAgent API key (NOT OpenAI key)")
    parser.add_argument("--audio", default="", help="Path to mp3/wav/m4a/ogg")
    parser.add_argument(
        "--prompt-text",
        default=(
            "Создай отчёт по Google Sheets "
            "https://docs.google.com/spreadsheets/d/example/edit "
            "с круговой диаграммой"
        ),
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    client = HttpClient()
    print(f"=== ReportAgent voice test ({base}) ===\n")

    api_key = args.api_key.strip()
    if api_key.startswith("sk-"):
        print("ERROR: X-API-Key must be a ReportAgent key from POST /api/keys/generate,")
        print("       not an OpenAI key (sk-...). OpenAI key goes in .env as OPENAI_API_KEY.")
        return 1

    if not api_key:
        print("1. Generate ReportAgent API key")
        status, payload = client.post_json(f"{base}/api/keys/generate", {"email": "voice-test@example.com"})
        if status not in (200, 201):
            print(f"   Failed: {status} {payload}")
            return 1
        api_key = payload["api_key"]
        print(f"   api_key: ****{api_key[-4:]}\n")
    else:
        print(f"1. Using ReportAgent API key ****{api_key[-4:]}\n")

    headers = {"X-API-Key": api_key}
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    try:
        print("2. Prepare audio")
        try:
            audio_path, temp_dir = _resolve_audio(args.audio, args.prompt_text)
        except FileNotFoundError as exc:
            print(f"   {exc}")
            return 1
        print(f"   file: {audio_path} ({audio_path.stat().st_size} bytes)\n")

        mime, _ = mimetypes.guess_type(audio_path.name)
        mime = mime or "application/octet-stream"
        content = audio_path.read_bytes()

        print("3. POST /voice/generate_report")
        status, payload = client.post_multipart(
            f"{base}/voice/generate_report",
            fields={},
            files={"audio": (audio_path.name, content, mime)},
            headers=headers,
        )
        print(f"   Status: {status}")
        if status == 501:
            print("   Voice disabled — set OPENAI_API_KEY in .env on server and redeploy")
            print(f"   Body: {payload}")
            return 1
        if status not in (200, 202):
            print(f"   Error: {payload}")
            return 1

        task_id = payload.get("task_id")
        st = payload.get("status")
        print(f"   task_id: {task_id}")
        print(f"   status: {st}")
        print(f"   transcript: {(payload.get('transcript') or '')[:120]}")
        if st == "needs_clarification":
            print(f"   clarification: {payload.get('clarification_question')}")
            return 0

        print("\n4. Poll task status")
        for i in range(12):
            time.sleep(5)
            code, data = client.get_json(f"{base}/tasks/{task_id}", headers=headers)
            print(f"   poll {i+1}: HTTP {code} status={data.get('status')}")
            if data.get("status") in ("SUCCESS", "FAILURE", "NEEDS_CLARIFICATION"):
                print(f"   result: {data}")
                break

    finally:
        if temp_dir:
            temp_dir.cleanup()

    print("\nVoice test finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
