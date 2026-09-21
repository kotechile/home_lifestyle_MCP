"""Periodic background scheduler using APScheduler for continuous feed monitoring."""

import logging
from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import get_config
from app.db import init_db
from app.ingest.feed_crawler import crawl_all_feeds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def job_crawl_all():
    logger.info("Executing scheduled crawl across all Home & Lifestyle feeds...")
    try:
        stats = crawl_all_feeds(max_items_per_feed=10)
        logger.info(f"Scheduled crawl finished: {stats.get('total_articles_ingested', 0)} articles ingested.")
    except Exception as e:
        logger.error(f"Error during scheduled feed crawl: {e}")


def start_scheduler():
    init_db()
    config = get_config()
    sched_cfg = config.get("scheduler", {})
    crawl_hours = sched_cfg.get("crawl_interval_hours", 6)

    scheduler = BlockingScheduler()

    # Initial warm-up crawl on startup
    logger.info("Running initial startup crawl check...")
    try:
        job_crawl_all()
    except Exception as e:
        logger.error(f"Startup crawl error: {e}")

    # Register interval
    scheduler.add_job(job_crawl_all, "interval", hours=crawl_hours, id="job_home_feeds")
    logger.info(f"Scheduler active. Monitoring feeds every {crawl_hours} hours.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler shutting down gracefully.")


if __name__ == "__main__":
    start_scheduler()
