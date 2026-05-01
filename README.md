# Daily News Digest Agent

Python scaffold for a configurable morning news digest:

1. Uses an LLM as the agent brain for research, planning, and writing.
2. Researches current headlines for your configured subjects with OpenAI Responses and web search.
3. Writes a readable email digest with a heading, 3-4 sentence brief, and source link for each story.
4. Writes Markdown and HTML artifacts for review or attachment.
5. Optionally generates audio with ElevenLabs or the built-in macOS `say` voice.
6. Optionally sends the formatted digest through the Gmail API.
7. Can run once or stay alive and send every morning at 5:00 AM.

## Project Layout

```text
config/
  subjects.example.yaml
src/daily_podcast/
  ai.py          # Digest-specific prompting and draft parsing
  cli.py         # Command line entry point
  config.py      # YAML and environment configuration
  gmailer.py     # Gmail OAuth and sending
  llm.py         # LLM provider interface and OpenAI implementation
  runner.py      # End-to-end orchestration
  scheduler.py   # 5:00 AM scheduler
  tts.py         # ElevenLabs and macOS audio generation
.env.example
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
cp config/subjects.example.yaml config/subjects.yaml
```

Edit `.env` with your API keys and Gmail paths. Edit `config/subjects.yaml` with your preferred topics.

For Gmail, create OAuth credentials in Google Cloud with the Gmail API enabled, download the OAuth client JSON, and set `GMAIL_CREDENTIALS_FILE` to that path. On first run, the app opens the OAuth flow and stores `token.json`.

## Run Once

```bash
daily-podcast run
```

## Run Every Morning At 5:00 AM

```bash
daily-podcast daemon
```

For a more reliable production setup, run the `run` command from cron, launchd, systemd, or a cloud scheduler instead of keeping a terminal process alive.

## Notes

- `LLM_PROVIDER=openai` selects the OpenAI-backed LLM implementation.
- Default OpenAI model is configurable with `OPENAI_MODEL`.
- `TTS_PROVIDER=elevenlabs` uses ElevenLabs and writes `podcast.mp3` by default.
- `TTS_PROVIDER=macos` uses the built-in macOS `say` command for free local audio.
- For macOS audio, set `AUDIO_OUTPUT_FILE=podcast.m4a`. macOS built-in tools reliably create M4A/AIFF; MP3 output needs `ffmpeg` installed.
- Default ElevenLabs voice is configurable with `ELEVENLABS_VOICE_ID`.
- Default macOS voice and speaking rate are configurable with `MACOS_TTS_VOICE` and `MACOS_TTS_RATE`.
- The agent always reads topics from `config/subjects.yaml`.
- The agent writes generated artifacts under `output/YYYY-MM-DD/`, including `summary.md`, `summary.html`, `script.md`, and `draft.json`.
- `ENABLE_AUDIO=false` skips ElevenLabs audio generation.
- `ENABLE_EMAIL=true` sends a formatted HTML email with `summary.html` and `summary.md` attached.
- `ENABLE_AUDIO=true` optionally adds an audio attachment, but email delivery no longer requires audio.
- Gmail supports HTML formatting well for headings, spacing, links, and simple cards. For a richer attachment, `summary.html` is the best default because it opens cleanly in a browser; `summary.md` is also attached for easy editing.

## Agent Architecture

```text
DailyPodcastAgent
  -> LLMClient researches subjects and writes the digest
  -> GmailSender emails formatted HTML plus summary attachments
  -> Optional TTS provider turns the script into an audio file
```

The agent interface is intentionally small: `LLMClient.generate_with_web_search(prompt)`.
That keeps OpenAI as the default while leaving room to add Anthropic, Gemini, local models,
or a LangChain/LlamaIndex-style planner later.
