"""Pipedrive service for nurturing operations.

Ported from PipedriveService.cs (nurturing-relevant methods only).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from community_manager.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PipedriveDealContact:
    deal_id: int
    deal_title: str
    contact_name: str | None
    contact_email: str | None
    organization_name: str | None


class PipedriveService:
    """Pipedrive CRM client for nurturing operations."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._stage_cache: dict[str, int] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.pipedrive_key and self.settings.pipedrive_base_url)

    @property
    def _base_url(self) -> str:
        return self.settings.pipedrive_base_url.rstrip("/")

    @property
    def _api_token(self) -> str:
        return self.settings.pipedrive_key

    async def get_nurturing_deal_contacts(self) -> list[PipedriveDealContact]:
        """Get all deals in "Nurturing Automático" stage with contact emails."""
        if not self.is_configured:
            logger.warning("Pipedrive not configured")
            return []

        try:
            stage_id = await self._get_stage_id_by_name("Nurturing Automático")
            if not stage_id:
                logger.warning("Stage 'Nurturing Automático' not found")
                return []

            contacts = []
            start = 0
            limit = 100

            async with httpx.AsyncClient(timeout=30.0) as client:
                while True:
                    resp = await client.get(
                        f"{self._base_url}/api/v1/deals",
                        params={
                            "api_token": self._api_token,
                            "stage_id": stage_id,
                            "status": "all_not_deleted",
                            "start": start,
                            "limit": limit,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    deals = data.get("data") or []
                    for deal in deals:
                        contact = self._extract_deal_contact(deal)
                        if contact:
                            contacts.append(contact)

                    # Check pagination
                    pagination = data.get("additional_data", {}).get("pagination", {})
                    if not pagination.get("more_items_in_collection"):
                        break

                    start = pagination.get("next_start", start + limit)

            logger.info("Found %d nurturing deal contacts", len(contacts))
            return contacts

        except Exception:
            logger.exception("Failed to get nurturing deal contacts")
            return []

    async def get_deal_contact(self, deal_id: int) -> PipedriveDealContact | None:
        """Get a single deal contact by ID."""
        if not self.is_configured:
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/deals/{deal_id}",
                    params={"api_token": self._api_token},
                )
                resp.raise_for_status()
                data = resp.json()

                deal = data.get("data")
                if not deal:
                    return None

                return self._extract_deal_contact(deal)

        except Exception:
            logger.exception("Failed to get deal contact %d", deal_id)
            return None

    async def get_deal_notes(self, deal_id: int) -> list[str]:
        """Get notes for a deal (for AI personalization)."""
        if not self.is_configured:
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/notes",
                    params={
                        "api_token": self._api_token,
                        "deal_id": deal_id,
                        "sort": "add_time DESC",
                        "limit": 10,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                notes = []
                for note in (data.get("data") or []):
                    content = note.get("content") or ""
                    if content:
                        # Strip HTML and truncate
                        import re
                        text = re.sub(r"<[^>]+>", " ", content)
                        text = re.sub(r"\s+", " ", text).strip()
                        if len(text) > 500:
                            text = text[:500] + "..."
                        add_time = note.get("add_time", "")[:10]
                        notes.append(f"[{add_time}] {text}")

                return notes

        except Exception:
            logger.exception("Failed to get deal notes %d", deal_id)
            return []

    async def add_note_to_deal(self, deal_id: int, content: str) -> bool:
        """Add a note to a deal."""
        if not self.is_configured:
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/notes",
                    params={"api_token": self._api_token},
                    json={
                        "deal_id": deal_id,
                        "content": content,
                    },
                )
                resp.raise_for_status()
                return True

        except Exception:
            logger.exception("Failed to add note to deal %d", deal_id)
            return False

    def _extract_deal_contact(self, deal: dict) -> PipedriveDealContact | None:
        """Extract contact info from a deal object."""
        deal_id = deal.get("id")
        deal_title = deal.get("title", "")

        # Extract person info
        person = deal.get("person_id")
        contact_name = None
        contact_email = None

        if isinstance(person, dict):
            contact_name = person.get("name")
            # Extract email from person
            emails = person.get("email") or []
            if isinstance(emails, list) and emails:
                contact_email = emails[0].get("value") if isinstance(emails[0], dict) else emails[0]

        # Extract organization
        org = deal.get("org_id")
        org_name = None
        if isinstance(org, dict):
            org_name = org.get("name")

        if not contact_email:
            return None

        return PipedriveDealContact(
            deal_id=deal_id,
            deal_title=deal_title,
            contact_name=contact_name,
            contact_email=contact_email,
            organization_name=org_name,
        )

    async def _get_stage_id_by_name(self, stage_name: str) -> int | None:
        """Get stage ID by name (cached)."""
        if stage_name in self._stage_cache:
            return self._stage_cache[stage_name]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/stages",
                    params={"api_token": self._api_token},
                )
                resp.raise_for_status()
                data = resp.json()

                for stage in (data.get("data") or []):
                    name = stage.get("name", "")
                    stage_id = stage.get("id")
                    if name and stage_id:
                        self._stage_cache[name] = stage_id

            return self._stage_cache.get(stage_name)

        except Exception:
            logger.exception("Failed to load Pipedrive stages")
            return None
