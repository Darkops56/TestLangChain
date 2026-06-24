"""Nurturing mail service - IMAP/SMTP email operations.

Ported from NurturingMailService.cs.
"""

from __future__ import annotations

import email
import email.mime.multipart
import email.mime.text
import html
import imaplib
import logging
import re
import smtplib
from dataclasses import dataclass
from email.header import decode_header
from email.utils import parseaddr

from community_manager.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class IncomingEmail:
    message_id: str
    from_address: str
    subject: str
    body: str


class NurturingMailService:
    """IMAP/SMTP email service for nurturing operations."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.nurturing_imap_host
            and self.settings.nurturing_smtp_host
            and self.settings.nurturing_login_email
            and self.settings.nurturing_email_password
        )

    async def get_unanswered_replies(self, days: int = 30) -> list[IncomingEmail]:
        """Get unanswered email replies from the last N days."""
        if not self.is_configured:
            logger.warning("Mail service not configured")
            return []

        try:
            import asyncio
            return await asyncio.to_thread(self._get_unanswered_replies_sync, days)
        except Exception:
            logger.exception("Failed to get unanswered replies")
            return []

    def _get_unanswered_replies_sync(self, days: int) -> list[IncomingEmail]:
        """Synchronous IMAP implementation."""
        imap = imaplib.IMAP4_SSL(
            self.settings.nurturing_imap_host,
            self.settings.nurturing_imap_port or 993,
        )
        try:
            imap.login(
                self.settings.nurturing_login_email,
                self.settings.nurturing_email_password,
            )

            # Get sent message IDs from Sent folder
            sent_message_ids = set()
            answered_message_ids = set()

            try:
                imap.select('"[Gmail]/Sent Mail"', readonly=True)
                status, messages = imap.search(None, "ALL")
                if status == "OK":
                    for msg_num in messages[0].split():
                        status, msg_data = imap.fetch(msg_num, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
                        if status == "OK" and msg_data[0]:
                            msg_id = self._extract_header_value(msg_data[0][1], "Message-ID")
                            if msg_id:
                                sent_message_ids.add(msg_id)

                        # Check for In-Reply-To (our replies)
                        status, msg_data = imap.fetch(msg_num, "(BODY[HEADER.FIELDS (IN-REPLY-TO)])")
                        if status == "OK" and msg_data[0]:
                            in_reply_to = self._extract_header_value(msg_data[0][1], "In-Reply-To")
                            if in_reply_to:
                                answered_message_ids.add(in_reply_to)
            except Exception:
                logger.warning("Could not read Sent folder", exc_info=True)

            # Search inbox for recent messages
            imap.select("INBOX", readonly=True)
            status, messages = imap.search(None, f'(SINCE "{self._days_ago(days)}")')

            if status != "OK":
                return []

            replies = []
            login_email = self.settings.nurturing_login_email.lower()
            sender_email = (self.settings.nurturing_sender_email or self.settings.nurturing_login_email).lower()

            for msg_num in messages[0].split():
                status, msg_data = imap.fetch(msg_num, "(RFC822)")
                if status != "OK":
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                from_addr = parseaddr(msg.get("From", ""))[1].lower()

                # Skip messages from ourselves
                if from_addr == login_email or from_addr == sender_email:
                    continue

                msg_id = msg.get("Message-ID", "")

                # Check if we already answered this
                if msg_id in answered_message_ids:
                    continue

                # Check if this is a reply to something we sent
                in_reply_to = msg.get("In-Reply-To", "")
                references = msg.get("References", "")
                is_reply_to_us = False

                for sent_id in sent_message_ids:
                    if sent_id in in_reply_to or sent_id in references:
                        is_reply_to_us = True
                        break

                if not is_reply_to_us:
                    continue

                # Extract body
                body = self._extract_body(msg)
                subject = self._decode_subject(msg.get("Subject", ""))

                replies.append(IncomingEmail(
                    message_id=msg_id,
                    from_address=from_addr,
                    subject=subject,
                    body=body,
                ))

            return replies

        finally:
            try:
                imap.logout()
            except Exception:
                pass

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        is_html: bool = False,
    ) -> None:
        """Send a single email."""
        if not self.is_configured:
            logger.warning("Mail service not configured")
            return

        import asyncio
        await asyncio.to_thread(self._send_email_sync, to, subject, body, is_html)

    def _send_email_sync(self, to: str, subject: str, body: str, is_html: bool) -> None:
        """Synchronous SMTP implementation."""
        sender_email = self.settings.nurturing_sender_email or self.settings.nurturing_login_email
        sender_name = self.settings.nurturing_sender_name or "Nicolas Piccardo"

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = to
        msg["Subject"] = subject

        if is_html:
            # Add plain text alternative
            plain_text = self._html_to_plain_text(body)
            msg.attach(email.mime.text.MIMEText(plain_text, "plain", "utf-8"))
            msg.attach(email.mime.text.MIMEText(body, "html", "utf-8"))
        else:
            msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(self.settings.nurturing_smtp_host, self.settings.nurturing_smtp_port or 587) as server:
            server.starttls()
            server.login(self.settings.nurturing_login_email, self.settings.nurturing_email_password)
            server.send_message(msg)

    async def send_reply(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str,
    ) -> None:
        """Send a reply to an existing email thread."""
        if not self.is_configured:
            return

        # Add Re: prefix if not already present
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        import asyncio
        await asyncio.to_thread(self._send_reply_sync, to, subject, body, in_reply_to)

    def _send_reply_sync(self, to: str, subject: str, body: str, in_reply_to: str) -> None:
        """Synchronous SMTP reply implementation."""
        sender_email = self.settings.nurturing_sender_email or self.settings.nurturing_login_email
        sender_name = self.settings.nurturing_sender_name or "Nicolas Piccardo"

        msg = email.mime.text.MIMEText(body, "plain", "utf-8")
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

        with smtplib.SMTP(self.settings.nurturing_smtp_host, self.settings.nurturing_smtp_port or 587) as server:
            server.starttls()
            server.login(self.settings.nurturing_login_email, self.settings.nurturing_email_password)
            server.send_message(msg)

    async def mark_as_read(self, message_ids: list[str]) -> None:
        """Mark messages as read and move to Nurturing folder."""
        if not self.is_configured or not message_ids:
            return

        import asyncio
        await asyncio.to_thread(self._mark_as_read_sync, message_ids)

    def _mark_as_read_sync(self, message_ids: list[str]) -> None:
        """Synchronous IMAP mark as read."""
        imap = imaplib.IMAP4_SSL(
            self.settings.nurturing_imap_host,
            self.settings.nurturing_imap_port or 993,
        )
        try:
            imap.login(self.settings.nurturing_login_email, self.settings.nurturing_email_password)
            imap.select("INBOX")

            for msg_id in message_ids:
                status, messages = imap.search(None, f'(HEADER Message-ID "{msg_id}")')
                if status == "OK" and messages[0]:
                    for msg_num in messages[0].split():
                        imap.store(msg_num, "+FLAGS", "\\Seen")
                        # Try to move to Nurturing folder
                        try:
                            imap.copy(msg_num, "Nurturing")
                            imap.store(msg_num, "+FLAGS", "\\Deleted")
                        except Exception:
                            logger.warning("Could not move message to Nurturing folder")

            imap.expunge()
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    def _extract_header_value(self, header_bytes: bytes, header_name: str) -> str | None:
        """Extract a header value from raw header bytes."""
        try:
            text = header_bytes.decode("utf-8", errors="replace")
            for line in text.split("\n"):
                if line.lower().startswith(header_name.lower() + ":"):
                    return line.split(":", 1)[1].strip().strip("<>")
        except Exception:
            pass
        return None

    def _extract_body(self, msg: email.message.Message) -> str:
        """Extract text body from an email message."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="replace")
        return ""

    def _decode_subject(self, subject: str) -> str:
        """Decode encoded email subject."""
        try:
            decoded_parts = decode_header(subject)
            parts = []
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    parts.append(part.decode(charset or "utf-8", errors="replace"))
                else:
                    parts.append(part)
            return " ".join(parts)
        except Exception:
            return subject

    def _days_ago(self, days: int) -> str:
        """Get date string for N days ago (IMAP format)."""
        from datetime import datetime, timedelta
        d = datetime.now() - timedelta(days=days)
        return d.strftime("%d-%b-%Y")

    def _html_to_plain_text(self, html_body: str) -> str:
        """Convert HTML to plain text for multipart/alternative."""
        if not html_body:
            return ""

        text = html_body
        # Convert common HTML elements to plain text
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</(p|div|tr)>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()
