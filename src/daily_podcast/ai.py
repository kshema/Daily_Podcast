from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from .config import PodcastConfig, Subject
from .llm import LLMClient


@dataclass(frozen=True)
class Headline:
    title: str
    summary: str
    source_title: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class PodcastDraft:
    title: str
    date: str
    headlines: list[Headline]
    script: str
    email_summary: str
    sections: list[dict[str, str | list[str]]] = field(default_factory=list)


class PodcastWriter:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def create_draft(self, podcast: PodcastConfig, subjects: list[Subject]) -> PodcastDraft:
        prompt = self._build_prompt(podcast, subjects)
        payload = _parse_json(self.llm.generate_with_web_search(prompt))
        return PodcastDraft(
            title=payload["title"],
            date=payload.get("date", date.today().isoformat()),
            headlines=[
                Headline(
                    title=item["title"],
                    summary=item["summary"],
                    source_title=item.get("source_title"),
                    source_url=item.get("source_url"),
                )
                for item in payload["headlines"]
            ],
            script=payload["script"],
            email_summary=payload["email_summary"],
            sections=payload.get("sections", []),
        )

    @staticmethod
    def _build_prompt(podcast: PodcastConfig, subjects: list[Subject]) -> str:
        subject_lines = "\n".join(
            f"- {s.name} | priority={s.priority} | focus={s.focus or 'latest important developments'}"
            for s in subjects
        )
        target_words = podcast.duration_minutes * 130
        return f"""
Create a personalized daily news email digest for today.

Digest title: {podcast.title}
Audience: {podcast.audience}
Tone: {podcast.tone}
Target length: roughly {target_words} spoken words if read aloud.

Subjects:
{subject_lines}

Use web search for current, credible headlines. Favor primary sources, reputable journalism,
official releases, and recent dates. Avoid filler and avoid sensationalism.

Optimize for a readable email digest:
- Make the brief skimmable in an email inbox.
- Separate what happened, why it matters, and what to watch next.
- Use concrete facts, dates, names, and numbers when they are available.
- For every headline, write a 3-4 sentence brief that can stand alone under the heading.
- Keep the script conversational, but organize it into clear sections for optional later audio.
- End with a practical bottom line that connects the subjects.
- For high-priority regional subjects such as US, India, and Kerala, first include the biggest public headline for that region before narrowing to personal relevance.
- Do not let markets, technology, or lifestyle items crowd out major government, foreign-policy, security, or disaster news.

Return only valid JSON with this exact shape:
{{
  "title": "string",
  "date": "YYYY-MM-DD",
  "headlines": [
    {{
      "title": "string",
      "summary": "3-4 concise sentences: what happened, why it matters, what to watch next, and any practical impact",
      "source_title": "string",
      "source_url": "https://..."
    }}
  ],
  "email_summary": "short HTML-safe plain text summary, 5-8 bullets using hyphens; include why it matters or what to watch",
  "sections": [
    {{
      "title": "Opening | Artificial intelligence | Markets | Health and longevity | Bottom line",
      "key_points": ["short skimmable point", "short skimmable point"],
      "script": "spoken narration for this section"
    }}
  ],
  "script": "full podcast narration script, ready for text-to-speech"
}}
""".strip()


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])
