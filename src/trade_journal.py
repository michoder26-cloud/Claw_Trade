"""Trade Journal: Structured entry/exit reasoning and lesson-learned extraction.

This module provides the :class:`TradeJournal` — a structured record of every
trade taken by the orchestrator, capturing:

- **Entry reasoning**: CEO reasoning + bull/bear consensus + quant/news
  summaries + Risk Critic verdict at decision time.
- **Exit reasoning**: close reason (TP/SL/breakeven), P&L, and an
  AI-generated post-mortem / lesson learned.
- **Performance summaries**: recent win rate, regime win rate, streak strings,
  consecutive loss/win counts, recent P&L trajectory — all consumed by the
  Risk Critic, :class:`AdaptivePositionSizer`, and :class:`RiskManager`.

Design principles (per the upgrade plan):

1. **Backtest-compatible**: works with **no SQLite database**. When ``db`` is
   ``None`` (or any DB call fails), the journal falls back to an in-memory ring
   buffer that retains the last ``max_buffer`` trades. This makes it fully
   functional in ``USE_MOCK_AI=true`` backtest mode with zero persistence.
2. **Non-breaking**: wraps every DB call in try/except and never propagates
   persistence failures to the orchestrator. A failed SQLite write degrades
   silently to in-memory-only operation.
3. **Never touches MT5**: this module has no dependency on ``mt5_connector.py``
   and makes no network calls.
4. **Composable**: the orchestrator delegates to a single ``TradeJournal``
   instance; :class:`RiskManager` and :class:`AdaptivePositionSizer` read from
   it via simple accessor methods.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TradeJournal:
    """Structured trade journal with entry/exit reasoning and lessons.

    Uses the existing SQLite database from ``learning_engine.py``
    (:class:`TradeDatabase`) when available, but adds structured entry/exit
    reasoning fields that the flat ``trades`` table does not capture.

    Also maintains an **in-memory ring buffer** (last ``max_buffer`` trades)
    for fast access by the Risk Critic and :class:`AdaptivePositionSizer`.
    The in-memory buffer is the authoritative source for all
    performance/streak/P&L queries; the SQLite DB is a durable backup used only
    for regime win-rate lookups (and only when present).

    The class works **without any SQLite database** — in backtest mode simply
    instantiate ``TradeJournal()`` with no ``db`` argument and every method
    falls back to the in-memory buffer.
    """

    def __init__(self, db: Optional[Any] = None, max_buffer: int = 50):
        """Initialize the TradeJournal.

        Args:
            db: Optional :class:`TradeDatabase` (from ``learning_engine.py``).
                When ``None`` (the backtest default), the journal operates
                purely in-memory. When provided, entries/exits are also
                persisted to SQLite, but all read-side queries still use the
                in-memory buffer for speed.
            max_buffer: Maximum number of trades kept in the in-memory ring
                buffer. Older trades are evicted once the buffer is full.
        """
        self.db = db  # TradeDatabase from learning_engine.py (optional)
        self.recent_trades: List[Dict[str, Any]] = []  # In-memory ring buffer
        self.max_buffer = max_buffer
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.daily_pnl: Dict[str, float] = {}  # date_str (YYYY-MM-DD) -> pnl

    # ------------------------------------------------------------------ #
    # Recording
    # ------------------------------------------------------------------ #

    def record_entry(
        self,
        ticket: Optional[int],
        signal: str,
        entry_price: float,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        confidence: float,
        regime: str,
        fibo_zone: str,
        macd_state: str,
        ceo_reasoning: str,
        bull_reasoning: str = "",
        bear_reasoning: str = "",
        quant_summary: str = "",
        news_summary: str = "",
        critic_verdict: str = "",
        critic_concerns: str = "",
        timestamp: Optional[str] = None,
    ) -> int:
        """Record a trade entry with full reasoning context.

        All reasoning strings are optional (default empty) so the method can
        be called from backtest mode where bull/bear/news summaries may not
        exist.

        Args:
            ticket: MT5 ticket (``None`` in backtest/paper mode).
            signal: ``"BUY"`` or ``"SELL"``.
            entry_price: Execution price.
            lot_size: Lot size executed.
            stop_loss: SL price.
            take_profit: TP price.
            confidence: CEO confidence (0-1).
            regime: Market regime string (e.g. ``"TRENDING"``).
            fibo_zone: Fibo zone label.
            macd_state: MACD state label.
            ceo_reasoning: CEO decision reasoning text.
            bull_reasoning: Bull agent reasoning (optional).
            bear_reasoning: Bear agent reasoning (optional).
            quant_summary: QuantAnalyst summary (optional).
            news_summary: NewsAnalyst summary (optional).
            critic_verdict: Risk Critic verdict (``"APPROVE"``/``"DOWNSIZE"``
                /``"VETO"``) — empty if no critic ran.
            critic_concerns: Risk Critic concerns text (optional).
            timestamp: ISO timestamp string. When ``None``, ``utcnow()`` is
                used.

        Returns:
            ``trade_id`` from the database, or ``-1`` if the DB is unavailable
            or the write failed (the in-memory buffer is still updated).
        """
        if timestamp is None:
            timestamp = str(datetime.utcnow())

        entry_data = {
            "ticket": ticket,
            "signal": signal,
            "entry_price": entry_price,
            "lot_size": lot_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "regime": regime,
            "fibo_zone": fibo_zone,
            "macd_state": macd_state,
            "confidence": confidence,
            "ceo_reasoning": ceo_reasoning,
            "lot_multiplier": 1.0,  # Updated by orchestrator if overridden
            "entry_time": timestamp,
        }

        trade_id = -1
        if self.db is not None:
            try:
                trade_id = self.db.record_entry(entry_data)
            except Exception as e:
                logger.error(f"Journal DB entry failed (falling back to memory): {e}")
                trade_id = -1

        # Structured in-memory record (holds richer reasoning than the DB schema)
        record: Dict[str, Any] = {
            "trade_id": trade_id,
            "ticket": ticket,
            "signal": signal,
            "entry_price": entry_price,
            "lot_size": lot_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": confidence,
            "regime": regime,
            "fibo_zone": fibo_zone,
            "macd_state": macd_state,
            "entry_time": timestamp,
            "entry_reasoning": {
                "ceo": ceo_reasoning,
                "bull": bull_reasoning,
                "bear": bear_reasoning,
                "quant": quant_summary,
                "news": news_summary,
                "critic_verdict": critic_verdict,
                "critic_concerns": critic_concerns,
            },
            "exit_reasoning": None,
            "lesson_learned": None,
            "pnl_usd": None,
            "close_reason": None,
            "exit_price": None,
            "exit_time": None,
            "status": "OPEN",
        }

        self.recent_trades.append(record)
        if len(self.recent_trades) > self.max_buffer:
            self.recent_trades = self.recent_trades[-self.max_buffer:]

        return trade_id

    def record_exit(
        self,
        ticket: Optional[int],
        exit_price: float,
        pnl_usd: float,
        close_reason: str,
        exit_reasoning: str = "",
        lesson_learned: str = "",
        exit_time: Optional[str] = None,
    ) -> None:
        """Record a trade exit with reasoning and lesson.

        Updates the matching OPEN trade in the in-memory buffer and, when a
        DB is present, persists the exit via ``db.record_exit``. Also updates
        the consecutive win/loss streak counters and the daily P&L map.

        Args:
            ticket: MT5 ticket (``None`` in backtest mode — matched by
                ``trade_id`` / OPEN status instead).
            exit_price: Price at which the trade closed.
            pnl_usd: Realized profit/loss in USD.
            close_reason: ``"TP"``, ``"SL"``, ``"BREAKEVEN"``, or
                ``"MANUAL_CLOSE"``.
            exit_reasoning: Post-mortem text (AI-generated or rule-based).
            lesson_learned: One-line lesson extracted from the trade.
            exit_time: ISO timestamp string (``utcnow()`` when ``None``).
        """
        if exit_time is None:
            exit_time = str(datetime.utcnow())

        exit_data = {
            "ticket": ticket,
            "exit_price": exit_price,
            "pnl_usd": pnl_usd,
            "close_reason": close_reason,
            "lesson": lesson_learned,
            "exit_time": exit_time,
        }

        if self.db is not None:
            try:
                self.db.record_exit(ticket, exit_data)
            except Exception as e:
                logger.error(f"Journal DB exit update failed (memory-only): {e}")

        # Update the in-memory buffer: find the matching OPEN trade.
        # Match priority:
        #   1. ticket is not None  → match by ticket
        #   2. ticket is None     → match the oldest OPEN trade (backtest mode)
        target: Optional[Dict[str, Any]] = None
        if ticket is not None:
            for trade in self.recent_trades:
                if trade["status"] == "OPEN" and trade.get("ticket") == ticket:
                    target = trade
                    break
        else:
            for trade in self.recent_trades:
                if trade["status"] == "OPEN":
                    target = trade
                    break

        if target is not None:
            target["exit_price"] = exit_price
            target["pnl_usd"] = pnl_usd
            target["close_reason"] = close_reason
            target["exit_reasoning"] = exit_reasoning
            target["lesson_learned"] = lesson_learned
            target["exit_time"] = exit_time
            target["status"] = "CLOSED"

        # Update streak counters
        if close_reason == "TP":
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        elif close_reason in ("SL", "MANUAL_CLOSE"):
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        elif close_reason == "BREAKEVEN":
            # Breakeven resets neither counter
            pass

        # Update daily P&L map
        date_key = str(exit_time)[:10]
        self.daily_pnl[date_key] = self.daily_pnl.get(date_key, 0.0) + float(pnl_usd)

    # ------------------------------------------------------------------ #
    # Streak / P&L accessors (consumed by RiskManager & AdaptivePositionSizer)
    # ------------------------------------------------------------------ #

    def get_consecutive_losses(self) -> int:
        """Return the current consecutive loss count."""
        return self.consecutive_losses

    def get_consecutive_wins(self) -> int:
        """Return the current consecutive win count."""
        return self.consecutive_wins

    def get_daily_pnl(self, date_str: Optional[str] = None) -> float:
        """Get cumulative P&L for a specific date (or today).

        Args:
            date_str: ``"YYYY-MM-DD"`` string. When ``None``, today's UTC date
                is used.

        Returns:
            Total realized P&L for that date (0.0 if no trades closed).
        """
        if date_str is None:
            date_str = str(datetime.utcnow())[:10]
        return self.daily_pnl.get(date_str, 0.0)

    def get_recent_pnl(self, n: int = 5) -> List[float]:
        """Get P&L values for the last ``n`` closed trades.

        Used by :class:`AdaptivePositionSizer` to compute the P&L trajectory
        multiplier.

        Args:
            n: Number of most recent closed trades to return.

        Returns:
            List of P&L floats (most recent last). Empty list if no closed
            trades are recorded.
        """
        closed = [t for t in self.recent_trades if t["status"] == "CLOSED"]
        return [t["pnl_usd"] for t in closed[-n:] if t["pnl_usd"] is not None]

    # ------------------------------------------------------------------ #
    # Performance summaries (consumed by Risk Critic)
    # ------------------------------------------------------------------ #

    def get_recent_performance(self, regime: Optional[str] = None) -> Dict[str, Any]:
        """Get a recent performance summary for the Risk Critic.

        All values are derived from the in-memory buffer (no DB hit for the
        core metrics), with the regime win rate optionally enriched from the
        SQLite ``feature_winrates`` table when a DB is present.

        Args:
            regime: Current market regime. When provided (and a DB is
                available), the regime-specific historical win rate is looked
                up.

        Returns:
            Dict with keys:

            - ``last_5_winrate`` (float, 0-100): win rate of the last 5 closed
              trades. Defaults to 50.0 when no closed trades exist.
            - ``regime_winrate`` (float, 0-100): historical win rate for the
              given regime (from SQLite), or 50.0 when no data.
            - ``recent_streak`` (str): recent outcome sequence, e.g.
              ``"WWLLW"`` (oldest first). ``"W"`` for TP, ``"L"`` for SL/manual
              close, ``"="`` for breakeven.
            - ``last_5_pnl`` (List[float]): P&L of the last 5 closed trades.
        """
        closed = [t for t in self.recent_trades if t["status"] == "CLOSED"]
        recent_closed = closed[-5:] if len(closed) >= 5 else closed

        wins = sum(1 for t in recent_closed if t["close_reason"] == "TP")
        last_5_wr = (wins / len(recent_closed) * 100) if recent_closed else 50.0

        # Regime-specific win rate (from DB when available)
        regime_wr = 50.0
        if regime and self.db is not None:
            try:
                wr_data = self.db.get_winrate_by_feature("regime", min_samples=3)
                regime_wr = wr_data.get(regime, 50.0)
            except Exception:
                pass

        # Streak string (oldest → newest)
        streak_parts: List[str] = []
        for t in recent_closed:
            reason = t.get("close_reason")
            if reason == "TP":
                streak_parts.append("W")
            elif reason in ("SL", "MANUAL_CLOSE"):
                streak_parts.append("L")
            else:
                streak_parts.append("=")
        recent_streak = "".join(streak_parts)

        return {
            "last_5_winrate": last_5_wr,
            "regime_winrate": regime_wr,
            "recent_streak": recent_streak,
            "last_5_pnl": [t["pnl_usd"] for t in recent_closed if t["pnl_usd"] is not None],
        }

    def get_recent_lessons(self, n: int = 5) -> List[str]:
        """Get the last ``n`` lessons learned for CEO prompt injection.

        Replaces the flat ``learning_memory`` list of strings with structured
        lesson text extracted from closed trades.

        Args:
            n: Number of recent lessons to return.

        Returns:
            List of lesson strings (most recent last). Empty if no lessons.
        """
        closed = [
            t
            for t in self.recent_trades
            if t["status"] == "CLOSED" and t.get("lesson_learned")
        ]
        return [t["lesson_learned"] for t in closed[-n:]]

    # ------------------------------------------------------------------ #
    # Market context digest (for agent prompts)
    # ------------------------------------------------------------------ #

    def get_market_context_digest(self, regime: Optional[str] = None) -> str:
        """Build a compact summary string of recent performance for agent prompts.

        This is injected into the CEO / Risk Critic prompts so the agents have
        awareness of recent trade outcomes, streak direction, and regime
        performance history at decision time — fulfilling the "market memory"
        gap identified in the upgrade plan.

        The digest is deterministic and works in backtest mode (in-memory only).

        Args:
            regime: Current market regime (included in the digest for
                regime-specific context).

        Returns:
            A multi-line summary string, e.g.::

                Recent: WLLWW (last-5 winrate: 60.0%) | Streak: 2W | Regime[TRENDING]: 55.0% | Daily P&L: +$32.50 | Consec losses: 0 | Lessons: 2
        """
        perf = self.get_recent_performance(regime=regime)
        consec_losses = self.consecutive_losses
        consec_wins = self.consecutive_wins
        daily_pnl = self.get_daily_pnl()
        lessons = self.get_recent_lessons(n=3)

        streak_label = (
            f"{consec_wins}W"
            if consec_wins > 0
            else (f"{consec_losses}L" if consec_losses > 0 else "none")
        )

        parts = [
            f"Recent: {perf['recent_streak'] or '-'} (last-5 winrate: {perf['last_5_winrate']:.1f}%)",
            f"Streak: {streak_label}",
        ]
        if regime:
            parts.append(f"Regime[{regime}]: {perf['regime_winrate']:.1f}%")
        parts.append(f"Daily P&L: {'+' if daily_pnl >= 0 else ''}${daily_pnl:.2f}")
        parts.append(f"Consec losses: {consec_losses}")
        if lessons:
            parts.append(f"Lessons: {len(lessons)}")
        return " | ".join(parts)

    # ------------------------------------------------------------------ #
    # Export / persistence
    # ------------------------------------------------------------------ #

    def export_journal(self, filepath: str = "trade_journal.json") -> None:
        """Export the full in-memory journal to JSON for offline analysis.

        Args:
            filepath: Output file path.
        """
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.recent_trades, f, indent=2, default=str, ensure_ascii=False)
        logger.info(f"📖 Trade journal exported to {filepath}")