"""Single-runtime TRADE_ORACLE daemon for forward testing and Telegram review polling."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from config import settings
from execution.runtime import build_execution_client_from_settings, resolve_execution_backend
from risk.manager import RiskManager

from .langgraph_orchestrator import (
    LangGraphEvaluationResult,
    LangGraphExecutionCandidate,
    LangGraphSupervisorOrchestrator,
    resolve_live_take_profit,
)
from .shadow_mode import (
    SHADOW_MODE_ENABLED,
    ShadowCycleResult,
    ShadowModeRunner,
    build_shadow_mode_runner,
)
from .trade_oracle_benchmark import TradeOracleBenchmarkEvent
from .trade_oracle_storage import (
    TradeOracleBenchmarkStoreProtocol,
    TradeOracleRuntimeStateStoreProtocol,
    build_trade_oracle_benchmark_store,
    build_trade_oracle_runtime_state_store,
)

logger = logging.getLogger("TRADE_ORACLE.SingleRuntimeDaemon")

TELEGRAM_UPDATE_OFFSET_CHECKPOINT_KEY = "telegram_update_offset"
OPEN_REVIEW_STATUSES = {"pending", "telegram_sent"}
REPO_ROOT = Path(__file__).resolve().parents[1]


class TradeOracleAccountSnapshot(BaseModel):
    """Resolved account context for one daemon cycle or resume action."""

    model_config = ConfigDict(extra="forbid")

    current_balance: float
    highest_equity: float
    active_trades_count: int = 0
    source: str = ""


class TradeOracleCycleResult(BaseModel):
    """High-level cycle/resume outcome for daemon orchestration."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    cycle_id: str
    outcome: str
    pending_review_count: int = 0
    candidate_count: int = 0
    transmitted: bool = False
    thread_ids: list[str] = Field(default_factory=list)


class TelegramBotClientProtocol(Protocol):
    async def send_review_request(self, *, chat_id: str, text: str, thread_id: str) -> str: ...

    async def send_message(self, *, chat_id: str, text: str) -> str: ...

    async def edit_review_message(self, *, chat_id: str, message_id: str, text: str) -> None: ...

    async def answer_callback_query(self, *, callback_query_id: str, text: str = "") -> None: ...

    async def fetch_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]: ...


async def _default_scanner_runner(watchlist: list[str]) -> list[dict[str, Any]]:
    from data.scanner import MarketScanner

    scanner = MarketScanner(watchlist)
    return await scanner.run_scan()


def _now_run_seed() -> int:
    return int(time.time() * 1000)


def _build_run_id(seed: int | None = None) -> str:
    resolved_seed = seed if seed is not None else _now_run_seed()
    return f"trade_oracle_{resolved_seed}"


def _build_cycle_id(seed: int | None = None) -> str:
    resolved_seed = seed if seed is not None else _now_run_seed()
    return f"cycle_{resolved_seed}"


@dataclass(slots=True)
class _CycleLock:
    path: Path
    fd: int

    def release(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove cycle lock at %s.", self.path)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


def _try_acquire_cycle_lock(path: str | Path, *, stale_seconds: int) -> _CycleLock | None:
    lock_path = Path(path)
    if not lock_path.is_absolute():
        lock_path = REPO_ROOT / lock_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    def _open_lock() -> _CycleLock:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        payload = {
            "pid": os.getpid(),
            "created_at_epoch": time.time(),
            "created_at_monotonic": time.monotonic(),
        }
        os.write(fd, json.dumps(payload).encode("utf-8"))
        return _CycleLock(path=lock_path, fd=fd)

    try:
        return _open_lock()
    except FileExistsError:
        pass

    try:
        existing = json.loads(lock_path.read_text(encoding="utf-8"))
        owner_pid = int(existing.get("pid", 0) or 0)
        created_at_epoch = float(existing.get("created_at_epoch", 0.0) or 0.0)
    except Exception:
        logger.warning("Removing corrupted or unreadable daemon lock at %s.", lock_path)
        try:
            lock_path.unlink(missing_ok=True)
            return _open_lock()
        except Exception:
            return None

    if owner_pid > 0 and not _pid_is_running(owner_pid):
        logger.warning("Removing dead-owner daemon lock at %s (pid=%s).", lock_path, owner_pid)
        try:
            lock_path.unlink(missing_ok=True)
            return _open_lock()
        except FileExistsError:
            return None
        except OSError:
            return None

    if stale_seconds > 0 and (time.time() - created_at_epoch) > stale_seconds:
        logger.warning("Removing stale daemon cycle lock at %s.", lock_path)
        try:
            lock_path.unlink(missing_ok=True)
            return _open_lock()
        except FileExistsError:
            return None
        except OSError:
            return None
    return None


def _reviewer_name(callback_query: dict[str, Any]) -> str:
    actor = callback_query.get("from", {}) if isinstance(callback_query, dict) else {}
    username = str(actor.get("username", "")).strip()
    if username:
        return username
    first_name = str(actor.get("first_name", "")).strip()
    return first_name or "telegram_reviewer"


def _resolve_high_watermark(current_equity: float, *, state_manager_factory: Callable[[], Any] | None) -> tuple[float, str]:
    if state_manager_factory is None:
        try:
            from journal.supabase_client import StateManager as state_manager_factory
        except Exception:
            state_manager_factory = None
    if state_manager_factory is None:
        return current_equity, "fallback_current_equity"
    try:
        state_manager = state_manager_factory()
        return float(state_manager.update_high_watermark(current_equity)), "supabase"
    except Exception:
        return current_equity, "fallback_current_equity"


class HttpxTelegramBotClient:
    """Telegram Bot API client using long polling instead of webhooks."""

    def __init__(self, token: str, *, timeout_seconds: int = 30):
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.request_attempts = max(1, int(settings.TRADE_ORACLE_DAEMON_TELEGRAM_REQUEST_ATTEMPTS))
        self.retry_base_seconds = max(0.25, float(settings.TRADE_ORACLE_DAEMON_TELEGRAM_RETRY_BASE_SECONDS))
        self.client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{token}/",
            timeout=max(10, timeout_seconds + 10),
            trust_env=False,
        )

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            return exc.response.status_code >= 500 or exc.response.status_code == 409
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "getaddrinfo failed",
                "name or service not known",
                "temporary failure in name resolution",
                "connection reset",
                "connection aborted",
                "server disconnected",
            )
        )

    async def _post_json(self, endpoint: str, payload: dict[str, Any], *, swallow_retryable_failure: bool = False) -> Any | None:
        last_exc: Exception | None = None
        for attempt in range(1, self.request_attempts + 1):
            try:
                response = await self.client.post(endpoint, json=payload)
                response.raise_for_status()
                return response
            except Exception as exc:
                last_exc = exc
                if attempt >= self.request_attempts or not self._is_retryable_error(exc):
                    break
                delay_seconds = self.retry_base_seconds * attempt
                logger.warning(
                    "Telegram request retry %s/%s for %s after %s: %s",
                    attempt,
                    self.request_attempts,
                    endpoint,
                    type(exc).__name__,
                    exc,
                )
                await asyncio.sleep(delay_seconds)
        if swallow_retryable_failure and last_exc is not None and self._is_retryable_error(last_exc):
            logger.warning(
                "Telegram request %s exhausted retries after %s attempts; continuing without raising.",
                endpoint,
                self.request_attempts,
            )
            return None
        if last_exc is not None:
            raise last_exc
        return None

    async def send_review_request(self, *, chat_id: str, text: str, thread_id: str) -> str:
        response = await self._post_json(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {"text": "Approve", "callback_data": f"approve:{thread_id}"},
                            {"text": "Reject", "callback_data": f"reject:{thread_id}"},
                        ]
                    ]
                },
            },
        )
        if response is None:
            raise RuntimeError("Telegram send_review_request returned no response.")
        payload = response.json()
        return str(payload.get("result", {}).get("message_id", ""))

    async def send_message(self, *, chat_id: str, text: str) -> str:
        response = await self._post_json(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
        )
        if response is None:
            raise RuntimeError("Telegram send_message returned no response.")
        payload = response.json()
        return str(payload.get("result", {}).get("message_id", ""))

    async def edit_review_message(self, *, chat_id: str, message_id: str, text: str) -> None:
        if not chat_id or not message_id:
            return
        await self._post_json(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": int(message_id),
                "text": text,
                "parse_mode": "Markdown",
            },
        )

    async def answer_callback_query(self, *, callback_query_id: str, text: str = "") -> None:
        if not callback_query_id:
            return
        try:
            await self._post_json(
                "answerCallbackQuery",
                {"callback_query_id": callback_query_id, "text": text},
                swallow_retryable_failure=True,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 400:
                logger.warning(
                    "Ignoring stale or invalid Telegram callback query answer for callback_id=%s.",
                    callback_query_id,
                )
                return
            raise

    async def fetch_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        response = await self._post_json(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": ["callback_query"],
            },
            swallow_retryable_failure=True,
        )
        if response is None:
            return []
        payload = response.json()
        return payload.get("result", []) if isinstance(payload, dict) else []

    async def aclose(self) -> None:
        await self.client.aclose()


@dataclass(slots=True)
class TradeOracleSingleRuntimeDaemon:
    """Forward-testing daemon that replaces n8n orchestration with one Python runtime."""

    runtime_state_store: TradeOracleRuntimeStateStoreProtocol
    benchmark_store: TradeOracleBenchmarkStoreProtocol
    orchestrator: LangGraphSupervisorOrchestrator
    scanner_runner: Callable[[list[str]], Awaitable[list[dict[str, Any]]]]
    execution_client_factory: Callable[[], Any]
    execution_backend: str
    benchmark_variant: str = settings.TRADE_ORACLE_BENCHMARK_VARIANT
    shadow_variant: str = settings.TRADE_ORACLE_SHADOW_BENCHMARK_VARIANT
    shadow_runner: ShadowModeRunner | None = None
    telegram_client: TelegramBotClientProtocol | None = None
    telegram_chat_id: str = settings.TRADE_ORACLE_TELEGRAM_CHAT_ID
    watchlist: list[str] = field(default_factory=list)
    state_manager_factory: Callable[[], Any] | None = None
    cycle_interval_seconds: int = settings.TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS
    telegram_poll_timeout_seconds: int = settings.TRADE_ORACLE_DAEMON_TELEGRAM_POLL_TIMEOUT_SECONDS
    idle_sleep_seconds: float = settings.TRADE_ORACLE_DAEMON_IDLE_SLEEP_SECONDS
    send_cycle_summary: bool = settings.TRADE_ORACLE_DAEMON_SEND_CYCLE_SUMMARY
    telegram_update_offset: int | None = None
    _halted: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not self.watchlist:
            self.watchlist = list(settings.TRADE_ORACLE_DAEMON_WATCHLIST)
        if self.telegram_update_offset is None:
            self.telegram_update_offset = self._load_telegram_update_offset()

    def _load_telegram_update_offset(self) -> int | None:
        try:
            checkpoint = self.runtime_state_store.get_daemon_checkpoint(TELEGRAM_UPDATE_OFFSET_CHECKPOINT_KEY)
        except AttributeError:
            return None
        except Exception:
            logger.exception("Failed to load Telegram update-offset checkpoint.")
            return None
        if checkpoint is None:
            return None
        try:
            offset = int(checkpoint.checkpoint_value.get("offset"))
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid Telegram update-offset checkpoint: %s", checkpoint.checkpoint_value)
            return None
        return offset if offset >= 0 else None

    def _persist_telegram_update_offset(self) -> None:
        if self.telegram_update_offset is None:
            return
        try:
            self.runtime_state_store.upsert_daemon_checkpoint(
                {
                    "checkpoint_key": TELEGRAM_UPDATE_OFFSET_CHECKPOINT_KEY,
                    "checkpoint_value": {"offset": int(self.telegram_update_offset)},
                }
            )
        except AttributeError:
            return
        except Exception:
            logger.exception("Failed to persist Telegram update-offset checkpoint.")

    def _list_open_reviews(self, *, limit: int = 100) -> list[Any]:
        records: list[Any] = []
        seen_thread_ids: set[str] = set()
        for review_status in sorted(OPEN_REVIEW_STATUSES):
            for record in self.runtime_state_store.list_pending_reviews(
                limit=limit,
                review_status=review_status,
            ):
                if record.thread_id in seen_thread_ids:
                    continue
                seen_thread_ids.add(record.thread_id)
                records.append(record)
                if len(records) >= limit:
                    return records
        return records

    def _record_benchmark_event(
        self,
        *,
        event_type: str,
        run_id: str,
        cycle_id: str,
        thread_id: str = "",
        symbol: str = "",
        status: str = "",
        decision: str = "",
        payload: dict[str, Any] | None = None,
    ) -> TradeOracleBenchmarkEvent | None:
        try:
            return self.benchmark_store.record_event(
                event_type=event_type,
                source="single_runtime_daemon",
                cycle_id=cycle_id,
                run_id=run_id,
                thread_id=thread_id,
                symbol=symbol,
                execution_backend=self.execution_backend,
                benchmark_variant=self.benchmark_variant,
                status=status,
                decision=decision,
                payload=payload,
            )
        except Exception:
            logger.exception("Benchmark write failed for %s.", event_type)
            return None

    async def _resolve_account_state(self) -> TradeOracleAccountSnapshot:
        client = None
        try:
            client = self.execution_client_factory()
            authenticated = await client.authenticate()
            if not authenticated:
                raise ValueError(f"{self.execution_backend} authentication failed.")
            platform_details = await client.get_platform_details()
            current_equity = float(platform_details.get("equity", settings.TRADE_ORACLE_CURRENT_BALANCE))
            active_trades = int(platform_details.get("active_trades", settings.TRADE_ORACLE_ACTIVE_TRADES_COUNT))
            high_watermark, source = _resolve_high_watermark(
                current_equity,
                state_manager_factory=self.state_manager_factory,
            )
            return TradeOracleAccountSnapshot(
                current_balance=current_equity,
                highest_equity=high_watermark,
                active_trades_count=active_trades,
                source=source,
            )
        except Exception:
            logger.exception("Falling back to env-backed account state.")
            return TradeOracleAccountSnapshot(
                current_balance=settings.TRADE_ORACLE_CURRENT_BALANCE,
                highest_equity=settings.TRADE_ORACLE_HIGHEST_EQUITY,
                active_trades_count=settings.TRADE_ORACLE_ACTIVE_TRADES_COUNT,
                source="env_fallback",
            )
        finally:
            if client is not None and hasattr(client, "shutdown"):
                try:
                    await client.shutdown()
                except Exception:
                    logger.debug("Execution client shutdown failed during account-state resolve.")

    @staticmethod
    def _top_candidate(evaluations: list[LangGraphEvaluationResult]) -> Any | None:
        candidates = [evaluation.candidate for evaluation in evaluations if evaluation.candidate is not None]
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                int(candidate.execute_trade),
                candidate.confidence,
                float(candidate.position_sizing.get("usd_value", 0.0)),
                candidate.symbol,
            ),
            reverse=True,
        )
        return ranked[0]

    @staticmethod
    def _summary_decision(evaluations: list[LangGraphEvaluationResult]) -> str:
        pending_review_count = sum(1 for evaluation in evaluations if evaluation.status == "pending_review")
        if pending_review_count > 0:
            return "pending_review"
        top_candidate = TradeOracleSingleRuntimeDaemon._top_candidate(evaluations)
        if top_candidate and top_candidate.execute_trade and top_candidate.execution_status == "approved":
            return "approved_candidate_ready"
        if top_candidate is not None:
            return "candidate_ranked"
        return "no_trade"

    async def _send_review_prompt(self, pending_record: dict[str, Any]) -> str:
        if self.telegram_client is None or not self.telegram_chat_id:
            return ""
        use_langgraph = settings.TRADE_ORACLE_USE_LANGGRAPH
        engine_ver = "v2 (LangGraph)" if use_langgraph else "v0 (Deterministic)"
        candidate = pending_record.get("candidate", {})
        text = (
            "🔔 *TRADE_ORACLE Review Required*\n"
            "----------------------------------------\n"
            f"Engine: *{engine_ver}*\n"
            f"Symbol: `{pending_record.get('symbol') or 'n/a'}`\n"
            f"Direction: `{pending_record.get('direction') or 'n/a'}`\n"
            f"Entry Price: `{candidate.get('entry_price', 'n/a')}`\n"
            f"Stop Loss: `{candidate.get('stop_loss', 'n/a')}`\n"
            f"Take Profit: `{candidate.get('take_profit', 'n/a')}`\n"
            f"Size: `{candidate.get('size_tokens', 'n/a')}` tokens\n"
            f"Conviction: `{candidate.get('confidence', 0.0) * 10:.1f}/10`\n"
            f"Rationale: {str(candidate.get('rationale', 'n/a')).replace('_', '\\_')}\n\n"
            f"Cycle ID: `{pending_record.get('cycle_id') or 'n/a'}`\n"
            f"Thread ID: `{pending_record.get('thread_id') or 'n/a'}`"
        )
        return await self.telegram_client.send_review_request(
            chat_id=self.telegram_chat_id,
            text=text,
            thread_id=str(pending_record.get("thread_id", "")),
        )

    async def _send_cycle_summary_message(self, text: str, *, chat_id: str | None = None) -> None:
        logger.info("[Telegram Alert] Sending cycle summary:\n%s", text)
        if self.telegram_client is None or not self.send_cycle_summary:
            return
        resolved_chat_id = chat_id or self.telegram_chat_id
        if not resolved_chat_id:
            return
        await self.telegram_client.send_message(chat_id=resolved_chat_id, text=text)

    @staticmethod
    def _risk_direction(direction: str) -> str:
        return "LONG" if str(direction).upper() in {"BUY", "LONG"} else "SHORT"

    def _position_size_from_candidate(self, *, candidate: Any, raw_setup: dict[str, Any], account_state: TradeOracleAccountSnapshot) -> tuple[bool, dict[str, Any] | None]:
        risk_manager = RiskManager(
            current_balance=account_state.current_balance,
            highest_equity=account_state.highest_equity,
            active_trades_count=account_state.active_trades_count,
        )
        if not risk_manager.can_open_new_trade():
            return False, None

        position_sizing = dict(getattr(candidate, "position_sizing", {}) or {})
        if position_sizing.get("tokens"):
            return True, position_sizing

        atr = float(raw_setup.get("localized_atr", 0.0) or raw_setup.get("atr", 0.0) or 0.0)
        if atr <= 0.0:
            return True, None
        calculated = risk_manager.calculate_position_size(
            entry_price=float(candidate.entry_price),
            atr=atr,
            direction=self._risk_direction(str(candidate.direction)),
        )
        return True, calculated

    async def _transmit_candidate(
        self,
        *,
        run_id: str,
        cycle_id: str,
        thread_id: str,
        candidate: Any,
        position_sizing: dict[str, Any] | None,
    ) -> bool:
        if position_sizing is None:
            return False
        take_profit, _ = resolve_live_take_profit(position_sizing)
        if take_profit <= 0.0:
            take_profit = float(getattr(candidate, "take_profit", 0.0) or 0.0)

        self._record_benchmark_event(
            event_type="order_transmit_attempt",
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=thread_id,
            symbol=str(candidate.symbol),
            status="pending",
            decision="attempt",
            payload={
                "direction": candidate.direction,
                "size": float(position_sizing.get("tokens", getattr(candidate, "size_tokens", 0.0) or 0.0)),
                "size_mode": "units",
                "limit_price": float(position_sizing.get("entry_price", candidate.entry_price)),
                "stop_loss": float(position_sizing.get("stop_loss", candidate.stop_loss)),
                "take_profit": take_profit,
            },
        )

        client = self.execution_client_factory()
        try:
            authenticated = await client.authenticate()
            if not authenticated:
                raise ValueError(f"{self.execution_backend} authentication failed.")
            transmitted = await client.transmit_limit_order(
                symbol=str(candidate.symbol),
                direction=str(candidate.direction),
                size=float(position_sizing.get("tokens", getattr(candidate, "size_tokens", 0.0) or 0.0)),
                size_mode="units",
                limit_price=float(position_sizing.get("entry_price", candidate.entry_price)),
                stop_loss=float(position_sizing.get("stop_loss", candidate.stop_loss)),
                take_profit=float(take_profit),
            )
            self._record_benchmark_event(
                event_type="order_transmit_result",
                run_id=run_id,
                cycle_id=cycle_id,
                thread_id=thread_id,
                symbol=str(candidate.symbol),
                status="ok" if transmitted else "rejected",
                decision="transmitted" if transmitted else "not_transmitted",
                payload={"authenticated": authenticated},
            )
            return bool(transmitted)
        except Exception as exc:
            self._record_benchmark_event(
                event_type="order_transmit_result",
                run_id=run_id,
                cycle_id=cycle_id,
                thread_id=thread_id,
                symbol=str(candidate.symbol),
                status="error",
                decision="exception",
                payload={"error_type": type(exc).__name__, "message": str(exc)},
            )
            raise
        finally:
            if hasattr(client, "shutdown"):
                try:
                    await client.shutdown()
                except Exception:
                    logger.debug("Execution client shutdown failed after transmit.")

    async def _finalize_terminal_outcome(
        self,
        *,
        run_id: str,
        cycle_id: str,
        thread_id: str,
        outcome: str,
        candidate: Any | None,
        direction: str = "",
        pending_review: bool = False,
        transmitted: bool = False,
        summary: dict[str, Any] | None = None,
    ) -> None:
        symbol = str(candidate.symbol) if candidate is not None else ""
        resolved_direction = direction or (str(candidate.direction) if candidate is not None else "")
        self.runtime_state_store.upsert_forward_journal_entry(
            {
                "cycle_id": cycle_id,
                "run_id": run_id,
                "benchmark_variant": self.benchmark_variant,
                "thread_id": thread_id,
                "workflow_name": "TRADE_ORACLE Single Runtime Daemon",
                "stage": outcome,
                "outcome": outcome,
                "symbol": symbol,
                "direction": resolved_direction,
                "pending_review": pending_review,
                "transmit_succeeded": transmitted,
                "benchmark_event_count": len(self.benchmark_store.list_cycle_events(cycle_id, limit=200)),
                "thread_ids": [item.thread_id for item in self._list_open_reviews(limit=100) if item.cycle_id == cycle_id] if pending_review else ([thread_id] if thread_id else []),
                "summary": summary or {},
            }
        )
        self._record_benchmark_event(
            event_type="cycle_summary",
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=thread_id,
            symbol=symbol,
            status="ok",
            decision=outcome,
            payload=summary or {},
        )

        if not pending_review:
            use_langgraph = settings.TRADE_ORACLE_USE_LANGGRAPH
            engine_ver = "v2 (LangGraph Supervisor)" if use_langgraph else "v0 (Deterministic)"
            
            account_state = (summary or {}).get("account_state") or {}
            balance = float(account_state.get("current_balance", settings.TRADE_ORACLE_CURRENT_BALANCE))
            watermark = float(account_state.get("highest_equity", settings.TRADE_ORACLE_HIGHEST_EQUITY))
            active_trades = int(account_state.get("active_trades_count", settings.TRADE_ORACLE_ACTIVE_TRADES_COUNT))
            
            watchlist_lines = []
            scanner_rows_list = (summary or {}).get("scanner_rows") or []
            detected_symbols = {row.get("symbol"): row for row in scanner_rows_list if row.get("symbol")}
            for w_symbol in self.watchlist:
                if w_symbol in detected_symbols:
                    row = detected_symbols[w_symbol]
                    qual = row.get("setup_quality", 0.0)
                    reg = row.get("regime", "")
                    watchlist_lines.append(f"  • {w_symbol}: *{reg}* setup detected (Quality: {qual:.2f})")
                else:
                    watchlist_lines.append(f"  • {w_symbol}: No setup")
            watchlist_str = "\n".join(watchlist_lines)

            # Compile Shadow Mode (v1) status
            shadow_result_dict = (summary or {}).get("shadow_result")
            if shadow_result_dict is not None:
                sh_status = shadow_result_dict.get("status")
                sh_symbol = shadow_result_dict.get("symbol") or "n/a"
                sh_dir = shadow_result_dict.get("direction") or "n/a"
                sh_confidence = shadow_result_dict.get("confidence", 0.0)
                sh_rationale = (shadow_result_dict.get("rationale") or "n/a").replace("_", "\\_")
                sh_model = shadow_result_dict.get("model_used") or "n/a"
                sh_error = str(shadow_result_dict.get("error") or "").replace("_", "\\_") if shadow_result_dict.get("error") else None
                
                if sh_status == "shadow_trade":
                    sh_entry = shadow_result_dict.get("entry_price", 0.0)
                    sh_sl = shadow_result_dict.get("stop_loss", 0.0)
                    sh_tp1 = shadow_result_dict.get("tp1", 0.0)
                    sh_tp2 = shadow_result_dict.get("tp2", 0.0)
                    shadow_status_str = (
                        f"  • Status: `Active (Trade Selected)`\n"
                        f"  • Symbol: `{sh_symbol}`\n"
                        f"  • Direction: `{sh_dir}`\n"
                        f"  • Entry Price: `{sh_entry:.6f}`\n"
                        f"  • Stop Loss: `{sh_sl:.6f}`\n"
                        f"  • TP1: `{sh_tp1:.6f}` | TP2: `{sh_tp2:.6f}`\n"
                        f"  • Conviction: `{sh_confidence * 10:.1f}/10`\n"
                        f"  • Rationale: {sh_rationale}\n"
                        f"  • Model: `{sh_model}`"
                    )
                elif sh_status == "shadow_no_trade":
                    shadow_status_str = (
                        f"  • Status: `Active (PASS)`\n"
                        f"  • Rationale: {sh_rationale}\n"
                        f"  • Model: `{sh_model}`"
                    )
                elif sh_status == "shadow_error":
                    shadow_status_str = (
                        f"  • Status: `Error`\n"
                        f"  • Error Message: `{sh_error}`\n"
                        f"  • Model: `{sh_model}`"
                    )
                elif sh_status == "shadow_disabled":
                    shadow_status_str = "  • Status: `Disabled`"
                elif sh_status == "shadow_no_candidates":
                    shadow_status_str = "  • Status: `Inactive (No setups to evaluate)`"
                else:
                    shadow_status_str = f"  • Status: `{sh_status}`"
            else:
                if "review_action" in (summary or {}):
                    shadow_status_str = "  • Status: `Inactive (Resumed Cycle)`"
                elif not settings.TRADE_ORACLE_SHADOW_MODE_ENABLED:
                    shadow_status_str = "  • Status: `Disabled`"
                elif getattr(self, "shadow_runner", None) is None:
                    shadow_status_str = "  • Status: `Inactive (Missing API Key)`"
                elif not scanner_rows_list:
                    shadow_status_str = "  • Status: `Inactive (No setups to evaluate)`"
                else:
                    shadow_status_str = "  • Status: `Inactive (Bypassed/Unknown)`"

            if candidate is not None:
                pos_sizing = (summary or {}).get("position_sizing") or getattr(candidate, "position_sizing", {}) or {}
                size_tokens = pos_sizing.get("tokens", getattr(candidate, "size_tokens", 0.0))
                usd_val = pos_sizing.get("usd_value", float(size_tokens) * candidate.entry_price if size_tokens else 0.0)
                confidence = getattr(candidate, "confidence", 1.0)
                rationale = (getattr(candidate, "rationale", "") or "n/a").replace("_", "\\_")
                
                candidate_str = (
                    f"  • Symbol: `{candidate.symbol}`\n"
                    f"  • Direction: `{candidate.direction}`\n"
                    f"  • Entry Price: `{candidate.entry_price:.6f}`\n"
                    f"  • Stop Loss: `{candidate.stop_loss:.6f}`\n"
                    f"  • Take Profit: `{candidate.take_profit:.6f}`\n"
                    f"  • Size: `{size_tokens}` tokens (${usd_val:.2f})\n"
                    f"  • Conviction: `{confidence * 10:.1f}/10`\n"
                    f"  • Rationale: {rationale}"
                )
            else:
                candidate_str = "  • None selected"

            cycle_summary_text = (
                "📊 *TRADE_ORACLE Cycle Dashboard*\n"
                "----------------------------------------\n"
                f"Engine: *{engine_ver}*\n"
                f"Cycle ID: `{cycle_id}`\n"
                f"Outcome: `{outcome}`\n\n"
                "💰 *Account State:*\n"
                f"  • Balance: `${balance:.2f}`\n"
                f"  • Peak Watermark: `${watermark:.2f}`\n"
                f"  • Concurrency: `{active_trades}/4` active positions\n\n"
                "🔍 *Watchlist Scan:*\n"
                f"{watchlist_str}\n\n"
                "👤 *Shadow Engine (v1):*\n"
                f"{shadow_status_str}\n\n"
                "🎯 *Selected Candidate:*\n"
                f"{candidate_str}\n\n"
                "⚡ *Execution:*\n"
                f"  • Order Transmitted: `{transmitted}`\n"
                f"  • Run ID: `{run_id}`\n"
                f"  • Thread ID: `{thread_id or 'n/a'}`"
            )
            await self._send_cycle_summary_message(cycle_summary_text)

    def _write_shadow_journal(self, result: ShadowCycleResult, *, run_id: str, cycle_id: str) -> None:
        """
        Persist a shadow LLM decision to the forward journal.
        transmit_succeeded is ALWAYS False — shadow mode never touches MT5.
        """
        try:
            self.runtime_state_store.upsert_forward_journal_entry(
                {
                    "cycle_id": f"{cycle_id}_shadow",
                    "run_id": run_id,
                    "benchmark_variant": self.shadow_variant,
                    "thread_id": "",
                    "workflow_name": "TRADE_ORACLE Shadow Mode v1",
                    "stage": result.status,
                    "outcome": result.status,
                    "symbol": result.symbol,
                    "direction": result.direction,
                    "pending_review": False,
                    "transmit_succeeded": False,  # NEVER True in shadow mode
                    "benchmark_event_count": 1,
                    "thread_ids": [],
                    "summary": {
                        "entry_price": result.entry_price,
                        "stop_loss": result.stop_loss,
                        "tp1": result.tp1,
                        "tp2": result.tp2,
                        "confidence": result.confidence,
                        "rationale": result.rationale,
                        "compliance_proof": result.compliance_proof,
                        "model_used": result.model_used,
                        "latency_ms": result.latency_ms,
                        "shadow_mode": True,
                        "error": result.error,
                    },
                }
            )
            logger.info(
                "[ShadowMode] Journal entry written: %s %s %s (variant=%s)",
                result.status,
                result.direction or "-",
                result.symbol or "-",
                self.shadow_variant,
            )
        except Exception:
            logger.exception("[ShadowMode] Failed to write shadow journal entry — continuing.")

    async def _handle_circuit_breaker_event(self, error: Exception, run_id: str, cycle_id: str) -> None:
        logger.critical("Handling circuit breaker event: %s", error)
        self._halted = True
        
        drawdown_pct = getattr(error, 'current_drawdown_pct', 0.0)
        drawdown_usd = getattr(error, 'current_drawdown_usd', 0.0)
        high_watermark = getattr(error, 'high_watermark', 0.0)

        self._record_benchmark_event(
            event_type="circuit_breaker_triggered",
            run_id=run_id,
            cycle_id=cycle_id,
            status="halted",
            decision="system_halted",
            payload={
                "drawdown_pct": drawdown_pct * 100,
                "drawdown_usd": drawdown_usd,
                "high_watermark": high_watermark,
                "circuit_breaker_limit_pct": 2.5,
                "message": str(error),
            }
        )

        alert_message = (
            f"🚨 *CIRCUIT BREAKER TRIGGERED* 🚨\n\n"
            f"Drawdown: `{drawdown_pct * 100:.3f}%` "
            f"(${drawdown_usd:.2f})\n"
            f"Hard limit: `2.5%`\n"
            f"High watermark: `${high_watermark:.2f}`\n\n"
            f"*All new trade evaluation is HALTED.*\n"
            f"Existing positions remain open.\n\n"
            f"To resume: investigate, then restart daemon manually."
        )
        await self._send_cycle_summary_message(alert_message)

    async def run_cycle_once(self) -> TradeOracleCycleResult:
        cycle_lock = _try_acquire_cycle_lock(
            settings.TRADE_ORACLE_DAEMON_CYCLE_LOCK_PATH,
            stale_seconds=settings.TRADE_ORACLE_DAEMON_CYCLE_LOCK_STALE_SECONDS,
        )
        if cycle_lock is None:
            logger.warning("Skipping cycle because another daemon cycle owns the cycle lock.")
            return TradeOracleCycleResult(
                run_id="",
                cycle_id="",
                outcome="cycle_lock_held",
            )
        try:
            return await self._run_cycle_once_locked_body()
        finally:
            cycle_lock.release()

    async def _run_cycle_once_locked_body(self) -> TradeOracleCycleResult:
        if self._halted:
            logger.critical("Daemon is in HALTED state due to circuit breaker. Manual restart required.")
            return TradeOracleCycleResult(
                run_id="",
                cycle_id="",
                outcome="halted_circuit_breaker",
            )

        open_reviews = self._list_open_reviews(limit=100)
        if open_reviews:
            logger.info("Skipping cycle because %s pending review(s) already exist.", len(open_reviews))
            return TradeOracleCycleResult(
                run_id="",
                cycle_id=open_reviews[0].cycle_id,
                outcome="skipped_pending_review",
                pending_review_count=len(open_reviews),
                thread_ids=[item.thread_id for item in open_reviews],
            )

        seed = _now_run_seed()
        run_id = _build_run_id(seed)
        cycle_id = _build_cycle_id(seed)
        account_state = await self._resolve_account_state()
        shadow_result = None

        # --- CIRCUIT BREAKER CHECK ---
        try:
            risk_manager = RiskManager(
                current_balance=account_state.current_balance,
                highest_equity=account_state.highest_equity,
                active_trades_count=account_state.active_trades_count,
            )
            if hasattr(risk_manager, "check_circuit_breaker"):
                risk_manager.check_circuit_breaker()
        except Exception as e:
            if type(e).__name__ == "CircuitBreakerTriggered":
                await self._handle_circuit_breaker_event(e, run_id=run_id, cycle_id=cycle_id)
                return TradeOracleCycleResult(
                    run_id=run_id,
                    cycle_id=cycle_id,
                    outcome="halted_circuit_breaker",
                )
            else:
                raise

        scanner_rows = await self.scanner_runner(list(self.watchlist))
        scanner_symbols = sorted({str(row.get("symbol", "")).strip() for row in scanner_rows if str(row.get("symbol", "")).strip()})
        self._record_benchmark_event(
            event_type="scanner_cycle",
            run_id=run_id,
            cycle_id=cycle_id,
            status="ok",
            decision="scanner_rows_ready",
            payload={
                "scanner_row_count": len(scanner_rows),
                "scanner_symbols": scanner_symbols,
                "watchlist": list(self.watchlist),
                "account_state_source": account_state.source,
            },
        )

        # -----------------------------------------------------------------------
        # SHADOW MODE BLOCK — live LLM evaluation, NEVER transmits to MT5
        # Runs as a parallel counterfactual immediately after scanner rows are
        # ready so its latency does not block the primary decision path.
        # -----------------------------------------------------------------------
        if self.shadow_runner is not None and scanner_rows:
            try:
                primary_confidence = 0.0  # resolved post-evaluation; we call before primary intentionally
                shadow_result = await self.shadow_runner.run_shadow_cycle(
                    scanner_rows,
                    account_state.model_dump(),
                    run_id=run_id,
                    cycle_id=cycle_id,
                    primary_candidate_confidence=primary_confidence,
                )
                self._write_shadow_journal(shadow_result, run_id=run_id, cycle_id=cycle_id)
                self._record_benchmark_event(
                    event_type="shadow_brain_run",
                    run_id=run_id,
                    cycle_id=cycle_id,
                    symbol=shadow_result.symbol,
                    status=shadow_result.status,
                    decision=shadow_result.status,
                    payload=shadow_result.model_dump(),
                )
                if self.telegram_client is not None and self.telegram_chat_id:
                    msg = (
                        "👤 *Shadow Mode (v1)* Cycle Evaluation\n"
                        f"Status: `{shadow_result.status.replace('_', ' ').title()}`\n"
                        f"Symbol: `{shadow_result.symbol or 'n/a'}`\n"
                        f"Direction: `{shadow_result.direction or 'PASS'}`\n"
                    )
                    if shadow_result.status == "shadow_trade":
                        msg += (
                            f"Entry Price: `{shadow_result.entry_price:.6f}`\n"
                            f"Stop Loss: `{shadow_result.stop_loss:.6f}`\n"
                            f"TP1: `{shadow_result.tp1:.6f}` | TP2: `{shadow_result.tp2:.6f}`\n"
                            f"Conviction: `{shadow_result.confidence * 10:.1f}/10`\n"
                            f"Rationale: {shadow_result.rationale.replace('_', '\\_')}\n"
                        )
                    else:
                        if shadow_result.error:
                            msg += f"Error: `{shadow_result.error.replace('_', '\\_')}`\n"
                        else:
                            msg += f"Rationale: {shadow_result.rationale.replace('_', '\\_') or 'All setups passed/ignored'}\n"
                    msg += f"Model: `{shadow_result.model_used}`"
                    try:
                        await self.telegram_client.send_message(chat_id=self.telegram_chat_id, text=msg)
                    except Exception:
                        logger.exception("[ShadowMode] Failed to send Telegram alert. Message was:\n%s", msg)
            except Exception:
                logger.exception("[ShadowMode] Shadow cycle raised unexpectedly — primary cycle continues.")
        # -----------------------------------------------------------------------
        # END SHADOW MODE BLOCK
        # -----------------------------------------------------------------------

        if settings.TRADE_ORACLE_USE_LANGGRAPH or not isinstance(self.orchestrator, LangGraphSupervisorOrchestrator):
            evaluations = await self.orchestrator.evaluate_batch(
                scanner_rows,
                current_balance=account_state.current_balance,
                highest_equity=account_state.highest_equity,
                active_trades_count=account_state.active_trades_count,
                run_id=run_id,
                event_source="single_runtime_daemon",
            )
        else:
            logger.info("TRADE_ORACLE_USE_LANGGRAPH is False. Routing setups to deterministic v0 engine...")
            evaluations = []
            for scanner_row in scanner_rows:
                symbol = str(scanner_row.get("symbol", ""))
                regime = str(scanner_row.get("regime", ""))
                direction = "BUY" if regime == "BULLISH" else "SELL"
                entry_price = float(scanner_row.get("current_price", 0.0))
                atr = float(scanner_row.get("atr", 0.0))
                
                thread_id = f"det-{symbol.replace('/', '-')}-{cycle_id}"
                
                risk_manager = RiskManager(
                    current_balance=account_state.current_balance,
                    highest_equity=account_state.highest_equity,
                    active_trades_count=account_state.active_trades_count,
                )
                
                position_sizing = risk_manager.calculate_position_size(
                    entry_price=entry_price,
                    atr=atr,
                    direction=self._risk_direction(direction),
                )
                
                if position_sizing is None:
                    logger.info("Deterministic candidate for %s rejected by risk manager.", symbol)
                    execute_trade = False
                    stop_loss = 0.0
                    take_profit = 0.0
                    size_tokens = 0.0
                    position_sizing = {}
                    execution_status = "risk_rejected"
                    execution_tp_mode = "unresolved"
                    status = "no_trade"
                else:
                    execute_trade = True
                    stop_loss = float(position_sizing.get("stop_loss", 0.0))
                    take_profit, execution_tp_mode = resolve_live_take_profit(position_sizing)
                    size_tokens = float(position_sizing.get("tokens", 0.0))
                    execution_status = "approved"
                    status = "completed"
                
                candidate = LangGraphExecutionCandidate(
                    execute_trade=execute_trade,
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    size_tokens=size_tokens,
                    confidence=float(scanner_row.get("setup_quality", 1.0)),
                    execution_status=execution_status,
                    execution_tp_mode=execution_tp_mode,
                    review_required=False,
                    rationale=str(scanner_row.get("rationale", "")),
                    position_sizing=position_sizing,
                    final_decision={
                        "decision": direction if execute_trade else "PASS",
                        "asset_ticker": symbol,
                        "confidence": float(scanner_row.get("setup_quality", 1.0)),
                        "execution_status": execution_status,
                        "entry_context": str(scanner_row.get("rationale", "")),
                        "position_sizing": position_sizing,
                    },
                    raw_setup=scanner_row,
                    thread_id=thread_id,
                )
                
                eval_result = LangGraphEvaluationResult(
                    status=status,
                    thread_id=thread_id,
                    interrupted=False,
                    review_required=False,
                    raw_setup=scanner_row,
                    review_context={},
                    final_decision=candidate.final_decision,
                    gatekeeper_status="pass",
                    audit_trail=["Deterministic bypass of LangGraph supervisor."],
                    tool_results=[],
                    specialist_reports=[],
                    errors=[],
                    thread_metadata={},
                    candidate=candidate,
                )
                evaluations.append(eval_result)
        summary_decision = self._summary_decision(evaluations)
        top_candidate = self._top_candidate(evaluations)
        pending_evaluations = [evaluation for evaluation in evaluations if evaluation.status == "pending_review"]
        self._record_benchmark_event(
            event_type="super_brain_run",
            run_id=run_id,
            cycle_id=cycle_id,
            symbol=str(top_candidate.symbol) if top_candidate is not None else "",
            status="ok",
            decision=summary_decision,
            payload={
                "evaluation_count": len(evaluations),
                "pending_review_count": len(pending_evaluations),
                "candidate_count": len([item for item in evaluations if item.candidate is not None]),
            },
        )

        if pending_evaluations:
            for evaluation in pending_evaluations:
                record = {
                    "thread_id": evaluation.thread_id,
                    "cycle_id": cycle_id,
                    "run_id": run_id,
                    "benchmark_variant": self.benchmark_variant,
                    "review_status": "pending",
                    "review_action": "PENDING",
                    "telegram_chat_id": self.telegram_chat_id,
                    "symbol": evaluation.candidate.symbol if evaluation.candidate is not None else str(evaluation.raw_setup.get("asset_ticker", "")),
                    "direction": evaluation.candidate.direction if evaluation.candidate is not None else "",
                    "candidate": evaluation.candidate.model_dump() if evaluation.candidate is not None else {},
                    "review_context": evaluation.review_context,
                    "account_state": account_state.model_dump(),
                    "review_notes": "Awaiting Telegram review.",
                    "cycle_outcome": "pending_review",
                }
                message_id = await self._send_review_prompt(record)
                if message_id:
                    record["telegram_message_id"] = message_id
                self.runtime_state_store.upsert_pending_review(record)

            await self._finalize_terminal_outcome(
                run_id=run_id,
                cycle_id=cycle_id,
                thread_id=pending_evaluations[0].thread_id,
                outcome="pending_review",
                candidate=top_candidate,
                pending_review=True,
                transmitted=False,
                summary={
                    "pending_review_count": len(pending_evaluations),
                    "thread_ids": [item.thread_id for item in pending_evaluations],
                    "scanner_rows": scanner_rows,
                    "account_state": account_state.model_dump(),
                    "shadow_result": shadow_result.model_dump() if shadow_result is not None else None,
                },
            )
            return TradeOracleCycleResult(
                run_id=run_id,
                cycle_id=cycle_id,
                outcome="pending_review",
                pending_review_count=len(pending_evaluations),
                candidate_count=len([item for item in evaluations if item.candidate is not None]),
                thread_ids=[item.thread_id for item in pending_evaluations],
            )

        if top_candidate is None or not top_candidate.execute_trade or top_candidate.execution_status != "approved":
            await self._finalize_terminal_outcome(
                run_id=run_id,
                cycle_id=cycle_id,
                thread_id="",
                outcome="no_trade",
                candidate=top_candidate,
                summary={
                    "candidate_count": len([item for item in evaluations if item.candidate is not None]),
                    "scanner_rows": scanner_rows,
                    "account_state": account_state.model_dump(),
                    "shadow_result": shadow_result.model_dump() if shadow_result is not None else None,
                },
            )
            return TradeOracleCycleResult(
                run_id=run_id,
                cycle_id=cycle_id,
                outcome="no_trade",
                candidate_count=len([item for item in evaluations if item.candidate is not None]),
            )

        raw_setup = next((item.raw_setup for item in evaluations if item.thread_id == top_candidate.thread_id), {})
        can_open_new_trade, position_sizing = self._position_size_from_candidate(
            candidate=top_candidate,
            raw_setup=raw_setup,
            account_state=account_state,
        )
        self._record_benchmark_event(
            event_type="risk_check",
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=top_candidate.thread_id,
            symbol=top_candidate.symbol,
            status="ok",
            decision="allow" if can_open_new_trade and position_sizing is not None else "deny",
            payload={"position_size_available": position_sizing is not None},
        )
        if not can_open_new_trade or position_sizing is None:
            await self._finalize_terminal_outcome(
                run_id=run_id,
                cycle_id=cycle_id,
                thread_id=top_candidate.thread_id,
                outcome="risk_rejected",
                candidate=top_candidate,
                summary={
                    "reason": "risk_gate_denied",
                    "scanner_rows": scanner_rows,
                    "account_state": account_state.model_dump(),
                    "shadow_result": shadow_result.model_dump() if shadow_result is not None else None,
                },
            )
            return TradeOracleCycleResult(
                run_id=run_id,
                cycle_id=cycle_id,
                outcome="risk_rejected",
                candidate_count=1,
                thread_ids=[top_candidate.thread_id],
            )

        transmitted = await self._transmit_candidate(
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=top_candidate.thread_id,
            candidate=top_candidate,
            position_sizing=position_sizing,
        )
        outcome = "execution_result" if transmitted else "risk_rejected"
        await self._finalize_terminal_outcome(
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=top_candidate.thread_id,
            outcome=outcome,
            candidate=top_candidate,
            transmitted=transmitted,
            summary={
                "position_sizing": position_sizing,
                "scanner_rows": scanner_rows,
                "account_state": account_state.model_dump(),
                "shadow_result": shadow_result.model_dump() if shadow_result is not None else None,
            },
        )
        return TradeOracleCycleResult(
            run_id=run_id,
            cycle_id=cycle_id,
            outcome=outcome,
            candidate_count=1,
            transmitted=transmitted,
            thread_ids=[top_candidate.thread_id],
        )

    async def _handle_resume_result(
        self,
        *,
        thread_id: str,
        run_id: str,
        cycle_id: str,
        account_state: TradeOracleAccountSnapshot,
        evaluation: LangGraphEvaluationResult,
        telegram_chat_id: str,
        telegram_message_id: str,
        reviewer: str,
        review_action: str,
    ) -> TradeOracleCycleResult:
        self._record_benchmark_event(
            event_type="super_brain_resume",
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=thread_id,
            symbol=evaluation.candidate.symbol if evaluation.candidate is not None else "",
            status="ok",
            decision=evaluation.status,
            payload={"review_action": review_action},
        )

        use_langgraph = settings.TRADE_ORACLE_USE_LANGGRAPH
        engine_ver = "v2 (LangGraph)" if use_langgraph else "v0 (Deterministic)"

        candidate = evaluation.candidate
        if candidate is None or not candidate.execute_trade or candidate.execution_status != "approved":
            self.runtime_state_store.resolve_pending_review(
                thread_id,
                review_action=review_action,
                reviewer=reviewer,
                review_notes=f"{review_action} from Telegram runtime daemon.",
                telegram_message_id=telegram_message_id,
                cycle_outcome="no_trade",
            )
            await self._finalize_terminal_outcome(
                run_id=run_id,
                cycle_id=cycle_id,
                thread_id=thread_id,
                outcome="no_trade",
                candidate=candidate,
                summary={
                    "review_action": review_action,
                    "scanner_rows": [evaluation.raw_setup] if evaluation.raw_setup else [],
                    "account_state": account_state.model_dump(),
                },
            )
            if self.telegram_client is not None and telegram_chat_id and telegram_message_id:
                await self.telegram_client.edit_review_message(
                    chat_id=telegram_chat_id,
                    message_id=telegram_message_id,
                    text=(
                        "✅ *TRADE_ORACLE Review Resolved*\n"
                        "----------------------------------------\n"
                        f"Engine: *{engine_ver}*\n"
                        f"Action: *{review_action}*\n"
                        "Outcome: `no_trade`\n"
                        f"Symbol: `{candidate.symbol if candidate is not None else 'n/a'}`\n"
                        f"Direction: `{candidate.direction if candidate is not None else 'n/a'}`\n"
                        f"Cycle ID: `{cycle_id}`\n"
                        f"Run ID: `{run_id}`\n"
                        f"Thread ID: `{thread_id}`"
                    ),
                )
            return TradeOracleCycleResult(
                run_id=run_id,
                cycle_id=cycle_id,
                outcome="no_trade",
                candidate_count=1 if candidate is not None else 0,
                thread_ids=[thread_id],
            )

        can_open_new_trade, position_sizing = self._position_size_from_candidate(
            candidate=candidate,
            raw_setup=evaluation.raw_setup,
            account_state=account_state,
        )
        self._record_benchmark_event(
            event_type="risk_check",
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=thread_id,
            symbol=candidate.symbol,
            status="ok",
            decision="allow" if can_open_new_trade and position_sizing is not None else "deny",
            payload={"position_size_available": position_sizing is not None},
        )
        if not can_open_new_trade or position_sizing is None:
            self.runtime_state_store.resolve_pending_review(
                thread_id,
                review_action=review_action,
                reviewer=reviewer,
                review_notes=f"{review_action} but risk gate denied execution.",
                telegram_message_id=telegram_message_id,
                cycle_outcome="risk_rejected",
            )
            await self._finalize_terminal_outcome(
                run_id=run_id,
                cycle_id=cycle_id,
                thread_id=thread_id,
                outcome="risk_rejected",
                candidate=candidate,
                summary={
                    "review_action": review_action,
                    "scanner_rows": [evaluation.raw_setup] if evaluation.raw_setup else [],
                    "account_state": account_state.model_dump(),
                },
            )
            if self.telegram_client is not None and telegram_chat_id and telegram_message_id:
                await self.telegram_client.edit_review_message(
                    chat_id=telegram_chat_id,
                    message_id=telegram_message_id,
                    text=(
                        "✅ *TRADE_ORACLE Review Resolved*\n"
                        "----------------------------------------\n"
                        f"Engine: *{engine_ver}*\n"
                        f"Action: *{review_action}*\n"
                        "Outcome: `risk_rejected`\n"
                        f"Symbol: `{candidate.symbol}`\n"
                        f"Direction: `{candidate.direction}`\n"
                        f"Cycle ID: `{cycle_id}`\n"
                        f"Run ID: `{run_id}`\n"
                        f"Thread ID: `{thread_id}`\n"
                        "Transmitted: `False`"
                    ),
                )
            return TradeOracleCycleResult(
                run_id=run_id,
                cycle_id=cycle_id,
                outcome="risk_rejected",
                candidate_count=1,
                thread_ids=[thread_id],
            )

        transmitted = await self._transmit_candidate(
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=thread_id,
            candidate=candidate,
            position_sizing=position_sizing,
        )
        cycle_outcome = "resume_execution_result" if transmitted else "risk_rejected"
        self.runtime_state_store.resolve_pending_review(
            thread_id,
            review_action=review_action,
            reviewer=reviewer,
            review_notes=f"{review_action} from Telegram runtime daemon.",
            telegram_message_id=telegram_message_id,
            cycle_outcome=cycle_outcome,
        )
        await self._finalize_terminal_outcome(
            run_id=run_id,
            cycle_id=cycle_id,
            thread_id=thread_id,
            outcome=cycle_outcome,
            candidate=candidate,
            transmitted=transmitted,
            summary={
                "review_action": review_action,
                "position_sizing": position_sizing,
                "scanner_rows": [evaluation.raw_setup] if evaluation.raw_setup else [],
                "account_state": account_state.model_dump(),
            },
        )
        if self.telegram_client is not None and telegram_chat_id and telegram_message_id:
            await self.telegram_client.edit_review_message(
                chat_id=telegram_chat_id,
                message_id=telegram_message_id,
                text=(
                    "✅ *TRADE_ORACLE Review Resolved*\n"
                    "----------------------------------------\n"
                    f"Engine: *{engine_ver}*\n"
                    f"Action: *{review_action}*\n"
                    f"Outcome: `{cycle_outcome}`\n"
                    f"Symbol: `{candidate.symbol}`\n"
                    f"Direction: `{candidate.direction}`\n"
                    f"Cycle ID: `{cycle_id}`\n"
                    f"Run ID: `{run_id}`\n"
                    f"Thread ID: `{thread_id}`\n"
                    f"Transmitted: `{transmitted}`"
                ),
            )
        return TradeOracleCycleResult(
            run_id=run_id,
            cycle_id=cycle_id,
            outcome=cycle_outcome,
            candidate_count=1,
            transmitted=transmitted,
            thread_ids=[thread_id],
        )

    async def process_callback_query(self, callback_query: dict[str, Any]) -> TradeOracleCycleResult | None:
        callback_id = str(callback_query.get("id", ""))
        raw_data = str(callback_query.get("data", "") or "")
        if ":" not in raw_data:
            if self.telegram_client is not None:
                await self.telegram_client.answer_callback_query(
                    callback_query_id=callback_id,
                    text="Unsupported callback payload.",
                )
            return None

        action_token, thread_id = raw_data.split(":", 1)
        action = action_token.strip().upper()
        if action not in {"APPROVE", "REJECT"}:
            if self.telegram_client is not None:
                await self.telegram_client.answer_callback_query(
                    callback_query_id=callback_id,
                    text="Unsupported review action.",
                )
            return None

        pending_review = self.runtime_state_store.get_pending_review(thread_id)
        if pending_review is None:
            if self.telegram_client is not None:
                await self.telegram_client.answer_callback_query(
                    callback_query_id=callback_id,
                    text="Pending review not found.",
                )
            return None
        if pending_review.review_status not in OPEN_REVIEW_STATUSES:
            if self.telegram_client is not None:
                await self.telegram_client.answer_callback_query(
                    callback_query_id=callback_id,
                    text=f"Review already {pending_review.review_status}.",
                )
            return None

        if self.telegram_client is not None:
            await self.telegram_client.answer_callback_query(
                callback_query_id=callback_id,
                text=f"{action.title()} received.",
            )

        reviewer = _reviewer_name(callback_query)
        account_state = TradeOracleAccountSnapshot.model_validate(pending_review.account_state)
        seed = _now_run_seed()
        run_id = _build_run_id(seed)

        if action == "APPROVE":
            # --- CIRCUIT BREAKER CHECK DURING REVIEW WINDOW ---
            account_state_for_cb = await self._resolve_account_state()
            try:
                risk_manager = RiskManager(
                    current_balance=account_state_for_cb.current_balance,
                    highest_equity=account_state_for_cb.highest_equity,
                    active_trades_count=account_state_for_cb.active_trades_count,
                )
                if hasattr(risk_manager, "check_circuit_breaker"):
                    risk_manager.check_circuit_breaker()
            except Exception as e:
                if type(e).__name__ == "CircuitBreakerTriggered":
                    await self._handle_circuit_breaker_event(e, run_id=run_id, cycle_id=pending_review.cycle_id)
                    await self._send_cycle_summary_message(
                        "⚠️ Approved trade was NOT executed — circuit breaker triggered during review window. System halted."
                    )
                    self.runtime_state_store.resolve_pending_review(
                        thread_id,
                        review_action=action,
                        reviewer=reviewer,
                        review_notes="Approved, but circuit breaker triggered before execution.",
                        telegram_message_id=pending_review.telegram_message_id,
                        cycle_outcome="halted_circuit_breaker",
                    )
                    return TradeOracleCycleResult(
                        run_id=run_id,
                        cycle_id=pending_review.cycle_id,
                        outcome="halted_circuit_breaker",
                    )
                else:
                    raise

        evaluation = await self.orchestrator.resume_review(
            thread_id=thread_id,
            human_decision={
                "action": action,
                "reviewer": reviewer,
                "notes": f"{action.title()} from Telegram runtime daemon.",
            },
            run_id=run_id,
            event_source="single_runtime_daemon",
        )
        return await self._handle_resume_result(
            thread_id=thread_id,
            run_id=run_id,
            cycle_id=pending_review.cycle_id,
            account_state=account_state,
            evaluation=evaluation,
            telegram_chat_id=pending_review.telegram_chat_id,
            telegram_message_id=pending_review.telegram_message_id,
            reviewer=reviewer,
            review_action=action,
        )

    async def poll_telegram_once(self) -> int:
        if self.telegram_client is None:
            return 0
        updates = await self.telegram_client.fetch_updates(
            offset=self.telegram_update_offset,
            timeout=self.telegram_poll_timeout_seconds,
        )
        processed = 0
        for update in updates:
            update_id = int(update.get("update_id", 0) or 0)
            callback_query = update.get("callback_query")
            if isinstance(callback_query, dict):
                await self.process_callback_query(callback_query)
                processed += 1
            next_offset = update_id + 1
            if self.telegram_update_offset is None or next_offset > self.telegram_update_offset:
                self.telegram_update_offset = next_offset
                self._persist_telegram_update_offset()
        return processed

    async def run_forever(self, *, start_immediately: bool = settings.TRADE_ORACLE_DAEMON_START_IMMEDIATELY) -> None:
        next_cycle_at = time.monotonic() if start_immediately else time.monotonic() + self.cycle_interval_seconds
        while True:
            try:
                await self.poll_telegram_once()
            except Exception:
                logger.exception("Telegram polling failed.")
            if time.monotonic() >= next_cycle_at:
                try:
                    await self.run_cycle_once()
                except Exception:
                    logger.exception("Forward-test cycle failed.")
                next_cycle_at = time.monotonic() + self.cycle_interval_seconds
            await asyncio.sleep(max(0.1, self.idle_sleep_seconds))


def build_default_trade_oracle_daemon(
    *,
    runtime_state_backend: str | None = None,
    benchmark_backend: str | None = None,
    telegram_token: str | None = None,
) -> TradeOracleSingleRuntimeDaemon:
    """Build the default single-runtime daemon from env-backed settings."""

    resolved_execution_backend = resolve_execution_backend()
    runtime_state_store = build_trade_oracle_runtime_state_store(
        backend=runtime_state_backend,
    )
    benchmark_store = build_trade_oracle_benchmark_store(
        backend=benchmark_backend,
    )
    orchestrator = LangGraphSupervisorOrchestrator(
        checkpointer_path=settings.TRADE_ORACLE_LANGGRAPH_CHECKPOINTER_PATH,
        audit_backend=settings.TRADE_ORACLE_AUDIT_BACKEND,
        audit_db_path=settings.TRADE_ORACLE_AUDIT_DB_PATH,
        auto_approve=settings.TRADE_ORACLE_DAEMON_AUTO_APPROVE_REVIEWS,
    )
    resolved_telegram_token = (telegram_token or settings.TRADE_ORACLE_TELEGRAM_BOT_TOKEN or "").strip()
    telegram_client = HttpxTelegramBotClient(resolved_telegram_token) if resolved_telegram_token else None

    # Build shadow runner — returns None if GOOGLE_API_KEY is missing or
    # TRADE_ORACLE_SHADOW_MODE_ENABLED=0, leaving the primary engine unchanged.
    shadow_runner = build_shadow_mode_runner()
    if shadow_runner is not None:
        logger.info(
            "[ShadowMode] Active. Writing counterfactuals to variant '%s'.",
            settings.TRADE_ORACLE_SHADOW_BENCHMARK_VARIANT,
        )
    else:
        logger.info("[ShadowMode] Inactive (key missing or disabled).")

    return TradeOracleSingleRuntimeDaemon(
        runtime_state_store=runtime_state_store,
        benchmark_store=benchmark_store,
        orchestrator=orchestrator,
        scanner_runner=_default_scanner_runner,
        execution_client_factory=build_execution_client_from_settings,
        execution_backend=resolved_execution_backend,
        benchmark_variant=settings.TRADE_ORACLE_BENCHMARK_VARIANT,
        shadow_variant=settings.TRADE_ORACLE_SHADOW_BENCHMARK_VARIANT,
        shadow_runner=shadow_runner,
        telegram_client=telegram_client,
        telegram_chat_id=settings.TRADE_ORACLE_TELEGRAM_CHAT_ID,
        watchlist=list(settings.TRADE_ORACLE_DAEMON_WATCHLIST),
    )


__all__ = [
    "HttpxTelegramBotClient",
    "TELEGRAM_UPDATE_OFFSET_CHECKPOINT_KEY",
    "TelegramBotClientProtocol",
    "TradeOracleAccountSnapshot",
    "TradeOracleCycleResult",
    "TradeOracleSingleRuntimeDaemon",
    "build_default_trade_oracle_daemon",
]
