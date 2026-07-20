from __future__ import annotations

import logging
import time

from prometheus_client import start_http_server

from backend.core.config import get_settings
from backend.services.risk_cases import scan_and_escalate_overdue
from database.database import SyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mental_health.sla")


def main() -> None:
    start_http_server(9101)
    interval = max(10, get_settings().risk_sla_scan_seconds)
    logger.info("Risk SLA worker started interval=%ss", interval)
    while True:
        try:
            with SyncSessionLocal() as db:
                escalated = scan_and_escalate_overdue(db)
            if escalated:
                logger.warning("Escalated %s overdue risk cases", escalated)
        except Exception:
            logger.exception("SLA scan failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
