from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from elevenlabs.client import ElevenLabs


class TTSProvider(Protocol):
    def synthesize_to_file(self, text: str, output_path: Path) -> Path: ...


class ElevenLabsTTS:
    def __init__(self, api_key: str, voice_id: str, model_id: str, output_format: str) -> None:
        self.client = ElevenLabs(api_key=api_key)
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_format = output_format

    def synthesize_to_file(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        audio = self.client.text_to_speech.convert(
            voice_id=self.voice_id,
            model_id=self.model_id,
            output_format=self.output_format,
            text=text,
        )
        with output_path.open("wb") as f:
            if isinstance(audio, bytes):
                f.write(audio)
            else:
                for chunk in audio:
                    f.write(chunk)
        return output_path


class MacOSTTS:
    def __init__(self, voice: str | None = None, rate: int | None = None) -> None:
        self.voice = voice
        self.rate = rate

    def synthesize_to_file(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        suffix = output_path.suffix.lower()
        if suffix == ".mp3":
            return self._synthesize_mp3(text, output_path)

        with tempfile.TemporaryDirectory(prefix=".macos-tts-", dir=output_path.parent) as temp_dir:
            script_path = Path(temp_dir) / "script.txt"
            script_path.write_text(text, encoding="utf-8")
            self._run_say(script_path, output_path)
        return output_path

    def _synthesize_mp3(self, text: str, output_path: Path) -> Path:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(
                "TTS_PROVIDER=macos can read text for free, but macOS built-in tools on this "
                "machine cannot encode MP3. Set AUDIO_OUTPUT_FILE=podcast.m4a, or install "
                "ffmpeg to allow MP3 conversion."
            )

        with tempfile.TemporaryDirectory(prefix=".macos-tts-", dir=output_path.parent) as temp_dir:
            temp_dir_path = Path(temp_dir)
            script_path = temp_dir_path / "script.txt"
            aiff_path = temp_dir_path / "podcast.aiff"
            script_path.write_text(text, encoding="utf-8")
            self._run_say(script_path, aiff_path)
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(aiff_path),
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        return output_path

    def _run_say(self, script_path: Path, output_path: Path) -> None:
        command = ["say"]
        if self.voice:
            command.extend(["-v", self.voice])
        if self.rate:
            command.extend(["-r", str(self.rate)])
        command.extend(["-f", str(script_path), "-o", str(output_path)])
        subprocess.run(command, check=True, capture_output=True, text=True)
