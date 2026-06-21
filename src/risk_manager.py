"""Risk Management Module: Cooldown, Kill Switch, Adaptive Position Sizing.

This module centralizes all pre-trade risk checks that previously were
scattered across the orchestrator. It is designed to be:
- Backtest-compatible (accepts a current_time parameter for deterministic time)
- Fail-safe (defaults to safe behavior if state is uncertain)
- Composable (orchestrator delegates to RiskManager, not embedded logic)
- Self-contained (works with or without a TradeJournal — maintains internal
  state as fallback when journal is None)

Never imports mt5_connector.py.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)


class RiskManager:
    """Centralized risk management: cooldown, kill switch, risk context.

    Tracks:
    - Consecutive losses (from TradeJournal or internal state)
    - Daily P&L (from TradeJournal or internal state)
    - Cooldown timers (scaled by loss count)
    - Kill switch state (daily loss circuit breaker)

    All time-dependent methods accept an optional ``current_time`` parameter
    so the class behaves identically in backtest and live mode. When
    ``current_time`` is ``None``, ``datetime.utcnow()`` is used.

    If ``journal`` is ``None``, the manager maintains its own internal
    counters (``_consecutive_losses``, ``_consecutive_wins``, ``_daily_pnl``)
    which can be updated via :meth:`record_trade_result`.
    """

    def __init__(
        self,
        journal: Optional[Any] = None,
        daily_loss_limit: float = -100.0,
        cooldown_loss_threshold: int = 2,
        cooldown_base_hours: float = 2.0,
        cooldown_max_hours: float = 8.0,
        current_time: Optional[datetime] = None,
    ):
        """Initialize the RiskManager.

        Args:
            journal: TradeJournal instance (optional). When provided, the
                manager delegates consecutive-loss / daily-pnl queries to it.
                When ``None``, internal state is used and updated via
                :meth:`record_trade_result`.
            daily_loss_limit: Max daily loss in USD (negative number, e.g. -100.0).
            cooldown_loss_threshold: Number of consecutive losses to trigger cooldown.
            cooldown_base_hours: Base cooldown duration in hours.
            cooldown_max_hours: Cap for cooldown duration in hours.
            current_time: Optional initial reference time (for backtests).
        """
        self.journal = journal
        self.daily_loss_limit = daily_loss_limit
        self.cooldown_loss_threshold = cooldown_loss_threshold
        self.cooldown_base_hours = cooldown_base_hours
        self.cooldown_max_hours = cooldown_max_hours

        # Cooldown state
        self.cooldown_until: Optional[datetime] = None
        self.kill_switch_active: bool = False
        self.kill_switch_date: Optional[str] = None  # Date string when kill switch was triggered

        # Internal fallback state (used when journal is None)
        self._consecutive_losses: int = 0
        self._consecutive_wins: int = 0
        self._daily_pnl: float = 0.0
        self._daily_pnl_date: Optional[str] = None

    # ------------------------------------------------------------------
    # Journal-delegated accessors (with internal fallback)
    # ------------------------------------------------------------------

    def _now(self, current_time: Optional[datetime] = None) -> datetime:
        """Return the effective current time."""
        return current_time if current_time is not None else datetime.utcnow()

    def _today(self, current_time: Optional[datetime] = None) -> str:
        """Return today's date string (YYYY-MM-DD)."""
        return str(self._now(current_time))[:10]

    def _current_month(self, current_time: Optional[datetime] = None) -> str:
        """Return the current month string (YYYY-MM)."""
        return str(self._now(current_time))[:7]

    def get_consecutive_losses(self) -> int:
        """Get current consecutive loss count."""
        if self.journal is not None:
            try:
                return int(self.journal.get_consecutive_losses())
            except Exception:
                pass
        return self._consecutive_losses

    def get_consecutive_wins(self) -> int:
        """Get current consecutive win count."""
        if self.journal is not None:
            try:
                return int(self.journal.get_consecutive_wins())
            except Exception:
                pass
        return self._consecutive_wins

    def get_daily_pnl(self, current_time: Optional[datetime] = None) -> float:
        """Get cumulative daily P&L.

        When using internal state, the daily P&L resets on date rollover.
        """
        if self.journal is not None:
            try:
                return float(self.journal.get_daily_pnl())
            except Exception:
                pass
        # Internal fallback: reset on date rollover
        today = self._today(current_time)
        if self._daily_pnl_date != today:
            self._daily_pnl = 0.0
            self._daily_pnl_date = today
        return self._daily_pnl

    def record_trade_result(
        self,
        pnl_usd: float,
        close_reason: str = "",
        current_time: Optional[datetime] = None,
    ) -> None:
        """Update internal fallback state after a trade closes.

        This is only used when ``journal`` is ``None``. When a journal is
        provided, the journal is responsible for updating its own state and
        this method is a no-op for journal-managed counters.

        Args:
            pnl_usd: Profit/loss of the closed trade in USD.
            close_reason: "TP" for win, "SL"/"MANUAL_CLOSE" for loss.
            current_time: Reference time (for backtest determinism).
        """
        today = self._today(current_time)
        if self._daily_pnl_date != today:
            # Date rollover — reset daily P&L
            self._daily_pnl = 0.0
            self._daily_pnl_date = today
        self._daily_pnl += float(pnl_usd)

        # Update streak counters (only when we don't have a journal managing them)
        if self.journal is None:
            if close_reason == "TP" or pnl_usd > 0:
                self._consecutive_wins += 1
                self._consecutive_losses = 0
            elif close_reason in ("SL", "MANUAL_CLOSE") or pnl_usd < 0:
                self._consecutive_losses += 1
                self._consecutive_wins = 0
            # Neutral (pnl == 0 and unknown reason) — don't change streaks

    def reset_daily_state(self, current_time: Optional[datetime] = None) -> None:
        """Reset daily P&L and streak counters (internal fallback mode).

        Useful at the start of a new trading day in backtest mode.
        """
        today = self._today(current_time)
        self._daily_pnl = 0.0
        self._daily_pnl_date = today
        # Note: consecutive losses/wins persist across days (they represent
        # a streak, not a daily counter). Reset them only via record_trade_result.

    # ------------------------------------------------------------------
    # Cooldown
    # ------------------------------------------------------------------

    def check_cooldown(self, current_time: Optional[datetime] = None) -> bool:
        """Check if we're currently in a no-trade cooldown.

        Args:
            current_time: Reference time (backtest timestamp or None for UTC now).

        Returns:
            True if cooldown is active (should NOT trade), False if clear.
        """
        now = self._now(current_time)
        self._reset_daily_kill_switch_if_needed(current_time)

        if self.kill_switch_active:
            return True

        if self.cooldown_until is not None:
            if now < self.cooldown_until:
                return True
            else:
                # Cooldown expired
                self.cooldown_until = None
                return False

        # Check if we need to ENTER cooldown
        consec_losses = self.get_consecutive_losses()
        if consec_losses >= self.cooldown_loss_threshold:
            self._enter_cooldown(consec_losses, current_time=now)
            return True

        return False

    def _enter_cooldown(
        self,
        consec_losses: int,
        current_time: Optional[datetime] = None,
    ) -> None:
        """Enter cooldown for a duration scaled by loss count.

        Duration formula: ``cooldown_base_hours * (loss_count - threshold + 1)``,
        capped at ``cooldown_max_hours``.

        Examples (threshold=2, base=2.0, max=8.0):
            - 2 losses → 2.0 hours
            - 3 losses → 4.0 hours
            - 4 losses → 6.0 hours
            - 5+ losses → 8.0 hours (capped)
        """
        now = self._now(current_time)
        multiplier = consec_losses - self.cooldown_loss_threshold + 1
        hours = min(self.cooldown_base_hours * multiplier, self.cooldown_max_hours)
        self.cooldown_until = now + timedelta(hours=hours)
        logger.warning(
            f"🧊 COOLDOWN ACTIVATED: {consec_losses} consecutive losses → "
            f"no trading for {hours:.1f} hours (until {self.cooldown_until.strftime('%H:%M UTC')})"
        )

    def force_cooldown(
        self,
        hours: float,
        reason: str = "manual",
        current_time: Optional[datetime] = None,
    ) -> None:
        """Manually force a cooldown (e.g. before high-impact news)."""
        now = self._now(current_time)
        self.cooldown_until = now + timedelta(hours=hours)
        logger.info(f"🧊 Manual cooldown for {hours:.1f}h: {reason}")

    # ------------------------------------------------------------------
    # Kill Switch
    # ------------------------------------------------------------------

    def check_kill_switch(self, current_time: Optional[datetime] = None) -> bool:
        """Check if the daily kill switch is active.

        The kill switch triggers when daily P&L falls to or below
        ``daily_loss_limit``. Once triggered, it stays active until the
        date rolls over (UTC midnight or next backtest day).

        Args:
            current_time: Reference time (backtest timestamp or None for UTC now).

        Returns:
            True if kill switch is active (should NOT trade), False if clear.
        """
        self._reset_daily_kill_switch_if_needed(current_time)
        if self.kill_switch_active:
            return True

        # Check if we should trigger the kill switch
        daily_pnl = self.get_daily_pnl(current_time)
        if daily_pnl <= self.daily_loss_limit:
            self.kill_switch_active = True
            self.kill_switch_date = self._today(current_time)
            logger.critical(
                f"🚨 KILL SWITCH ACTIVATED: Daily P&L ${daily_pnl:.2f} <= limit ${self.daily_loss_limit:.2f}. "
                f"Trading halted for the rest of the day."
            )
            return True

        return False

    def _reset_daily_kill_switch_if_needed(self, current_time: Optional[datetime] = None) -> None:
        """Reset kill switch if the date has rolled over."""
        today = self._today(current_time)
        if self.kill_switch_date and self.kill_switch_date != today:
            self.kill_switch_active = False
            self.kill_switch_date = None
            logger.info("🌅 New day — kill switch reset.")

    # ------------------------------------------------------------------
    # Risk Context
    # ------------------------------------------------------------------

    def get_risk_context(self, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get full risk context for the Risk Critic and orchestrator.

        Args:
            current_time: Reference time (backtest timestamp or None for UTC now).

        Returns:
            Dict with:
                - daily_pnl: float
                - daily_loss_limit: float
                - consecutive_losses: int
                - consecutive_wins: int
                - cooldown_active: bool
                - cooldown_until: str or None (ISO format)
                - kill_switch_active: bool
                - max_lot_allowed: float (computed from daily loss limit, or None)
        """
        cooldown_active = self.check_cooldown(current_time)
        kill_switch_active = self.check_kill_switch(current_time)
        daily_pnl = self.get_daily_pnl(current_time)

        # Compute max lot allowed from remaining daily loss budget.
        # This is a soft hint — the actual lot cap is enforced by AdaptivePositionSizer.
        max_lot_allowed: Optional[float] = None
        remaining_budget = self.daily_loss_limit - daily_pnl  # e.g. -100 - (-40) = -60
        # If daily_pnl is negative (losing), remaining budget is how much more we can lose.
        # If positive (winning), the full limit is available.
        # max_lot_allowed is left as None here; the sizer computes the hard cap from balance.
        # We expose the raw budget instead for the critic to reason about.
        if kill_switch_active:
            max_lot_allowed = 0.0
        # else: leave as None — sizer will compute from balance/sl

        return {
            "daily_pnl": daily_pnl,
            "daily_loss_limit": self.daily_loss_limit,
            "consecutive_losses": self.get_consecutive_losses(),
            "consecutive_wins": self.get_consecutive_wins(),
            "cooldown_active": cooldown_active,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "kill_switch_active": kill_switch_active,
            "max_lot_allowed": max_lot_allowed,
            "remaining_loss_budget": remaining_budget,
        }

    # ------------------------------------------------------------------
    # State persistence (for live state save/load)
    # ------------------------------------------------------------------

    def export_state(self) -> Dict[str, Any]:
        """Export serializable state for persistence (e.g. live_state.json)."""
        return {
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "kill_switch_active": self.kill_switch_active,
            "kill_switch_date": self.kill_switch_date,
            "consecutive_losses": self._consecutive_losses,
            "consecutive_wins": self._consecutive_wins,
            "daily_pnl": self._daily_pnl,
            "daily_pnl_date": self._daily_pnl_date,
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        """Import state from a persisted dict (e.g. live_state.json).

        Tolerant of missing keys — only updates fields that are present.
        """
        if not state:
            return
        cu = state.get("cooldown_until")
        if cu:
            try:
                self.cooldown_until = datetime.fromisoformat(cu)
            except (ValueError, TypeError):
                self.cooldown_until = None
        else:
            self.cooldown_until = None
        self.kill_switch_active = bool(state.get("kill_switch_active", False))
        self.kill_switch_date = state.get("kill_switch_date")
        self._consecutive_losses = int(state.get("consecutive_losses", 0))
        self._consecutive_wins = int(state.get("consecutive_wins", 0))
        self._daily_pnl = float(state.get("daily_pnl", 0.0))
        self._daily_pnl_date = state.get("daily_pnl_date")


class AdaptivePositionSizer:
    """Calculates adaptive lot size based on confidence, regime, and recent performance.

    Formula::

        base_lot = balance * risk_pct / (sl_distance * contract_size)
        lot = base_lot * confidence_mult * regime_mult * streak_mult * trajectory_mult * critic_mult

    The class is fully deterministic and makes no AI/LLM calls. It works in
    backtest mode (``USE_MOCK_AI=true``) identically to live mode.

    When ``journal`` is ``None``, streak and trajectory multipliers default
    to ``1.0`` (neutral). When ``optimizer`` is ``None``, regime multipliers
    use hardcoded defaults.
    """

    # Hardcoded regime defaults used when no optimizer is available.
    REGIME_DEFAULTS: Dict[str, float] = {
        "TRENDING": 1.0,
        "RANGING": 0.8,
        "HIGH_VOLATILITY": 0.6,
        "LOW_LIQUIDITY": 0.3,
    }

    def __init__(
        self,
        journal: Optional[Any] = None,
        optimizer: Optional[Any] = None,
        max_risk_per_trade_pct: float = 25.0,
        min_lot: float = 0.01,
    ):
        """Initialize the AdaptivePositionSizer.

        Args:
            journal: TradeJournal instance (optional). Used for streak and
                trajectory multipliers. When ``None``, those multipliers are 1.0.
            optimizer: LearningOptimizer instance (optional). Used for
                regime-specific win-rate lookups. When ``None``, hardcoded
                regime defaults are used.
            max_risk_per_trade_pct: Hard cap on risk per trade as % of balance.
            min_lot: Minimum lot size (floor).
        """
        self.journal = journal
        self.optimizer = optimizer
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.min_lot = min_lot

    def calculate_lot_size(
        self,
        balance: float,
        sl_distance: float,
        contract_size: float,
        confidence: float,
        regime: str,
        base_risk_pct: float,
        critic_lot_mult: float = 1.0,
        fixed_lot: float = 0.0,
        atr_percentile: Optional[float] = None,
    ) -> float:
        """Calculate the final adaptive lot size.

        Args:
            balance: Current account balance (USD).
            sl_distance: Stop-loss distance in USD (price units).
            contract_size: Gold contract size (typically 100.0).
            confidence: CEO confidence (0-1).
            regime: Market regime string (e.g. "TRENDING").
            base_risk_pct: Base risk percentage from Config (e.g. 6.0, 15.0).
            critic_lot_mult: Multiplier from Risk Critic (default 1.0).
            fixed_lot: If > 0, use fixed lot (skip adaptive sizing).
            atr_percentile: Percentile rank of current ATR (0.0-1.0). When ATR
                is in the top 20th percentile (>= 0.80), the lot is reduced by
                30% to account for elevated volatility.

        Returns:
            Final lot size (float, minimum 0.01, rounded to 2 decimals).
        """
        # ── Fixed-lot shortcut ──
        if fixed_lot and float(fixed_lot) > 0:
            lot = float(fixed_lot) * critic_lot_mult
            # ATR-based scaling still applies to fixed lots
            if atr_percentile is not None and atr_percentile >= 0.80:
                lot *= 0.70
                logger.info(
                    f"   📉 ATR LOT SCALING: ATR in top {atr_percentile*100:.0f}th percentile — "
                    f"reducing fixed lot 30% to {lot:.2f}"
                )
            return max(self.min_lot, round(lot, 2))

        # Guard against division by zero
        if sl_distance <= 0 or contract_size <= 0:
            return self.min_lot

        # ── Step 1: Base lot from risk percentage ──
        risk_amount = balance * (base_risk_pct / 100.0)
        base_lot = risk_amount / (sl_distance * contract_size)

        # ── Step 2: Confidence multiplier (tiered) ──
        conf_mult = self._confidence_multiplier(confidence)

        # ── Step 3: Regime multiplier ──
        regime_mult = self._regime_multiplier(regime)

        # ── Step 4: Streak multiplier ──
        streak_mult = self._streak_multiplier()

        # ── Step 5: P&L trajectory multiplier ──
        trajectory_mult = self._trajectory_multiplier()

        # ── Step 6: ATR-based volatility scaling ──
        # If ATR is in the top 20th percentile, reduce lot by 30% to dampen
        # risk during elevated volatility periods.
        atr_mult = 1.0
        if atr_percentile is not None and atr_percentile >= 0.80:
            atr_mult = 0.70
            logger.info(
                f"   📉 ATR LOT SCALING: ATR in top {atr_percentile*100:.0f}th percentile — "
                f"reducing lot 30%"
            )

        # ── Final lot ──
        lot = (
            base_lot
            * conf_mult
            * regime_mult
            * streak_mult
            * trajectory_mult
            * critic_lot_mult
            * atr_mult
        )

        # ── Safety cap: never exceed max_risk_per_trade_pct of balance ──
        max_risk = balance * (self.max_risk_per_trade_pct / 100.0)
        max_lot = max_risk / (sl_distance * contract_size)
        lot = min(lot, max_lot)

        return max(self.min_lot, round(lot, 2))

    # ------------------------------------------------------------------
    # Multiplier methods
    # ------------------------------------------------------------------

    def _confidence_multiplier(self, confidence: float) -> float:
        """Tiered confidence multiplier.

        Preserves the existing orchestrator behavior:
        - >= 0.95 → 3.0x (ultra conviction)
        - >= 0.90 → 2.0x (high conviction)
        - >= 0.85 → 1.5x
        - >= 0.78 → 1.0x (normal)
        - <  0.78 → 0.5x (reduced size — below threshold)

        The ``[OVERRIDE_LOT_MULTIPLIER=3.0]`` text-based override is handled
        separately in the orchestrator (preserving existing behavior).
        """
        if confidence >= 0.95:
            return 3.0
        elif confidence >= 0.90:
            return 2.0
        elif confidence >= 0.85:
            return 1.5
        elif confidence >= 0.78:
            return 1.0
        else:
            return 0.5

    def _regime_multiplier(self, regime: str) -> float:
        """Adjust lot based on regime's recent win rate.

        When an optimizer with a ``db.get_winrate_by_feature()`` method is
        available, the multiplier is derived from historical win rates:

        - >= 60% → 1.2
        - >= 50% → 1.0
        - >= 40% → 0.8
        - <  40% → 0.5

        Otherwise, hardcoded regime defaults are used.
        """
        if self.optimizer is not None:
            try:
                wr_data = self.optimizer.db.get_winrate_by_feature("regime", min_samples=3)
                wr = wr_data.get(regime, 50.0)
                if wr >= 60.0:
                    return 1.2
                elif wr >= 50.0:
                    return 1.0
                elif wr >= 40.0:
                    return 0.8
                else:
                    return 0.5
            except Exception:
                logger.debug("AdaptivePositionSizer: optimizer lookup failed, using defaults")

        return self.REGIME_DEFAULTS.get(regime, 1.0)

    def _streak_multiplier(self) -> float:
        """Reduce after consecutive losses, boost after consecutive wins.

        - 3+ losses → 0.4
        - 2 losses  → 0.6
        - 3+ wins   → 1.15 (small boost, not aggressive)
        - 2 wins    → 1.05
        - otherwise → 1.0
        """
        if self.journal is None:
            return 1.0
        try:
            consec_losses = int(self.journal.get_consecutive_losses())
            consec_wins = int(self.journal.get_consecutive_wins())
            if consec_losses >= 3:
                return 0.4
            elif consec_losses >= 2:
                return 0.6
            elif consec_wins >= 3:
                return 1.15
            elif consec_wins >= 2:
                return 1.05
        except Exception:
            logger.debug("AdaptivePositionSizer: journal streak lookup failed")
        return 1.0

    def _trajectory_multiplier(self) -> float:
        """Adjust based on recent P&L trend (last 5 trades).

        - Positive total P&L → slight increase, capped at 1.1
        - Negative total P&L → reduction, floored at 0.5

        Formula:
            - hot:  min(1.1, 1.0 + total_pnl / 1000.0)
            - cold: max(0.5, 1.0 + total_pnl / 500.0)
        """
        if self.journal is None:
            return 1.0
        try:
            recent_pnl = self.journal.get_recent_pnl(n=5)
            if not recent_pnl:
                return 1.0
            total_pnl = sum(recent_pnl)
            if total_pnl > 0:
                return min(1.1, 1.0 + (total_pnl / 1000.0))
            else:
                return max(0.5, 1.0 + (total_pnl / 500.0))
        except Exception:
            logger.debug("AdaptivePositionSizer: journal trajectory lookup failed")
        return 1.0

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def explain(
        self,
        balance: float,
        sl_distance: float,
        contract_size: float,
        confidence: float,
        regime: str,
        base_risk_pct: float,
        critic_lot_mult: float = 1.0,
        fixed_lot: float = 0.0,
    ) -> Dict[str, Any]:
        """Return a breakdown of all multipliers and the final lot size.

        Useful for logging and debugging. Same parameters as
        :meth:`calculate_lot_size`.
        """
        if fixed_lot and float(fixed_lot) > 0:
            lot = float(fixed_lot) * critic_lot_mult
            return {
                "mode": "fixed",
                "fixed_lot": float(fixed_lot),
                "critic_lot_mult": critic_lot_mult,
                "final_lot": max(self.min_lot, round(lot, 2)),
            }

        risk_amount = balance * (base_risk_pct / 100.0)
        base_lot = risk_amount / (sl_distance * contract_size) if (sl_distance > 0 and contract_size > 0) else 0.0
        conf_mult = self._confidence_multiplier(confidence)
        regime_mult = self._regime_multiplier(regime)
        streak_mult = self._streak_multiplier()
        trajectory_mult = self._trajectory_multiplier()

        lot = base_lot * conf_mult * regime_mult * streak_mult * trajectory_mult * critic_lot_mult
        max_risk = balance * (self.max_risk_per_trade_pct / 100.0)
        max_lot = max_risk / (sl_distance * contract_size) if (sl_distance > 0 and contract_size > 0) else 0.0
        capped = lot > max_lot
        lot = min(lot, max_lot)
        final_lot = max(self.min_lot, round(lot, 2))

        return {
            "mode": "adaptive",
            "balance": balance,
            "sl_distance": sl_distance,
            "contract_size": contract_size,
            "base_risk_pct": base_risk_pct,
            "risk_amount": risk_amount,
            "base_lot": base_lot,
            "confidence": confidence,
            "confidence_mult": conf_mult,
            "regime": regime,
            "regime_mult": regime_mult,
            "streak_mult": streak_mult,
            "trajectory_mult": trajectory_mult,
            "critic_lot_mult": critic_lot_mult,
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "max_lot": max_lot,
            "capped": capped,
            "final_lot": final_lot,
        }