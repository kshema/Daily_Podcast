from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import AppConfig
from .runner import DailyPodcastAgent


LOGGER = logging.getLogger(__name__)


def run_daemon(config: AppConfig) -> None:
    agent = DailyPodcastAgent(config)
    scheduler = BlockingScheduler(timezone=config.settings.podcast_timezone)
    trigger = CronTrigger(
        hour=config.settings.podcast_send_hour,
        minute=config.settings.podcast_send_minute,
        timezone=config.settings.podcast_timezone,
    )
    scheduler.add_job(
        agent.run_once,
        trigger=trigger,
        id="daily_podcast",
        name="Daily podcast email",
        replace_existing=True,
        misfire_grace_time=60 * 30,
    )
    LOGGER.info(
        "Daily podcast scheduler started for %02d:%02d %s",
        config.settings.podcast_send_hour,
        config.settings.podcast_send_minute,
        config.settings.podcast_timezone,
    )
    scheduler.start()
