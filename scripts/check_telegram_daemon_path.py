"""Safe Telegram diagnostic for the TRADE_ORACLE daemon path.

This script verifies the production Telegram path without starting a scan cycle
or touching broker execution. It can:
- validate bot auth with getMe
- send a harmless test message
- run one callback-only long poll
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def _run(*, env_file: str, send_message: bool, poll_once: bool) -> dict:
    load_dotenv(REPO_ROOT / env_file, override=True)

    import httpx

    from ai.trade_oracle_daemon import HttpxTelegramBotClient
    from config import settings

    token = (settings.TRADE_ORACLE_TELEGRAM_BOT_TOKEN or "").strip()
    chat_id = (settings.TRADE_ORACLE_TELEGRAM_CHAT_ID or "").strip()
    if not token:
        raise SystemExit("Missing TRADE_ORACLE_TELEGRAM_BOT_TOKEN.")
    if send_message and not chat_id:
        raise SystemExit("Missing TRADE_ORACLE_TELEGRAM_CHAT_ID.")

    client = HttpxTelegramBotClient(token, timeout_seconds=5)
    try:
        response = await client.client.get("getMe")
        response.raise_for_status()
        me_payload = response.json()
        bot_result = dict(me_payload.get("result", {})) if isinstance(me_payload, dict) else {}

        sent_message_id = ""
        if send_message:
            sent_message_id = await client.send_message(
                chat_id=chat_id,
                text="TRADE_ORACLE Telegram diagnostic: bot auth and outbound messaging are working.",
            )

        polled_updates = 0
        max_update_id = None
        if poll_once:
            updates = await client.fetch_updates(offset=None, timeout=1)
            polled_updates = len(updates)
            update_ids = [
                int(item.get("update_id", 0) or 0)
                for item in updates
                if isinstance(item, dict)
            ]
            max_update_id = max(update_ids) if update_ids else None

        return {
            "bot_ok": True,
            "bot_username": str(bot_result.get("username", "")),
            "bot_id": int(bot_result.get("id", 0) or 0),
            "chat_id_present": bool(chat_id),
            "message_sent": bool(sent_message_id),
            "sent_message_id": sent_message_id,
            "callback_poll_ran": poll_once,
            "callback_update_count": polled_updates,
            "max_callback_update_id": max_update_id,
        }
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the TRADE_ORACLE Telegram long-polling bot path safely.")
    parser.add_argument("--env-file", default=".env.n8n.local", help="Env file to load before the check.")
    parser.add_argument("--send-message", action="store_true", help="Send a harmless diagnostic message to the configured chat.")
    parser.add_argument("--poll-once", action="store_true", help="Run one callback-query-only long poll.")
    args = parser.parse_args()

    print(json.dumps(asyncio.run(_run(env_file=args.env_file, send_message=args.send_message, poll_once=args.poll_once)), indent=2))


if __name__ == "__main__":
    main()
