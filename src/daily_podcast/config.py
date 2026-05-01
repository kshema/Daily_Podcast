from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Subject(BaseModel):
    name: str
    focus: str = ""
    priority: str = "medium"


class PodcastConfig(BaseModel):
    title: str = "Morning Brief"
    duration_minutes: int = Field(default=5, ge=1, le=15)
    tone: str = "warm, concise, useful"
    audience: str = "a curious listener"
    include_sources: bool = True


class DeliveryConfig(BaseModel):
    email_subject_prefix: str = "Daily Podcast"
    include_transcript: bool = True
    include_headlines: bool = True


class SubjectsFile(BaseModel):
    podcast: PodcastConfig = Field(default_factory=PodcastConfig)
    subjects: list[Subject]
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.5", alias="OPENAI_MODEL")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")

    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field(default="eleven_multilingual_v2", alias="ELEVENLABS_MODEL_ID")
    elevenlabs_output_format: str = Field(default="mp3_44100_128", alias="ELEVENLABS_OUTPUT_FORMAT")
    tts_provider: str = Field(default="elevenlabs", alias="TTS_PROVIDER")
    macos_voice: str | None = Field(default=None, alias="MACOS_TTS_VOICE")
    macos_rate: int | None = Field(default=None, alias="MACOS_TTS_RATE")
    audio_output_file: str = Field(default="podcast.mp3", alias="AUDIO_OUTPUT_FILE")

    gmail_credentials_file: Path | None = Field(default=None, alias="GMAIL_CREDENTIALS_FILE")
    gmail_token_file: Path = Field(default=Path("secrets/token.json"), alias="GMAIL_TOKEN_FILE")
    email_from: str = Field(default="me", alias="EMAIL_FROM")
    email_to: str | None = Field(default=None, alias="EMAIL_TO")

    enable_audio: bool = Field(default=False, alias="ENABLE_AUDIO")
    enable_email: bool = Field(default=False, alias="ENABLE_EMAIL")

    podcast_timezone: str = Field(default="America/New_York", alias="PODCAST_TIMEZONE")
    podcast_send_hour: int = Field(default=5, alias="PODCAST_SEND_HOUR")
    podcast_send_minute: int = Field(default=0, alias="PODCAST_SEND_MINUTE")
    podcast_output_dir: Path = Field(default=Path("output"), alias="PODCAST_OUTPUT_DIR")


@dataclass(frozen=True)
class AppConfig:
    settings: Settings
    subjects_file: SubjectsFile
    config_path: Path


def load_subjects(path: Path) -> SubjectsFile:
    with path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    return SubjectsFile.model_validate(raw)


def load_app_config(config_path: Path) -> AppConfig:
    load_dotenv()
    return AppConfig(
        settings=Settings(),
        subjects_file=load_subjects(config_path),
        config_path=config_path,
    )
