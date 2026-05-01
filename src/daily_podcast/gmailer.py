from __future__ import annotations

import base64
import mimetypes
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailSender:
    def __init__(self, credentials_file: Path, token_file: Path, sender: str) -> None:
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.sender = sender

    def send(
        self,
        to: str,
        subject: str,
        body_text: str,
        attachment_paths: list[Path] | None = None,
        body_html: str | None = None,
    ) -> str:
        service = build("gmail", "v1", credentials=self._credentials())
        message = EmailMessage()
        message["To"] = to
        message["From"] = self.sender
        message["Subject"] = subject
        message.set_content(body_text)

        if body_html:
            message.add_alternative(body_html, subtype="html")

        for attachment_path in attachment_paths or []:
            content_type = mimetypes.guess_type(attachment_path.name)[0] or "application/octet-stream"
            maintype, subtype = content_type.split("/", 1)
            message.add_attachment(
                attachment_path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=attachment_path.name,
            )

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": encoded_message})
            .execute()
        )
        return result["id"]

    def _credentials(self) -> Credentials:
        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), GMAIL_SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_file), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)

        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds
