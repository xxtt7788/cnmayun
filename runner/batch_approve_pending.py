#!/usr/bin/env python3
"""
批量放行待审核事件和review queue。

1. review_required 事件 → published
2. pending review_queue → approved

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env file directly (sudo source may not propagate)
ENV_PATH = "/etc/china-succession/china-succession.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.startswith("export "):
                    key = key[7:]
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value

from app.db import session_scope
from sqlalchemy import text


def main():
    with session_scope() as db:
        # 1. review_required events → published
        result = db.execute(
            text("UPDATE events SET event_status='published', published_at=NOW() WHERE event_status='review_required'")
        )
        events_updated = result.rowcount

        # 2. pending review_queue → approved
        result2 = db.execute(
            text("UPDATE review_queue SET status='approved', resolution_notes='Batch approved pre-launch', resolved_at=NOW() WHERE status='pending'")
        )
        reviews_updated = result2.rowcount

        db.commit()

    print(f"Events updated (review_required→published): {events_updated}")
    print(f"Reviews updated (pending→approved): {reviews_updated}")


if __name__ == "__main__":
    main()
