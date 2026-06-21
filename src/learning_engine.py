"""Self-Learning Engine for XAU/USD Trading Bot
 learns from every trade and gets smarter over time.

Key features:
  - SQLite trade database with full market context
  - Win-rate analysis by regime, time, fibo zone, confidence
  - Parameter auto-tuning (SL distance, confidence threshold, position sizing)
  - Dynamic CEO prompt enhancement with stats
  - Weekly reflection that actually changes behavior
"""

import os
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trade_memory.db")
LEARNED_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "learned_config.json")

# ──────────────────────────────────────────────
# SCHEMA
# ──────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket          INTEGER,
    signal          TEXT NOT NULL,           -- BUY / SELL
    entry_price     REAL NOT NULL,
    exit_price      REAL,
    lot_size        REAL NOT NULL,
    stop_loss       REAL,
    take_profit     REAL,
    
    -- Result (populated at close)
    pnl_usd         REAL,
    pnl_pips        REAL,
    close_reason    TEXT,                     -- TP / SL / BREAKEVEN / MANUAL_CLOSE
    r_achieved      REAL,                     -- actual R:R achieved
    
    -- Market context at entry (features for learning)
    regime          TEXT,                     -- TRENDING / RANGING / HIGH_VOLATILITY / LOW_LIQUIDITY
    session         TEXT,                     -- TOKYO / LONDON / NY / ASIA
    fibo_zone       TEXT,                     -- equilibrium / discount_premium / all_in_market_maker / neutral
    macd_state      TEXT,                     -- bullish_cross / bearish_cross / neutral
    confidence      REAL,                     -- CEO confidence 0-1
    ceo_reasoning   TEXT,
    lot_multiplier  REAL DEFAULT 1.0,         -- 1.0, 2.0, 3.0
    
    -- Metadata
    entry_time      TEXT NOT NULL,
    exit_time       TEXT,
    lesson_learned  TEXT,
    week_number     INTEGER,                  -- ISO week for grouping
    year            INTEGER,
    
    UNIQUE(ticket)
);

CREATE TABLE IF NOT EXISTS weekly_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    week_number     INTEGER NOT NULL,
    year            INTEGER NOT NULL,
    total_trades    INTEGER DEFAULT 0,
    wins            INTEGER DEFAULT 0,
    losses          INTEGER DEFAULT 0,
    total_pnl       REAL DEFAULT 0.0,
    avg_confidence  REAL DEFAULT 0.0,
    best_regime     TEXT,
    worst_regime    TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(week_number, year)
);

CREATE TABLE IF NOT EXISTS feature_winrates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_name    TEXT NOT NULL,            -- e.g. 'regime', 'session', 'fibo_zone', 'confidence_bucket'
    feature_value   TEXT NOT NULL,            -- e.g. 'TRENDING', 'TOKYO', 'equilibrium'
    total_trades    INTEGER DEFAULT 0,
    wins            INTEGER DEFAULT 0,
    winrate         REAL DEFAULT 0.0,
    last_updated    TEXT DEFAULT (datetime('now')),
    UNIQUE(feature_name, feature_value)
);

CREATE TABLE IF NOT EXISTS parameter_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    updated_at      TEXT DEFAULT (datetime('now')),
    param_name      TEXT NOT NULL,
    old_value       REAL,
    new_value       REAL,
    reason          TEXT
);
"""


class TradeDatabase:
    """SQLite database for persisting trade history with full context."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()
        logger.info(f"🗄️ Trade database ready: {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_entry(self, trade_data: Dict) -> int:
        """Record a trade when it's opened. Returns trade ID."""
        now = datetime.utcnow()
        week = now.isocalendar()[1]
        
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO trades 
                (ticket, signal, entry_price, lot_size, stop_loss, take_profit,
                 regime, session, fibo_zone, macd_state, confidence, ceo_reasoning,
                 lot_multiplier, entry_time, week_number, year)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_data.get("ticket"),
                    trade_data["signal"],
                    trade_data["entry_price"],
                    trade_data["lot_size"],
                    trade_data.get("stop_loss"),
                    trade_data.get("take_profit"),
                    trade_data.get("regime"),
                    self._classify_session(trade_data.get("entry_time", str(now))),
                    trade_data.get("fibo_zone"),
                    trade_data.get("macd_state"),
                    trade_data.get("confidence"),
                    trade_data.get("ceo_reasoning"),
                    trade_data.get("lot_multiplier", 1.0),
                    trade_data.get("entry_time", str(now)),
                    week,
                    now.year
                )
            )
            conn.commit()
            trade_id = cursor.lastrowid
            logger.info(f"📝 Trade #{trade_id} recorded in learning DB")
            return trade_id
        finally:
            conn.close()

    def record_exit(self, ticket: Optional[int], exit_data: Dict):
        """Update a trade with exit/close information."""
        conn = self._get_conn()
        try:
            now = datetime.utcnow()
            pnl_usd = exit_data.get("pnl_usd", 0)
            entry_price = exit_data.get("entry_price", 0)
            exit_price = exit_data.get("exit_price", 0)
            signal = exit_data.get("signal", "BUY")
            
            if entry_price and exit_price:
                price_move = exit_price - entry_price if signal == "BUY" else entry_price - exit_price
                sl_distance = exit_data.get("sl_distance")
                if sl_distance and sl_distance > 0:
                    r_achieved = price_move / sl_distance
                else:
                    r_achieved = price_move / max(abs(price_move), 0.01)
            else:
                r_achieved = 0.0

            conn.execute(
                """UPDATE trades SET
                    exit_price = ?, pnl_usd = ?, pnl_pips = ?,
                    close_reason = ?, r_achieved = ?, lesson_learned = ?,
                    exit_time = ?
                WHERE ticket = ? OR (ticket IS NULL AND id = ?)""",
                (
                    exit_price, pnl_usd, exit_data.get("pnl_pips", 0),
                    exit_data.get("close_reason"), r_achieved,
                    exit_data.get("lesson", ""),
                    str(now),
                    ticket, exit_data.get("trade_db_id", 0)
                )
            )
            conn.commit()
            logger.info(f"📝 Trade #{ticket or '?'} - P&L: ${pnl_usd:.2f} - updated in learning DB")
            
            # Auto-update feature winrates
            self._update_feature_winrates(ticket, exit_data.get("close_reason", ""))
            
        finally:
            conn.close()

    def _classify_session(self, time_str: str) -> str:
        """Classify trading session from UTC time."""
        try:
            dt = datetime.fromisoformat(str(time_str).replace(' ', 'T'))
            h = dt.hour
        except:
            return "UNKNOWN"
        if 0 <= h < 4:
            return "ASIA"
        elif 4 <= h < 10:
            return "TOKYO_LONDON"
        elif 10 <= h < 12:
            return "LONDON"
        elif 12 <= h < 18:
            return "NY"
        else:
            return "NY_LATE"

    def _update_feature_winrates(self, ticket: Optional[int], close_reason: str):
        """Update win rate stats for all features of a closed trade."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT regime, session, fibo_zone, macd_state, confidence FROM trades WHERE ticket = ? OR id = ?",
                (ticket, ticket)
            ).fetchone()
            if not row:
                return

            is_win = close_reason == "TP"
            features = {
                "regime": row["regime"],
                "session": row["session"],
                "fibo_zone": row["fibo_zone"],
                "macd_state": row["macd_state"],
                "confidence_bucket": self._bucket_confidence(row["confidence"]),
            }

            for fname, fvalue in features.items():
                if not fvalue or fvalue == "UNKNOWN":
                    continue
                conn.execute(
                    """INSERT INTO feature_winrates (feature_name, feature_value, total_trades, wins, winrate)
                    VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(feature_name, feature_value) DO UPDATE SET
                        total_trades = total_trades + 1,
                        wins = CASE WHEN ? THEN wins + 1 ELSE wins END,
                        winrate = CAST(
                            (CASE WHEN ? THEN wins + 1 ELSE wins END) AS REAL
                        ) / (total_trades + 1),
                        last_updated = datetime('now')""",
                    (fname, fvalue, 1 if is_win else 0, 
                     float(is_win),  # cast for winrate
                     is_win, is_win)
                )
            conn.commit()
        finally:
            conn.close()

    def _bucket_confidence(self, conf: Optional[float]) -> str:
        if conf is None:
            return "UNKNOWN"
        if conf >= 0.95:
            return "ULTRA_HIGH"
        elif conf >= 0.90:
            return "HIGH"
        elif conf >= 0.85:
            return "MODERATE_HIGH"
        elif conf >= 0.78:
            return "MIN_THRESHOLD"
        else:
            return "LOW"

    def get_winrate_by_feature(self, feature: str, min_samples: int = 3) -> Dict[str, float]:
        """Get win rates for a specific feature (e.g. 'regime')."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT feature_value, total_trades, winrate 
                FROM feature_winrates 
                WHERE feature_name = ? AND total_trades >= ?
                ORDER BY winrate DESC""",
                (feature, min_samples)
            ).fetchall()
            return {r["feature_value"]: r["winrate"] * 100 for r in rows}
        finally:
            conn.close()

    def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """Get most recent trades for analysis."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_period_stats(self, days: int = 14) -> Dict:
        """Get summary stats for the last N days."""
        conn = self._get_conn()
        try:
            since = (datetime.utcnow() - timedelta(days=days)).isoformat()
            rows = conn.execute(
                """SELECT signal, close_reason, pnl_usd, r_achieved, confidence, regime
                FROM trades WHERE entry_time >= ?""",
                (since,)
            ).fetchall()
            
            total = len(rows)
            wins = sum(1 for r in rows if r["close_reason"] == "TP")
            losses = sum(1 for r in rows if r["close_reason"] in ("SL", "MANUAL_CLOSE"))
            total_pnl = sum(r["pnl_usd"] or 0 for r in rows)
            avg_r = 0.0
            if wins + losses > 0:
                avg_r = sum(r["r_achieved"] or 0 for r in rows if r["close_reason"]) / (wins + losses)
            
            return {
                "period_days": days,
                "total_trades": total,
                "wins": wins,
                "losses": losses,
                "winrate": (wins / total * 100) if total > 0 else 0,
                "total_pnl": total_pnl,
                "avg_r": avg_r,
                "best_trade": max([r["pnl_usd"] or 0 for r in rows] + [0]),
                "worst_trade": min([r["pnl_usd"] or 0 for r in rows] + [0]),
            }
        finally:
            conn.close()


class LearningOptimizer:
    """Analyzes trade history and adjusts trading parameters to improve performance."""

    def __init__(self, db: TradeDatabase, config_path: str = LEARNED_CONFIG_PATH):
        self.db = db
        self.config_path = config_path
        self.params = self._load_or_default()

    def _load_or_default(self) -> Dict:
        """Load learned config or create defaults."""
        defaults = {
            "version": 1,
            "last_updated": datetime.utcnow().isoformat(),
            "total_trades_analyzed": 0,

            # Confidence thresholds (by regime)
            "confidence_threshold": {
                "TRENDING": 0.78,
                "RANGING": 0.82,
                "HIGH_VOLATILITY": 0.85,
                "LOW_LIQUIDITY": 0.90,
                "DEFAULT": 0.78,
            },

            # SL/TP adjustments (multipliers on ATR)
            "sl_atr_multiplier": 1.0,
            "rr_ratio": 3.0,

            # Position sizing (% of balance per trade)
            "position_size_pct": {
                "TRENDING": 6.0,
                "RANGING": 4.0,
                "HIGH_VOLATILITY": 3.0,
                "LOW_LIQUIDITY": 2.0,
                "DEFAULT": 5.0,
            },

            # Session bias
            "session_multiplier": {
                "TOKYO_LONDON": 1.0,
                "LONDON": 1.0,
                "NY": 1.0,
                "NY_LATE": 0.7,
                "ASIA": 0.5,
            },

            # Feature-based multipliers (0.0 = block, 1.0 = neutral, >1 = encourage)
            "fibo_zone_bias": {
                "equilibrium": 1.0,
                "discount_premium": 1.2,
                "all_in_market_maker": 1.5,
                "neutral": 0.8,
            },

            # Win-rate tracking
            "overall_winrate": 0.0,
            "consecutive_losses": 0,
        }

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
                    logger.info(f"📖 Loaded learned config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load learned config: {e}")

        return defaults

    def save(self):
        """Persist learned config to disk."""
        self.params["last_updated"] = datetime.utcnow().isoformat()
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.params, f, indent=2)
        logger.info(f"💾 Learned config saved to {self.config_path}")

    def analyze_and_optimize(self):
        """Main optimization routine: analyze recent trades and adjust parameters."""
        logger.info(f"\n{'='*50}")
        logger.info("🧠 LEARNING ENGINE: Analyzing trade history...")
        
        trades = self.db.get_recent_trades(100)
        closed = [t for t in trades if t.get("close_reason")]
        
        if len(closed) < self.params.get("total_trades_analyzed") + 1:
            logger.info("No new trades since last analysis. Skipping optimization.")
            self._check_consecutive_losses(closed)
            return

        logger.info(f"📊 Analyzing {len(closed)} closed trades...")
        self.params["total_trades_analyzed"] = len(closed)

        # 1. Optimize confidence thresholds by regime
        self._optimize_confidence_by_regime(closed)

        # 2. Optimize position sizing by regime
        self._optimize_position_sizing(closed)

        # 3. Optimize SL/TP
        self._optimize_sl_tp(closed)

        # 4. Update session bias
        self._optimize_session_bias(closed)

        # 5. Update fibo zone bias
        self._update_fibo_bias(closed)

        # 6. Calculate overall win rate
        self._update_overall_stats(closed)

        # 7. Check consecutive losses → auto-cool-off
        self._check_consecutive_losses(closed)

        self.save()

    def _optimize_confidence_by_regime(self, trades: List[Dict]):
        """Adjust confidence threshold per regime based on recent win rates."""
        regime_stats = {}
        for t in trades:
            regime = t.get("regime", "DEFAULT")
            if regime not in regime_stats:
                regime_stats[regime] = {"total": 0, "wins": 0}
            regime_stats[regime]["total"] += 1
            if t.get("close_reason") == "TP":
                regime_stats[regime]["wins"] += 1

        for regime, stats in regime_stats.items():
            if stats["total"] < 3:
                continue
            wr = stats["wins"] / stats["total"]
            
            old_threshold = self.params["confidence_threshold"].get(regime, 0.78)
            
            if wr < 0.35 and stats["total"] >= 5:
                # Poor performance → raise threshold to be more selective
                new_threshold = min(old_threshold + 0.04, 0.95)
                self._log_param_change(f"confidence_threshold.{regime}", old_threshold, new_threshold,
                    f"Win rate {wr*100:.0f}% < 35% — being more selective")
                self.params["confidence_threshold"][regime] = new_threshold
                
            elif wr > 0.65 and old_threshold > 0.75:
                # Good performance → slightly lower threshold to take more trades
                new_threshold = max(old_threshold - 0.02, 0.72)
                self._log_param_change(f"confidence_threshold.{regime}", old_threshold, new_threshold,
                    f"Win rate {wr*100:.0f}% > 65% — relaxing threshold")
                self.params["confidence_threshold"][regime] = new_threshold

        logger.info(f"   📈 Optimized confidence thresholds per regime")

    def _optimize_position_sizing(self, trades: List[Dict]):
        """Adjust position size per regime based on risk-adjusted returns."""
        regime_stats = {}
        for t in trades:
            regime = t.get("regime", "DEFAULT")
            if regime not in regime_stats:
                regime_stats[regime] = {"total": 0, "wins": 0, "pnl": [], "r_values": []}
            regime_stats[regime]["total"] += 1
            if t.get("close_reason") == "TP":
                regime_stats[regime]["wins"] += 1
            if t.get("r_achieved") is not None:
                regime_stats[regime]["r_values"].append(t["r_achieved"])

        for regime, stats in regime_stats.items():
            if stats["total"] < 3:
                continue
            wr = stats["wins"] / stats["total"]
            avg_r = sum(stats["r_values"]) / len(stats["r_values"]) if stats["r_values"] else 0
            expectancy = (wr * avg_r) - ((1 - wr) * 1.0)  # Kelly-like: WR*avgR - (1-WR)*1
            
            current_pct = self.params["position_size_pct"].get(regime, 5.0)
            
            if expectancy > 0.5 and stats["total"] >= 5:
                # Strong edge → increase size
                new_pct = min(current_pct + 1.0, 10.0)
                self._log_param_change(f"position_size_pct.{regime}", current_pct, new_pct,
                    f"Expectancy {expectancy:.2f} — increasing size")
                self.params["position_size_pct"][regime] = new_pct
                
            elif expectancy < 0 and stats["total"] >= 5:
                # Negative edge → reduce size
                new_pct = max(current_pct - 1.0, 1.0)
                self._log_param_change(f"position_size_pct.{regime}", current_pct, new_pct,
                    f"Expectancy {expectancy:.2f} — reducing exposure")
                self.params["position_size_pct"][regime] = new_pct

        logger.info(f"   📈 Optimized position sizing per regime")

    def _optimize_sl_tp(self, trades: List[Dict]):
        """Adjust SL multiplier and R:R ratio."""
        closed_trades = [t for t in trades if t.get("r_achieved") is not None and t.get("close_reason")]
        if len(closed_trades) < 5:
            return

        avg_r = sum(t["r_achieved"] for t in closed_trades) / len(closed_trades)
        current_rr = self.params.get("rr_ratio", 3.0)
        current_sl = self.params.get("sl_atr_multiplier", 1.0)
        
        # If actual R:R is consistently below target, widen SL
        if avg_r < current_rr * 0.7 and len(closed_trades) >= 10:
            new_sl = min(current_sl * 1.15, 1.5)
            self._log_param_change("sl_atr_multiplier", current_sl, new_sl,
                f"Avg achieved R {avg_r:.1f} < target {current_rr} — widening SL")
            self.params["sl_atr_multiplier"] = new_sl
        
        # If actual R:R is consistently above target, tighten SL to improve WR
        elif avg_r > current_rr * 1.3 and len(closed_trades) >= 10:
            new_sl = max(current_sl * 0.9, 0.7)
            self._log_param_change("sl_atr_multiplier", current_sl, new_sl,
                f"Avg R {avg_r:.1f} > target {current_rr} — tightening SL")
            self.params["sl_atr_multiplier"] = new_sl

        logger.info(f"   📈 Avg achieved R:R = {avg_r:.2f} (target: {current_rr})")

    def _optimize_session_bias(self, trades: List[Dict]):
        """Adjust session multipliers based on win rates."""
        session_stats = {}
        for t in trades:
            sess = t.get("session", "UNKNOWN")
            if sess not in session_stats:
                session_stats[sess] = {"total": 0, "wins": 0}
            session_stats[sess]["total"] += 1
            if t.get("close_reason") == "TP":
                session_stats[sess]["wins"] += 1

        for sess, stats in session_stats.items():
            if stats["total"] < 3:
                continue
            wr = stats["wins"] / stats["total"]
            current = self.params["session_multiplier"].get(sess, 1.0)
            
            # Win rate drops below 30% → reduce size in this session
            if wr < 0.30:
                new_mult = max(current - 0.15, 0.3)
                self._log_param_change(f"session_multiplier.{sess}", current, new_mult,
                    f"Session win rate {wr*100:.0f}% — reducing")
                self.params["session_multiplier"][sess] = new_mult
            elif wr > 0.60 and current < 1.2:
                new_mult = min(current + 0.1, 1.5)
                self._log_param_change(f"session_multiplier.{sess}", current, new_mult,
                    f"Session win rate {wr*100:.0f}% — increasing")
                self.params["session_multiplier"][sess] = new_mult

    def _update_fibo_bias(self, trades: List[Dict]):
        """Update Fibo zone biases based on performance."""
        zone_stats = {}
        for t in trades:
            zone = t.get("fibo_zone", "neutral")
            if zone not in zone_stats:
                zone_stats[zone] = {"total": 0, "wins": 0}
            zone_stats[zone]["total"] += 1
            if t.get("close_reason") == "TP":
                zone_stats[zone]["wins"] += 1

        for zone, stats in zone_stats.items():
            if stats["total"] < 3:
                continue
            wr = stats["wins"] / stats["total"]
            current = self.params["fibo_zone_bias"].get(zone, 1.0)
            
            if wr < 0.30:
                new_bias = max(current - 0.2, 0.3)
                self.params["fibo_zone_bias"][zone] = new_bias
            elif wr > 0.60 and current < 1.5:
                self.params["fibo_zone_bias"][zone] = min(current + 0.15, 2.0)

    def _update_overall_stats(self, trades: List[Dict]):
        """Update overall win rate tracking."""
        closed = [t for t in trades if t.get("close_reason") in ("TP", "SL", "BREAKEVEN")]
        if not closed:
            return
        wins = sum(1 for t in closed if t["close_reason"] == "TP")
        self.params["overall_winrate"] = wins / len(closed) * 100

    def _check_consecutive_losses(self, trades: List[Dict]):
        """Count consecutive losses and auto-reduce risk."""
        closed = [t for t in trades if t.get("close_reason")]
        consecutive = 0
        for t in closed:
            if t["close_reason"] == "TP":
                consecutive = 0
            elif t["close_reason"] == "SL":
                consecutive += 1
        
        self.params["consecutive_losses"] = consecutive
        
        if consecutive >= 3:
            logger.warning(f"⚠️ {consecutive} consecutive losses! Auto-reducing risk...")
            # Reduce default position size by 50% during losing streak
            for regime in self.params["position_size_pct"]:
                current = self.params["position_size_pct"][regime]
                self.params["position_size_pct"][regime] = max(current * 0.7, 1.0)

    def _log_param_change(self, name: str, old_val: float, new_val: float, reason: str):
        """Log parameter change for audit trail."""
        logger.info(f"   🔧 PARAM CHANGE: {name}: {old_val:.3f} → {new_val:.3f} ({reason})")
        
        conn = sqlite3.connect(self.db.db_path)
        try:
            conn.execute(
                """INSERT INTO parameter_history (param_name, old_value, new_value, reason)
                VALUES (?, ?, ?, ?)""",
                (name, old_val, new_val, reason)
            )
            conn.commit()
        finally:
            conn.close()

    def get_enhanced_ceo_context(self) -> str:
        """Generate a dynamic context string for the CEO prompt with current stats."""
        lines = [
            "📊 **LEARNING ENGINE — LIVE STATS:**",
            f"📈 Overall Win Rate: {self.params['overall_winrate']:.1f}%",
            f"⚠️ Consecutive Losses: {self.params['consecutive_losses']}",
        ]
        
        # Regime win rates
        for regime in ["TRENDING", "RANGING", "HIGH_VOLATILITY"]:
            wr_data = self.db.get_winrate_by_feature("regime")
            if regime in wr_data:
                lines.append(f"🏷️ Win Rate in {regime}: {wr_data[regime]:.0f}%")
        
        # Session win rates
        session_wr = self.db.get_winrate_by_feature("session")
        for sess, wr in session_wr.items():
            lines.append(f"🕐 Win Rate in {sess}: {wr:.0f}%")
        
        # Current parameter overrides
        lines.append(f"\n⚙️ **Current Parameter Overrides:**")
        for regime, threshold in self.params["confidence_threshold"].items():
            if regime != "DEFAULT" and threshold != 0.78:
                lines.append(f"  - {regime}: confidence >= {threshold*100:.0f}%")
        
        lines.append(f"  - SL Multiplier: {self.params['sl_atr_multiplier']:.2f}x ATR")
        lines.append(f"  - R:R Target: {self.params['rr_ratio']:.1f}")
        
        return "\n".join(lines)

    def get_reflection_report(self, period_days: int = 7) -> str:
        """Generate an actual meaningful weekly reflection report."""
        stats = self.db.get_period_stats(days=period_days)
        trades = self.db.get_recent_trades(20)
        
        report = []
        report.append(f"📊 **รายงานทบทวนการเทรดทองคำ (XAU/USD Weekly Reflection)**")
        report.append(f"ประจำวันที่ {datetime.utcnow().strftime('%d %b %Y %H:%M')} UTC")
        report.append(f"")
        report.append(f"**📈 ผลงานรอบ {period_days} วันที่ผ่านมา:**")
        report.append(f"├─ ออเดอร์ทั้งหมด: **{stats['total_trades']}** ไม้")
        report.append(f"├─ ชนะ: **{stats['wins']}** ไม้")
        report.append(f"├─ แพ้: **{stats['losses']}** ไม้")
        report.append(f"├─ Win Rate: **{stats['winrate']:.1f}%**")
        report.append(f"├─ กำไร/ขาดทุนรวม: **${stats['total_pnl']:+.2f}**")
        report.append(f"├─ Avg R:R: **{stats['avg_r']:.2f}**")
        report.append(f"├─ เทรดที่ดีที่สุด: **+${stats['best_trade']:.2f}**")
        report.append(f"└─ เทรดที่แย่ที่สุด: **${stats['worst_trade']:.2f}**")
        report.append(f"")
        
        # Win rates by feature
        report.append(f"**🔍 Win Rate Breakdown:**")
        for feature in ["regime", "session", "fibo_zone"]:
            wr = self.db.get_winrate_by_feature(feature, min_samples=2)
            if wr:
                report.append(f"├─ **{feature}**:")
                for value, pct in wr.items():
                    emoji = "🟢" if pct >= 50 else "🔴"
                    report.append(f"│  {emoji} {value}: {pct:.0f}% ({'กำลังดี' if pct >= 50 else 'ต้องปรับปรุง'})")
        
        report.append(f"")
        
        # Parameter changes
        report.append(f"**⚙️ การปรับพารามิเตอร์อัตโนมัติ:**")
        
        # Session bias changes
        for sess, mult in self.params["session_multiplier"].items():
            if mult != 1.0:
                direction = "เพิ่ม" if mult > 1.0 else "ลด"
                report.append(f"├─ {sess}: {direction} น้ำหนักเป็น {mult:.1f}x")
        
        # Regime threshold changes
        for regime, thresh in self.params["confidence_threshold"].items():
            if regime != "DEFAULT":
                default = 0.78
                if abs(thresh - default) > 0.02:
                    direction = "เพิ่ม" if thresh > default else "ลด"
                    report.append(f"├─ {regime}: {direction} ความมั่นใจขั้นต่ำเป็น {thresh*100:.0f}%")
        
        report.append(f"├─ SL Multiplier: {self.params['sl_atr_multiplier']:.2f}x")
        report.append(f"└─ Consecutive Losses: {self.params['consecutive_losses']}")
        
        report.append(f"")
        report.append(f"**🧠 สรุปบทเรียน (Lessons Learned):**")
        
        # Generate lessons from recent losses
        recent_losses = [t for t in trades if t.get("close_reason") == "SL"][:3]
        if recent_losses:
            for i, loss in enumerate(recent_losses, 1):
                lesson = loss.get("lesson_learned", "") or ""
                short_lesson = lesson[:150] + "..." if len(lesson) > 150 else lesson
                report.append(f"{i}. 💔 SL ที่ ${loss.get('exit_price', 0):.2f} (ขาดทุน ${abs(loss.get('pnl_usd', 0)):.2f}) — {short_lesson}")
        else:
            report.append("🎉 ไม่มีการขาดทุนในรอบนี้!")
        
        # Consecutive loss warning
        if self.params["consecutive_losses"] >= 3:
            report.append(f"")
            report.append(f"⚠️ **⚠️ คำเตือน: ติดลบติดต่อกัน {self.params['consecutive_losses']} ครั้งแล้ว!**")
            report.append(f"⚠️ ระบบลดขนาด Lot ลง 30% อัตโนมัติเพื่อรักษาพอร์ต")
        
        report.append(f"")
        report.append(f"🤖 **Self-Learning System** v{self.params['version']} • ทำงานทุกครั้งที่มีการปิดออเดอร์")
        
        return "\n".join(report)


# ──────────────────────────────────────────────
# Patch: extend DiscordReporter with learning report
# ──────────────────────────────────────────────

def patch_discord_reporter():
    """Add learning report methods to DiscordReporter at runtime."""
    from discord_reporter import DiscordReporter
    
    def report_learning_summary(self, optimizer: LearningOptimizer, period_days: int = 7):
        """Send a learning summary to the weekly reflection webhook."""
        report = optimizer.get_reflection_report(period_days)
        webhook_url = os.getenv("DISCORD_WEEKLY_REFLECTION_WEBHOOK", "")
        if not webhook_url:
            webhook_url = os.getenv("DISCORD_GOLD_REFLECTION_WEBHOOK", "")
        
        if not webhook_url:
            logger.warning("No weekly reflection webhook URL configured.")
            return False
        
        payload = {
            "content": report[:4000],
            "username": "🧠 Auto-Learning System",
        }
        
        return self._send_to_url(webhook_url, payload)
    
    DiscordReporter.report_learning_summary = report_learning_summary
    logger.info("🧠 Patched DiscordReporter with learning_summary method")


# Initialize singleton
_db = None
_optimizer = None

def get_db() -> TradeDatabase:
    global _db
    if _db is None:
        _db = TradeDatabase()
    return _db

def get_optimizer() -> LearningOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = LearningOptimizer(get_db())
    return _optimizer

def run_optimization():
    """Run full learning cycle."""
    opt = get_optimizer()
    opt.analyze_and_optimize()
    return opt