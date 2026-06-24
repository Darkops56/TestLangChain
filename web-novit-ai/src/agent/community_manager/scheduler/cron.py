"""Cron-based scheduler for the agent.

Manages both Community Manager (social media) and Nurturing (newsletter)
scheduled tasks using APScheduler.

CM schedules:
    - Image posts only: 2/week (Monday & Thursday at 10:00 ART)
  - Message check: every 5 minutes

Nurturing schedules:
  - Generate newsletter: 1st Monday of each month at 08:00 ART
  - Check replies: daily at 09:00 ART (business days)
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class AgentScheduler:
    """Manages cron jobs for CM publication + nurturing workflows."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")
        self._publish_callback = None
        self._responder_callback = None
        self._nurturing_generate_callback = None
        self._nurturing_send_callback = None
        self._nurturing_check_replies_callback = None

    def configure(
        self,
        publish_callback=None,
        responder_callback=None,
        nurturing_generate_callback=None,
        nurturing_send_callback=None,
        nurturing_check_replies_callback=None,
    ) -> None:
        """Register callbacks and set up cron triggers."""
        self._publish_callback = publish_callback
        self._responder_callback = responder_callback
        self._nurturing_generate_callback = nurturing_generate_callback
        self._nurturing_send_callback = nurturing_send_callback
        self._nurturing_check_replies_callback = nurturing_check_replies_callback

        # ══════════════════════════════════════════════════════
        #  COMMUNITY MANAGER — Social media schedules
        # ══════════════════════════════════════════════════════

        # Image posts only: Monday & Thursday at 10:00
        if self._publish_callback:
            self._scheduler.add_job(
                self._trigger_image_post,
                CronTrigger(day_of_week="mon,thu", hour=10, minute=0),
                id="cm_image_post",
                name="CM: Image Post (2/week)",
                replace_existing=True,
            )

        # Message responder: every minute
        if self._responder_callback:
            self._scheduler.add_job(
                self._trigger_responder,
                CronTrigger(minute="*"),
                id="cm_responder",
                name="CM: Message Responder",
                replace_existing=True,
            )

        # ══════════════════════════════════════════════════════
        #  NURTURING — Newsletter schedules
        # ══════════════════════════════════════════════════════

        # Generate newsletter: Monday before last Wednesday, at 08:00
        # We use day=1-31 + day_of_week=mon and let the callback check
        # if it's the right Monday (Monday before last Wed of the month).
        if self._nurturing_generate_callback:
            self._scheduler.add_job(
                self._trigger_nurturing_generate,
                CronTrigger(day_of_week="mon", hour=8, minute=0),
                id="nurturing_generate",
                name="Nurturing: Generate Newsletter (monthly)",
                replace_existing=True,
            )

        # Send newsletter: last Wednesday of each month at 10:00
        # We schedule every Wednesday and let the callback check if
        # it's the last Wednesday.
        if self._nurturing_send_callback:
            self._scheduler.add_job(
                self._trigger_nurturing_send,
                CronTrigger(day_of_week="wed", hour=10, minute=0),
                id="nurturing_send",
                name="Nurturing: Send Newsletter (last Wed)",
                replace_existing=True,
            )

        # Check replies: every business day at 09:00
        if self._nurturing_check_replies_callback:
            self._scheduler.add_job(
                self._trigger_nurturing_check_replies,
                CronTrigger(day_of_week="mon-fri", hour=9, minute=0),
                id="nurturing_check_replies",
                name="Nurturing: Check Replies (daily)",
                replace_existing=True,
            )

        logger.info("Scheduler configured with %d jobs", len(self._scheduler.get_jobs()))

    # ── CM triggers ────────────────────────────────────────────

    async def _trigger_image_post(self) -> None:
        logger.info("⏰ CRON: Triggering image_post workflow")
        if self._publish_callback:
            await self._publish_callback("image_post")

    async def _trigger_responder(self) -> None:
        logger.debug("⏰ CRON: Checking for pending messages")
        if self._responder_callback:
            await self._responder_callback()

    # ── Nurturing triggers ─────────────────────────────────────

    async def _trigger_nurturing_generate(self) -> None:
        logger.info("⏰ CRON: Triggering nurturing newsletter generation")
        if self._nurturing_generate_callback:
            await self._nurturing_generate_callback()

    async def _trigger_nurturing_send(self) -> None:
        logger.info("⏰ CRON: Triggering nurturing newsletter send")
        if self._nurturing_send_callback:
            await self._nurturing_send_callback()

    async def _trigger_nurturing_check_replies(self) -> None:
        logger.info("⏰ CRON: Checking nurturing email replies")
        if self._nurturing_check_replies_callback:
            await self._nurturing_check_replies_callback()

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler."""
        self._scheduler.start()
        jobs = self._scheduler.get_jobs()
        logger.info("🗓️  Scheduler started with %d jobs:", len(jobs))
        for job in jobs:
            logger.info("   • %s → next run: %s", job.name, job.next_run_time)

    def shutdown(self) -> None:
        """Gracefully shut down the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
