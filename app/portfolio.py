"""portfolio.py — V5: progressive exits on YES rising (espejo de V2).

Exit stages per position:
  0 = open
  1 = first 50% sold at EXIT_1_THRESHOLD (YES ≥ 0.31)
  2 = second 50% sold at EXIT_2_THRESHOLD (YES ≥ 0.37)
  3 = fully closed at EXIT_3_THRESHOLD (YES ≥ 0.43)

Stop-loss: fixed drop of STOP_LOSS_DROP (5¢) from entry_yes.
WON: YES ≥ 0.99 (event happened — jackpot).
LOST: NO ≥ 0.99 (event didn't happen).
"""

import threading
from collections import defaultdict
from app.scanner import now_utc
from app.config import (
    MAX_POSITIONS,
    STOP_LOSS_DROP,
    EXIT_1_THRESHOLD,
    EXIT_2_THRESHOLD,
    EXIT_3_THRESHOLD,
    REGION_MAP, MAX_REGION_EXPOSURE,
)


class AutoPortfolio:
    def __init__(self, initial_capital):
        self.lock = threading.Lock()
        self.capital_inicial = initial_capital
        self.capital_total = initial_capital
        self.capital_disponible = initial_capital
        self.positions = {}
        self.closed_positions = []
        self.session_start = now_utc()
        self.capital_history = [
            {"time": now_utc().isoformat(), "capital": initial_capital}
        ]

    def can_open_position(self):
        return (len(self.positions) < MAX_POSITIONS and
                self.capital_disponible >= 1)

    def open_position(self, opp, amount):
        yes_price = opp["yes_price"]
        tokens = amount / yes_price
        max_gain = tokens * 1.0 - amount  # si YES llega a 1.00

        pos = {
            **opp,
            "entry_time":    now_utc().isoformat(),
            "entry_yes":     yes_price,
            "current_yes":   yes_price,
            "allocated":     amount,
            "tokens":        tokens,
            "max_gain":      max_gain,
            "exit_stage":    0,
            "status":        "OPEN",
            "pnl":           0.0,
        }
        self.positions[opp["condition_id"]] = pos
        self.capital_disponible -= amount
        return True

    def apply_price_updates(self, price_map):
        """Apply {cid: (yes_price, no_price)} and handle resolutions + stop loss.
        Must be called with self.lock held."""
        to_close = []

        for cid, (yes_price, no_price) in price_map.items():
            if cid not in self.positions:
                continue
            pos = self.positions[cid]
            pos["current_yes"] = yes_price

            # 1. YES resolvió → WON (el evento ocurrió)
            if yes_price >= 0.99:
                sale_value = pos["tokens"] * yes_price
                pnl = sale_value - pos["allocated"]
                resolution = f"YES resolvió — evento ocurrió (YES={yes_price*100:.1f}¢)"
                to_close.append((cid, "WON", pnl, resolution))

            # 2. NO resolvió → LOST (el evento no ocurrió)
            elif no_price >= 0.99:
                resolution = f"NO resolvió — evento no ocurrió (NO={no_price*100:.1f}¢)"
                to_close.append((cid, "LOST", -pos["allocated"], resolution))

            # 3. Stop loss: YES cae STOP_LOSS_DROP desde entrada
            else:
                drop = yes_price - pos["entry_yes"]
                if drop <= -STOP_LOSS_DROP:
                    sale_value = pos["tokens"] * yes_price
                    realized_loss = sale_value - pos["allocated"]
                    resolution = (
                        f"Stop loss @ YES={yes_price*100:.1f}¢ "
                        f"(entrada {pos['entry_yes']*100:.1f}¢, caída {-drop*100:.1f}¢)"
                    )
                    to_close.append((cid, "STOPPED", realized_loss, resolution))

        for cid, status, pnl, resolution in to_close:
            self._close_position(cid, status, pnl, resolution)

    def _close_position(self, cid, status, pnl, resolution=""):
        if cid not in self.positions:
            return
        pos = self.positions[cid]
        pos["status"] = status
        pos["pnl"] = pnl
        pos["close_time"] = now_utc().isoformat()
        pos["resolution"] = resolution

        recovered = pos["allocated"] + pnl
        self.capital_disponible += recovered
        self.capital_total += pnl

        self.closed_positions.append(pos.copy())
        del self.positions[cid]

    # ── Progressive 3-stage exits ─────────────────────────────────────────────

    def check_progressive_exits(self):
        """Evaluate each position for the next exit stage (YES rising).

        Stage 0 → 1: sell 50% when YES ≥ EXIT_1_THRESHOLD (0.31)
        Stage 1 → 2: sell 50% of remaining when YES ≥ EXIT_2_THRESHOLD (0.37)
        Stage 2 → 3: close all when YES ≥ EXIT_3_THRESHOLD (0.43)
        """
        for cid, pos in list(self.positions.items()):
            stage = pos.get("exit_stage", 0)
            current_yes = pos["current_yes"]

            if stage == 0 and current_yes >= EXIT_1_THRESHOLD:
                self._partial_exit(cid, fraction=0.50, new_stage=1, label="PARTIAL_1")
            elif stage == 1 and current_yes >= EXIT_2_THRESHOLD:
                self._partial_exit(cid, fraction=0.50, new_stage=2, label="PARTIAL_2")
            elif stage == 2 and current_yes >= EXIT_3_THRESHOLD:
                remaining_pnl = pos["tokens"] * current_yes - pos["allocated"]
                self._close_position(
                    cid, "WON", remaining_pnl,
                    resolution=(
                        f"Tramo 3: cierre total @ YES={current_yes*100:.1f}¢ "
                        f"(umbral {EXIT_3_THRESHOLD*100:.0f}¢)"
                    ),
                )

    def _partial_exit(self, cid, fraction, new_stage, label):
        pos = self.positions[cid]
        tokens_sold = pos["tokens"] * fraction
        sale_value = tokens_sold * pos["current_yes"]
        cost_fraction = pos["allocated"] * fraction
        realized_pnl = sale_value - cost_fraction

        pos["tokens"]    *= (1 - fraction)
        pos["allocated"] *= (1 - fraction)
        pos["max_gain"]  *= (1 - fraction)
        pos["exit_stage"] = new_stage

        self.capital_disponible += cost_fraction + realized_pnl
        self.capital_total += realized_pnl

        self.closed_positions.append({
            "question":   pos["question"],
            "city":       pos.get("city", ""),
            "condition_id": cid,
            "entry_yes":  pos["entry_yes"],
            "allocated":  round(cost_fraction, 2),
            "pnl":        round(realized_pnl, 2),
            "status":     label,
            "resolution": (
                f"Salida {label}: {int(fraction*100)}% tokens @ YES={pos['current_yes']*100:.1f}¢"
            ),
            "entry_time": pos["entry_time"],
            "close_time": now_utc().isoformat(),
        })

    # ── Region exposure ───────────────────────────────────────────────────────

    def get_region_allocated(self, region):
        return sum(
            pos["allocated"]
            for pos in self.positions.values()
            if REGION_MAP.get(pos.get("city", ""), "other") == region
        )

    def region_has_capacity(self, city):
        region = REGION_MAP.get(city, "other")
        return self.get_region_allocated(region) < self.capital_total * MAX_REGION_EXPOSURE

    # ── Learning insights ─────────────────────────────────────────────────────

    def compute_insights(self):
        exclude = {"PARTIAL_1", "PARTIAL_2", "LIQUIDATED"}
        closed = [p for p in self.closed_positions if p["status"] not in exclude]
        if len(closed) < 5:
            return None

        by_hour = defaultdict(lambda: {"won": 0, "total": 0})
        by_city = defaultdict(lambda: {"won": 0, "total": 0})

        for pos in closed:
            try:
                hour = int(pos["entry_time"][11:13])
            except Exception:
                hour = -1
            city = pos.get("city", "unknown")
            won = pos["status"] in ("WON",)

            if hour >= 0:
                by_hour[hour]["total"] += 1
                if won:
                    by_hour[hour]["won"] += 1
            by_city[city]["total"] += 1
            if won:
                by_city[city]["won"] += 1

        total = len(closed)
        won_total = sum(1 for p in closed if p["status"] == "WON")

        return {
            "overall_win_rate": round(won_total / total, 2),
            "total_trades": total,
            "by_hour": sorted(
                [{"hour": h, "win_rate": round(v["won"] / v["total"], 2), "trades": v["total"]}
                 for h, v in by_hour.items() if v["total"] >= 2],
                key=lambda x: x["win_rate"], reverse=True,
            )[:6],
            "by_city": sorted(
                [{"city": c, "win_rate": round(v["won"] / v["total"], 2), "trades": v["total"]}
                 for c, v in by_city.items() if v["total"] >= 2],
                key=lambda x: x["win_rate"], reverse=True,
            )[:6],
        }

    # ── Capital snapshot ──────────────────────────────────────────────────────

    def record_capital(self):
        self.capital_history.append({
            "time": now_utc().isoformat(),
            "capital": round(self.capital_total, 2),
        })

    def snapshot(self):
        pnl = self.capital_total - self.capital_inicial
        roi = (pnl / self.capital_inicial * 100) if self.capital_inicial else 0

        exclude = {"PARTIAL_1", "PARTIAL_2", "LIQUIDATED"}
        won  = sum(1 for p in self.closed_positions if p["pnl"] > 0  and p["status"] not in exclude)
        lost = sum(1 for p in self.closed_positions if p["pnl"] <= 0 and p["status"] not in exclude)
        stopped    = sum(1 for p in self.closed_positions if p["status"] == "STOPPED")
        partial1   = sum(1 for p in self.closed_positions if p["status"] == "PARTIAL_1")
        partial2   = sum(1 for p in self.closed_positions if p["status"] == "PARTIAL_2")
        liquidated = sum(1 for p in self.closed_positions if p["status"] == "LIQUIDATED")

        open_positions = []
        for pos in list(self.positions.values()):
            float_pnl = pos["tokens"] * pos["current_yes"] - pos["allocated"]
            open_positions.append({
                "question":   pos["question"],
                "city":       pos.get("city", ""),
                "entry_yes":  pos["entry_yes"],
                "current_yes": pos["current_yes"],
                "exit_stage": pos.get("exit_stage", 0),
                "allocated":  round(pos["allocated"], 2),
                "pnl":        round(float_pnl, 2),
                "entry_time": pos["entry_time"],
                "status":     pos["status"],
            })

        closed = []
        for pos in self.closed_positions:
            closed.append({
                "question":   pos["question"],
                "entry_yes":  pos.get("entry_yes", 0),
                "allocated":  round(pos["allocated"], 2),
                "pnl":        round(pos["pnl"], 2),
                "status":     pos["status"],
                "resolution": pos.get("resolution", ""),
                "entry_time": pos["entry_time"],
                "close_time": pos.get("close_time", ""),
            })

        return {
            "capital_inicial":   round(self.capital_inicial, 2),
            "capital_total":     round(self.capital_total, 2),
            "capital_disponible": round(self.capital_disponible, 2),
            "pnl":        round(pnl, 2),
            "roi":        round(roi, 2),
            "won":        won,
            "lost":       lost,
            "stopped":    stopped,
            "partial1":   partial1,
            "partial2":   partial2,
            "liquidated": liquidated,
            "open_positions":   open_positions,
            "closed_positions": closed,
            "capital_history":  self.capital_history,
            "session_start":    self.session_start.isoformat(),
            "insights":         self.compute_insights(),
        }
