from __future__ import annotations

import json
import logging
from html import escape
from datetime import date
from pathlib import Path

from .ai import Headline, PodcastDraft, PodcastWriter
from .config import AppConfig
from .gmailer import GmailSender
from .llm import build_llm_client
from .tts import ElevenLabsTTS, MacOSTTS, TTSProvider


class DailyPodcastAgent:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        settings = config.settings
        llm = build_llm_client(
            provider=settings.llm_provider,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
        self.writer = PodcastWriter(llm)
        self.tts: TTSProvider | None = None
        self.mailer = None

        if settings.enable_audio:
            provider = settings.tts_provider.lower()
            if provider == "elevenlabs":
                if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
                    raise ValueError(
                        "ENABLE_AUDIO=true with TTS_PROVIDER=elevenlabs requires "
                        "ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID."
                    )
                self.tts = ElevenLabsTTS(
                    api_key=settings.elevenlabs_api_key,
                    voice_id=settings.elevenlabs_voice_id,
                    model_id=settings.elevenlabs_model_id,
                    output_format=settings.elevenlabs_output_format,
                )
            elif provider == "macos":
                self.tts = MacOSTTS(voice=settings.macos_voice, rate=settings.macos_rate)
            else:
                raise ValueError("TTS_PROVIDER must be either 'elevenlabs' or 'macos'.")

        if settings.enable_email:
            if not settings.gmail_credentials_file or not settings.email_to:
                raise ValueError("ENABLE_EMAIL=true requires GMAIL_CREDENTIALS_FILE and EMAIL_TO.")
            self.mailer = GmailSender(
                credentials_file=settings.gmail_credentials_file,
                token_file=settings.gmail_token_file,
                sender=settings.email_from,
            )

    def run_once(self) -> dict[str, str]:
        today = date.today().isoformat()
        run_dir = self.config.settings.podcast_output_dir / today
        run_dir.mkdir(parents=True, exist_ok=True)
        logging.info("Writing artifacts under %s", run_dir)

        logging.info("Generating podcast draft with %s", self.config.settings.openai_model)
        draft = self.writer.create_draft(
            podcast=self.config.subjects_file.podcast,
            subjects=self.config.subjects_file.subjects,
        )
        self._write_draft_files(draft, run_dir)
        logging.info("Draft generated: %s headlines, %s script characters", len(draft.headlines), len(draft.script))

        audio_path = run_dir / self.config.settings.audio_output_file
        audio_status = "skipped"
        if self.tts:
            logging.info("Generating audio with %s", self.config.settings.tts_provider)
            self.tts.synthesize_to_file(draft.script, audio_path)
            logging.info("Audio written to %s", audio_path)
            audio_status = "created"
        else:
            logging.info("Audio generation skipped because ENABLE_AUDIO=false")

        message_id = "skipped"
        if self.mailer:
            subject = f"{self.config.subjects_file.delivery.email_subject_prefix}: {draft.title}"
            logging.info("Sending email to %s", self.config.settings.email_to)
            attachment_paths = [run_dir / "summary.html", run_dir / "summary.md"]
            if audio_status == "created":
                attachment_paths.append(audio_path)
            message_id = self.mailer.send(
                to=self.config.settings.email_to or "",
                subject=subject,
                body_text=self._email_body(draft),
                body_html=_format_email_html(draft),
                attachment_paths=attachment_paths,
            )
            logging.info("Email sent with Gmail message id %s", message_id)
        else:
            logging.info("Email sending skipped because ENABLE_EMAIL=false")

        return {
            "message_id": message_id,
            "audio_path": str(audio_path) if audio_status == "created" else audio_status,
            "summary_path": str(run_dir / "summary.md"),
            "html_summary_path": str(run_dir / "summary.html"),
            "script_path": str(run_dir / "script.md"),
            "run_dir": str(run_dir),
        }

    def send_existing(self, run_dir: Path | None = None) -> dict[str, str]:
        if not self.mailer:
            raise ValueError("ENABLE_EMAIL=true is required to send existing podcast artifacts.")

        if run_dir is None:
            run_dir = self.config.settings.podcast_output_dir / date.today().isoformat()
        logging.info("Reusing existing podcast artifacts from %s", run_dir)

        draft = self._read_draft_files(run_dir)
        audio_path = run_dir / self.config.settings.audio_output_file

        subject = f"{self.config.subjects_file.delivery.email_subject_prefix}: {draft.title}"
        logging.info("Sending existing digest to %s", self.config.settings.email_to)
        attachment_paths = [run_dir / "summary.html", run_dir / "summary.md"]
        if audio_path.exists():
            attachment_paths.append(audio_path)
        message_id = self.mailer.send(
            to=self.config.settings.email_to or "",
            subject=subject,
            body_text=self._email_body(draft),
            body_html=_format_email_html(draft),
            attachment_paths=[path for path in attachment_paths if path.exists()],
        )
        logging.info("Email sent with Gmail message id %s", message_id)
        return {
            "message_id": message_id,
            "audio_path": str(audio_path) if audio_path.exists() else "skipped",
            "run_dir": str(run_dir),
        }

    @staticmethod
    def _write_draft_files(draft: PodcastDraft, run_dir: Path) -> None:
        summary = _format_summary(draft)
        script = _format_script(draft)
        html_summary = _format_email_html(draft)
        (run_dir / "summary.md").write_text(summary, encoding="utf-8")
        (run_dir / "summary.html").write_text(html_summary, encoding="utf-8")
        (run_dir / "script.md").write_text(script, encoding="utf-8")
        (run_dir / "email_summary.txt").write_text(summary, encoding="utf-8")
        (run_dir / "script.txt").write_text(script, encoding="utf-8")
        (run_dir / "draft.json").write_text(
            json.dumps(
                {
                    "title": draft.title,
                    "date": draft.date,
                    "email_summary": draft.email_summary,
                    "script": draft.script,
                    "sections": draft.sections,
                    "headlines": [headline.__dict__ for headline in draft.headlines],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _read_draft_files(run_dir: Path) -> PodcastDraft:
        draft_path = run_dir / "draft.json"
        if not draft_path.exists():
            raise FileNotFoundError(str(draft_path))

        payload = json.loads(draft_path.read_text(encoding="utf-8"))
        return PodcastDraft(
            title=payload["title"],
            date=payload["date"],
            email_summary=payload["email_summary"],
            script=payload["script"],
            sections=payload.get("sections", []),
            headlines=[
                Headline(
                    title=item["title"],
                    summary=item["summary"],
                    source_title=item.get("source_title"),
                    source_url=item.get("source_url"),
                )
                for item in payload["headlines"]
            ],
        )

    def _email_body(self, draft: PodcastDraft) -> str:
        lines = [
            draft.title,
            draft.date,
            "",
            "News Brief:",
        ]
        for headline in draft.headlines:
            lines.extend(
                [
                    "",
                    headline.title,
                    headline.summary,
                ]
            )
            if headline.source_url:
                lines.append(f"Read more: {headline.source_url}")

        return "\n".join(lines)


def _format_summary(draft: PodcastDraft) -> str:
    lines = [
        f"# {draft.title}",
        "",
        f"Date: {draft.date}",
        "",
    ]
    lines.extend(["## News Brief", ""])
    for headline in draft.headlines:
        lines.extend([f"### {headline.title}", "", headline.summary])
        if headline.source_url:
            source_title = headline.source_title or "Read more"
            lines.extend(["", f"[{source_title}]({headline.source_url})"])
        lines.append("")

    sources = [
        (headline.source_title, headline.source_url)
        for headline in draft.headlines
        if headline.source_url
    ]
    if sources:
        lines.extend(["", "## Sources", ""])
        for title, url in sources:
            label = title or url
            lines.append(f"- [{label}]({url})")

    return "\n".join(lines).strip() + "\n"


def _format_script(draft: PodcastDraft) -> str:
    lines = [
        f"# {draft.title}",
        "",
        f"Date: {draft.date}",
        "",
    ]

    if draft.sections:
        for section in draft.sections:
            title = str(section.get("title", "Section")).strip() or "Section"
            lines.extend([f"## {title}", ""])
            key_points = section.get("key_points", [])
            if isinstance(key_points, list) and key_points:
                lines.append("Key points:")
                for point in key_points:
                    lines.append(f"- {point}")
                lines.append("")
            section_script = str(section.get("script", "")).strip()
            if section_script:
                lines.extend(_paragraphs(section_script))
                lines.append("")
    else:
        lines.extend(["## Script", ""])
        lines.extend(_paragraphs(draft.script))

    return "\n".join(lines).strip() + "\n"


def _format_email_html(draft: PodcastDraft) -> str:
    headline_cards = []
    for headline in draft.headlines:
        link = ""
        if headline.source_url:
            label = escape(headline.source_title or "Read more")
            url = escape(headline.source_url, quote=True)
            link = f'<p class="source"><a href="{url}">{label}</a></p>'
        headline_cards.append(
            f"""
            <section class="card">
              <h2>{escape(headline.title)}</h2>
              <p>{_paragraph_html(headline.summary)}</p>
              {link}
            </section>
            """
        )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(draft.title)}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: #f6f7f9;
      color: #1f2933;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    .container {{
      max-width: 760px;
      margin: 0 auto;
      padding: 28px 18px;
    }}
    .header {{
      border-bottom: 3px solid #1f2933;
      margin-bottom: 22px;
      padding-bottom: 14px;
    }}
    h1 {{
      font-size: 28px;
      margin: 0 0 4px;
    }}
    .date {{
      color: #64748b;
      margin: 0;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      margin: 16px 0;
      padding: 18px 20px;
    }}
    h2 {{
      font-size: 19px;
      margin: 0 0 10px;
      color: #111827;
    }}
    ul {{
      padding-left: 20px;
      margin: 8px 0 0;
    }}
    li {{
      margin: 8px 0;
    }}
    .source {{
      margin: 12px 0 0;
      font-weight: 600;
    }}
    a {{
      color: #0f5cad;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main class="container">
    <div class="header">
      <h1>{escape(draft.title)}</h1>
      <p class="date">{escape(draft.date)}</p>
    </div>
    {''.join(headline_cards)}
  </main>
</body>
</html>
"""


def _paragraph_html(text: str) -> str:
    return "<br><br>".join(escape(paragraph.strip()) for paragraph in text.split("\n\n") if paragraph.strip())


def _normalize_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("-", "*")):
            bullets.append(f"- {line[1:].strip()}")
        else:
            bullets.append(f"- {line}")
    return bullets


def _paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]


def _source_text(source_title: str | None, source_url: str | None) -> str:
    if source_title and source_url:
        return f" Source: [{source_title}]({source_url})"
    if source_url:
        return f" Source: {source_url}"
    if source_title:
        return f" Source: {source_title}"
    return ""
