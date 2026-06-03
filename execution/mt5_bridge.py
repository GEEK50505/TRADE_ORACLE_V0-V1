"""Async-friendly MetaTrader 5 execution bridge for the TRADE_ORACLE pivot."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from config import settings

try:  # pragma: no cover - depends on optional local Windows package
    import MetaTrader5 as _mt5
except ImportError:  # pragma: no cover - exercised through fake bridge tests instead
    _mt5 = None


class MetaTraderBridge:
    """
    Async wrapper around the synchronous MetaTrader 5 Python package.

    The MT5 package communicates with a locally running terminal over IPC, so we
    keep the public API async and dispatch blocking calls via ``asyncio.to_thread``.
    """

    def __init__(
        self,
        *,
        login: int | str,
        password: str,
        server: str,
        terminal_path: str | None = None,
        symbol_suffix: str = "",
        symbol_map: dict[str, str] | None = None,
        slippage_points: int = 20,
        magic_number: int = 26042026,
        comment_prefix: str = "TRADE_ORACLE",
        duplicate_guard_enabled: bool = settings.TRADE_ORACLE_MT5_DUPLICATE_GUARD_ENABLED,
        duplicate_price_tolerance_points: int = settings.TRADE_ORACLE_MT5_PRICE_TOLERANCE_POINTS,
    ) -> None:
        self.login_id = int(login)
        self.password = password
        self.server = server
        self.terminal_path = terminal_path or ""
        self.symbol_suffix = symbol_suffix or ""
        self.symbol_map = {str(key): str(value) for key, value in (symbol_map or settings.MT5_SYMBOL_MAP or {}).items()}
        self.slippage_points = int(slippage_points)
        self.magic_number = int(magic_number)
        self.comment_prefix = comment_prefix
        self.duplicate_guard_enabled = bool(duplicate_guard_enabled)
        self.duplicate_price_tolerance_points = max(0, int(duplicate_price_tolerance_points))
        self.logger = logging.getLogger("TRADE_ORACLE.MT5_Bridge")
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO)
        self._authenticated = False

    @staticmethod
    def _module() -> Any:
        if _mt5 is None:
            raise ImportError(
                "MetaTrader5 package is not installed. Install it in the local Windows execution environment."
            )
        return _mt5

    def _initialize_terminal(self) -> bool:
        mt5 = self._module()
        kwargs: dict[str, Any] = {}
        if self.terminal_path:
            kwargs["path"] = self.terminal_path

        initialized = mt5.initialize(**kwargs) if kwargs else mt5.initialize()
        if not initialized:
            self.logger.critical("MT5 initialization failed. Error: %s", mt5.last_error())
            return False
        return True

    async def authenticate(self) -> bool:
        return await asyncio.to_thread(self._authenticate_sync)

    def _authenticate_sync(self) -> bool:
        mt5 = self._module()
        if not self._initialize_terminal():
            return False

        account_info = mt5.account_info()
        terminal_info = mt5.terminal_info()
        current_login = int(getattr(account_info, "login", 0) or 0) if account_info else 0
        current_server = str(getattr(account_info, "server", "") or "").strip().lower() if account_info else ""
        expected_server = str(self.server).strip().lower()
        if (
            account_info is not None
            and terminal_info is not None
            and bool(getattr(terminal_info, "connected", False))
            and current_login == self.login_id
            and current_server == expected_server
        ):
            self._authenticated = True
            self.logger.info(
                "Attached to existing MT5 terminal session for login %s on server %s.",
                self.login_id,
                self.server,
            )
            return True

        authorized = mt5.login(self.login_id, password=self.password, server=self.server)
        if authorized:
            self._authenticated = True
            self.logger.info("Successfully authenticated with MT5 server %s.", self.server)
            return True

        self.logger.critical("MT5 authentication failed. Error: %s", mt5.last_error())
        return False

    async def get_platform_details(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_platform_details_sync)

    def _get_platform_details_sync(self) -> dict[str, Any] | None:
        mt5 = self._module()
        if not self._authenticated and not self._authenticate_sync():
            return None

        account_info = mt5.account_info()
        if account_info is None:
            self.logger.error("Failed to fetch MT5 account state. Error: %s", mt5.last_error())
            return None

        positions = mt5.positions_get()
        active_trades = len(positions or ())
        return {
            "equity": float(getattr(account_info, "equity", 0.0)),
            "active_trades": active_trades,
        }

    def _normalize_symbol(self, symbol: str) -> str:
        raw_symbol = str(symbol).strip()
        if raw_symbol in self.symbol_map:
            return self.symbol_map[raw_symbol]

        normalized = raw_symbol.replace("/", "")
        if normalized in self.symbol_map:
            return self.symbol_map[normalized]
        if self.symbol_suffix and not normalized.endswith(self.symbol_suffix):
            normalized = f"{normalized}{self.symbol_suffix}"
        return normalized

    async def get_symbol_status(self, symbol: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_symbol_status_sync, symbol)

    def _get_symbol_status_sync(self, symbol: str) -> dict[str, Any]:
        mt5 = self._module()
        if not self._authenticated and not self._authenticate_sync():
            return {"requested_symbol": symbol, "authenticated": False, "available": False}

        resolved_symbol = self._normalize_symbol(symbol)
        info = mt5.symbol_info(resolved_symbol)
        selected = False
        if info is not None and not getattr(info, "visible", True):
            selected = bool(mt5.symbol_select(resolved_symbol, True))
            info = mt5.symbol_info(resolved_symbol)

        tick = mt5.symbol_info_tick(resolved_symbol)
        bid = float(getattr(tick, "bid", 0.0) or 0.0) if tick else 0.0
        ask = float(getattr(tick, "ask", 0.0) or 0.0) if tick else 0.0
        last = float(getattr(tick, "last", 0.0) or 0.0) if tick else 0.0

        return {
            "requested_symbol": symbol,
            "resolved_symbol": resolved_symbol,
            "authenticated": True,
            "available": info is not None,
            "selected": selected,
            "visible": bool(getattr(info, "visible", False)) if info else False,
            "trade_mode": getattr(info, "trade_mode", None) if info else None,
            "point": float(getattr(info, "point", 0.0) or 0.0) if info else 0.0,
            "bid": bid,
            "ask": ask,
            "last": last,
            "has_live_tick": any(value > 0.0 for value in (bid, ask, last)),
        }

    async def transmit_limit_order(
        self,
        *,
        symbol: str,
        direction: str,
        size: float,
        limit_price: float,
        stop_loss: float,
        take_profit: float,
        size_mode: str = "units",
    ) -> bool:
        return await asyncio.to_thread(
            self._transmit_limit_order_sync,
            symbol,
            direction,
            size,
            limit_price,
            stop_loss,
            take_profit,
            size_mode,
        )

    @staticmethod
    def _round_volume_down(volume: float, step: float, digits: int = 8) -> float:
        if step <= 0:
            return round(volume, digits)
        stepped = math.floor((volume / step) + 1e-12) * step
        return round(stepped, digits)

    def _resolve_order_volume(
        self,
        *,
        resolved_symbol: str,
        requested_size: float,
        symbol_info: Any,
        size_mode: str,
    ) -> float | None:
        volume_min = float(getattr(symbol_info, "volume_min", 0.0) or 0.0)
        volume_max = float(getattr(symbol_info, "volume_max", 0.0) or 0.0)
        volume_step = float(getattr(symbol_info, "volume_step", 0.0) or 0.0)
        contract_size = float(getattr(symbol_info, "trade_contract_size", 0.0) or 0.0)

        if requested_size <= 0.0:
            self.logger.error("MT5 requested size for %s must be positive.", resolved_symbol)
            return None

        if str(size_mode).strip().lower() == "broker_volume":
            resolved_volume = float(requested_size)
        else:
            if contract_size <= 0.0:
                self.logger.error(
                    "MT5 symbol %s returned no valid contract size; refusing unit conversion.",
                    resolved_symbol,
                )
                return None

            resolved_volume = float(requested_size) / contract_size
            resolved_volume = self._round_volume_down(resolved_volume, volume_step or 0.01)

            if resolved_volume < volume_min:
                self.logger.error(
                    "Requested %s unit(s) for %s resolves to broker volume %.8f, below broker minimum %.8f.",
                    requested_size,
                    resolved_symbol,
                    resolved_volume,
                    volume_min,
                )
                return None

        if volume_step > 0.0:
            resolved_volume = round(resolved_volume, 8)
            ratio = resolved_volume / volume_step
            if not math.isclose(ratio, round(ratio), rel_tol=0.0, abs_tol=1e-8):
                resolved_volume = self._round_volume_down(resolved_volume, volume_step)

        if volume_min > 0.0 and resolved_volume < volume_min:
            self.logger.error(
                "MT5 broker volume %.8f for %s is below the minimum %.8f.",
                resolved_volume,
                resolved_symbol,
                volume_min,
            )
            return None
        if volume_max > 0.0 and resolved_volume > volume_max:
            self.logger.error(
                "MT5 broker volume %.8f for %s exceeds the maximum %.8f.",
                resolved_volume,
                resolved_symbol,
                volume_max,
            )
            return None
        return resolved_volume

    @staticmethod
    def _is_finite_positive(value: float) -> bool:
        return math.isfinite(float(value)) and float(value) > 0.0

    def _validate_order_levels(
        self,
        *,
        resolved_symbol: str,
        side: str,
        limit_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> bool:
        if not all(self._is_finite_positive(value) for value in (limit_price, stop_loss, take_profit)):
            self.logger.error(
                "MT5 order levels for %s must be finite positive numbers. price=%s sl=%s tp=%s",
                resolved_symbol,
                limit_price,
                stop_loss,
                take_profit,
            )
            return False

        if side == "BUY" and not (stop_loss < limit_price < take_profit):
            self.logger.error(
                "MT5 BUY levels for %s are invalid: expected stop_loss < limit_price < take_profit.",
                resolved_symbol,
            )
            return False
        if side == "SELL" and not (take_profit < limit_price < stop_loss):
            self.logger.error(
                "MT5 SELL levels for %s are invalid: expected take_profit < limit_price < stop_loss.",
                resolved_symbol,
            )
            return False
        return True

    def _has_duplicate_pending_order(
        self,
        *,
        mt5: Any,
        resolved_symbol: str,
        order_type: int,
        resolved_volume: float,
        limit_price: float,
        stop_loss: float,
        take_profit: float,
        symbol_info: Any,
    ) -> bool:
        if not self.duplicate_guard_enabled or not hasattr(mt5, "orders_get"):
            return False

        try:
            orders = mt5.orders_get(symbol=resolved_symbol)
        except TypeError:
            orders = mt5.orders_get()
        except Exception:
            self.logger.exception("MT5 duplicate-order inspection failed for %s.", resolved_symbol)
            return False

        if not orders:
            return False

        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        tolerance = point * self.duplicate_price_tolerance_points if point > 0.0 else 0.0
        comment_prefix = str(self.comment_prefix)

        for order in orders:
            order_symbol = str(getattr(order, "symbol", "") or "")
            order_magic = int(getattr(order, "magic", 0) or 0)
            existing_type = int(getattr(order, "type", -1) or -1)
            existing_price = float(getattr(order, "price_open", getattr(order, "price", 0.0)) or 0.0)
            existing_volume = float(getattr(order, "volume_initial", getattr(order, "volume_current", 0.0)) or 0.0)
            existing_sl = float(getattr(order, "sl", 0.0) or 0.0)
            existing_tp = float(getattr(order, "tp", 0.0) or 0.0)
            existing_comment = str(getattr(order, "comment", "") or "")

            if order_symbol != resolved_symbol:
                continue
            if order_magic != self.magic_number:
                continue
            if existing_type != int(order_type):
                continue
            if comment_prefix and not existing_comment.startswith(comment_prefix):
                continue
            if tolerance > 0.0 and abs(existing_price - float(limit_price)) > tolerance:
                continue
            if tolerance <= 0.0 and not math.isclose(existing_price, float(limit_price), rel_tol=0.0, abs_tol=1e-8):
                continue
            if existing_volume > 0.0 and not math.isclose(existing_volume, float(resolved_volume), rel_tol=0.0, abs_tol=1e-8):
                continue
            if existing_sl > 0.0 and abs(existing_sl - float(stop_loss)) > max(tolerance, 1e-8):
                continue
            if existing_tp > 0.0 and abs(existing_tp - float(take_profit)) > max(tolerance, 1e-8):
                continue

            self.logger.warning(
                "MT5 duplicate pending order detected for %s at price %.8f; treating transmit as already placed.",
                resolved_symbol,
                existing_price,
            )
            return True

        return False

    def _resolve_mt5_order_request(
        self,
        *,
        mt5: Any,
        side: str,
        symbol_info: Any,
        tick: Any,
        requested_price: float,
    ) -> dict[str, Any] | None:
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        tolerance = point if point > 0.0 else max(abs(float(requested_price)) * 1e-6, 1e-8)
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)

        if side == "BUY":
            if ask <= 0.0:
                self.logger.error("MT5 symbol returned no valid ask price for BUY order routing.")
                return None
            if abs(float(requested_price) - ask) <= tolerance:
                return {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "order_type": mt5.ORDER_TYPE_BUY,
                    "price": ask,
                    "comment": f"{self.comment_prefix}_BUY_MARKET",
                    "pending": False,
                }
            if float(requested_price) < ask:
                return {
                    "action": mt5.TRADE_ACTION_PENDING,
                    "order_type": mt5.ORDER_TYPE_BUY_LIMIT,
                    "price": float(requested_price),
                    "comment": f"{self.comment_prefix}_BUY_LIMIT",
                    "pending": True,
                }
            return {
                "action": mt5.TRADE_ACTION_PENDING,
                "order_type": mt5.ORDER_TYPE_BUY_STOP,
                "price": float(requested_price),
                "comment": f"{self.comment_prefix}_BUY_STOP",
                "pending": True,
            }

        if side == "SELL":
            if bid <= 0.0:
                self.logger.error("MT5 symbol returned no valid bid price for SELL order routing.")
                return None
            if abs(float(requested_price) - bid) <= tolerance:
                return {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "order_type": mt5.ORDER_TYPE_SELL,
                    "price": bid,
                    "comment": f"{self.comment_prefix}_SELL_MARKET",
                    "pending": False,
                }
            if float(requested_price) > bid:
                return {
                    "action": mt5.TRADE_ACTION_PENDING,
                    "order_type": mt5.ORDER_TYPE_SELL_LIMIT,
                    "price": float(requested_price),
                    "comment": f"{self.comment_prefix}_SELL_LIMIT",
                    "pending": True,
                }
            return {
                "action": mt5.TRADE_ACTION_PENDING,
                "order_type": mt5.ORDER_TYPE_SELL_STOP,
                "price": float(requested_price),
                "comment": f"{self.comment_prefix}_SELL_STOP",
                "pending": True,
            }

        self.logger.error("Invalid MT5 order direction %s.", side)
        return None

    def _transmit_limit_order_sync(
        self,
        symbol: str,
        direction: str,
        size: float,
        limit_price: float,
        stop_loss: float,
        take_profit: float,
        size_mode: str = "units",
    ) -> bool:
        mt5 = self._module()
        if not self._authenticated and not self._authenticate_sync():
            return False

        resolved_symbol = self._normalize_symbol(symbol)
        symbol_info = mt5.symbol_info(resolved_symbol)
        if symbol_info is None:
            self.logger.error("MT5 symbol %s not found.", resolved_symbol)
            return False
        if not getattr(symbol_info, "visible", True) and not mt5.symbol_select(resolved_symbol, True):
            self.logger.error("MT5 symbol %s could not be enabled for trading.", resolved_symbol)
            return False
        tick = mt5.symbol_info_tick(resolved_symbol)
        if tick is None or not any(float(getattr(tick, field, 0.0) or 0.0) > 0.0 for field in ("bid", "ask", "last")):
            self.logger.error("MT5 symbol %s has no live tick data; refusing transmission.", resolved_symbol)
            return False
        resolved_volume = self._resolve_order_volume(
            resolved_symbol=resolved_symbol,
            requested_size=float(size),
            symbol_info=symbol_info,
            size_mode=size_mode,
        )
        if resolved_volume is None:
            return False

        side = direction.upper()
        if not self._validate_order_levels(
            resolved_symbol=resolved_symbol,
            side=side,
            limit_price=float(limit_price),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
        ):
            return False

        order_request = self._resolve_mt5_order_request(
            mt5=mt5,
            side=side,
            symbol_info=symbol_info,
            tick=tick,
            requested_price=float(limit_price),
        )
        if order_request is None:
            return False
        order_type = int(order_request["order_type"])

        if bool(order_request.get("pending", False)):
            if self._has_duplicate_pending_order(
                mt5=mt5,
                resolved_symbol=resolved_symbol,
                order_type=order_type,
                resolved_volume=resolved_volume,
                limit_price=float(order_request["price"]),
                stop_loss=float(stop_loss),
                take_profit=float(take_profit),
                symbol_info=symbol_info,
            ):
                return True

        request = {
            "action": int(order_request["action"]),
            "symbol": resolved_symbol,
            "volume": resolved_volume,
            "type": order_type,
            "price": float(order_request["price"]),
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": int(self.slippage_points),
            "magic": int(self.magic_number),
            "comment": str(order_request["comment"]),
        }
        if bool(order_request.get("pending", False)):
            request["type_time"] = mt5.ORDER_TIME_GTC
            request["type_filling"] = getattr(mt5, "ORDER_FILLING_RETURN", 0)

        result = mt5.order_send(request)
        if result is None:
            self.logger.error("MT5 order_send returned no result. Error: %s", mt5.last_error())
            return False

        success_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", None),
            getattr(mt5, "TRADE_RETCODE_PLACED", None),
        }
        if getattr(result, "retcode", None) in success_codes:
            self.logger.info(
                "MT5 order placed: %s %s volume=%s price=%s action=%s (requested_size=%s size_mode=%s)",
                resolved_symbol,
                side,
                resolved_volume,
                order_request["price"],
                order_request["comment"],
                size,
                size_mode,
            )
            return True

        self.logger.error(
            "MT5 order placement failed for %s. Retcode=%s Comment=%s",
            resolved_symbol,
            getattr(result, "retcode", None),
            getattr(result, "comment", ""),
        )
        return False

    async def shutdown(self) -> None:
        await asyncio.to_thread(self._shutdown_sync)

    def _shutdown_sync(self) -> None:
        mt5 = self._module()
        mt5.shutdown()
        self._authenticated = False
