"""bot.py — V5: Momentum YES (espejo de V2).

Cycle:
  1. Gamma discovery → candidates (YES 0.10–0.40)
  2. CLOB YES price → record in trend_tracker
  3. Entry gate: YES in 0.22–0.27 AND (uptrend YES OR ≥4 obs en rango)
  4. Open positions for confirmed entries
  5. Update prices for open positions (CLOB → Gamma fallback)
  6. check_progressive_exits() — 3-stage exit logic (YES rising)
  7. Auto-liquidate positions outside allowed range
  8. Purge stale trend_tracker history
"""

import threading
import logging
from datetime import datetime, timezone

from app.scanner import (
    scan_opportunities, fetch_live_prices, fetch_yes_price_clob,
)
from app.config import (
    MONITOR_INTERVAL, POSITION_SIZE_MIN, POSITION_SIZE_MAX,
    ENTRY_YES_MIN, ENTRY_YES_MAX, PRICE_UPDATE_INTERVAL, MAX_POSITIONS,
    TREND_MIN_OBSERVATIONS,
)

log = logging.getLogger(__name__)

MAX_CLOB_VERIFY = 20


def calc_position_size(capital_disponible, yes_price):
    """5%–10% de capital_disponible, proporcional al YES price.

    YES=0.22 → 5%  (menor convicción)
    YES=0.27 → 10% (mayor convicción — el mercado ya está en 27¢)
    Espejo directo de V2: más precio = más apuesta.
    """
    price_range = ENTRY_YES_MAX - ENTRY_YES_MIN
    if price_range <= 0:
        pct = POSITION_SIZE_MIN
    else:
        t   = (yes_price - ENTRY_YES_MIN) / price_range
        t   = max(0.0, min(1.0, t))
        pct = POSITION_SIZE_MIN + t * (POSITION_SIZE_MAX - POSITION_SIZE_MIN)
    return min(capital_disponible * pct, capital_disponible)


class BotRunner:
    def __init__(self, portfolio, trend_tracker):
        self.portfolio     = portfolio
        self.trend_tracker = trend_tracker
        self._stop_event   = threading.Event()
        self._thread       = None
        self._price_thread = None
        self.scan_count    = 0
        self.last_opportunities = []
        self.status        = "stopped"
        self.last_price_update = None

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    # ── Thread management ──────────────────────────────────────────────────────

    def start(self):
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread       = threading.Thread(target=self._run,        daemon=True)
        self._price_thread = threading.Thread(target=self._run_prices, daemon=True)
        self._thread.start()
        self._price_thread.start()
        self.status = "running"

    def stop(self):
        self._stop_event.set()
        self.status = "stopped"

    # ── Main scan loop ─────────────────────────────────────────────────────────

    def _run(self):
        log.info("Bot V5 iniciado — Momentum YES (espejo de V2)")
        while not self._stop_event.is_set():
            try:
                self._cycle()
            except Exception:
                log.exception("Error en ciclo V5")
            self._stop_event.wait(MONITOR_INTERVAL)
        log.info("Bot V5 detenido")

    def _cycle(self):
        self.scan_count += 1
        portfolio = self.portfolio
        tracker   = self.trend_tracker

        # Watchdog
        if self._price_thread is not None and not self._price_thread.is_alive():
            log.warning("Price thread caído — reiniciando")
            self._price_thread = threading.Thread(target=self._run_prices, daemon=True)
            self._price_thread.start()

        # 1. IDs a saltar
        with portfolio.lock:
            existing_ids = set(portfolio.positions.keys())
            closed_ids   = {
                p["condition_id"] for p in portfolio.closed_positions
                if p.get("condition_id")
            }
            existing_ids |= closed_ids

        # 2. Gamma discovery (YES 0.10–0.40, wide for trend building)
        candidates = scan_opportunities(existing_ids)

        # 3. CLOB price → record en trend_tracker → entry gate
        clob_verified = []
        display_opps  = []
        clob_fails    = 0
        clob_ok       = True

        for opp in candidates[:MAX_CLOB_VERIFY]:
            if self._stop_event.is_set():
                return
            yes_tid = opp.get("yes_token_id")
            rt_yes, rt_no = None, None

            if clob_ok and yes_tid:
                rt_yes, rt_no = fetch_yes_price_clob(yes_tid)
                # Sanity: si YES > 0.50 probablemente devolvió el token NO
                if rt_yes is not None and rt_yes > 0.50:
                    rt_yes, rt_no = None, None
                if rt_yes is None:
                    clob_fails += 1
                    if clob_fails >= 2:
                        clob_ok = False

            if rt_yes is None:
                display_opps.append({
                    **opp,
                    "trend_obs": tracker.observation_count(opp["condition_id"]),
                    "has_trend": False,
                })
                continue

            # Record YES price para trend building (aunque esté fuera del rango de entrada)
            tracker.record(opp["condition_id"], rt_yes)

            opp = {**opp, "yes_price": rt_yes, "no_price": rt_no or round(1 - rt_yes, 4)}
            obs_count = tracker.observation_count(opp["condition_id"])
            has_trend = tracker.has_uptrend(opp["condition_id"])

            display_opps.append({**opp, "trend_obs": obs_count, "has_trend": has_trend})

            # Entry gate: YES en rango + (uptrend YES O ≥4 obs en rango)
            stable_in_range = (obs_count >= TREND_MIN_OBSERVATIONS)
            if ENTRY_YES_MIN <= rt_yes <= ENTRY_YES_MAX and (has_trend or stable_in_range):
                entry_type = "uptrend" if has_trend else "stable"
                log.info(
                    "Entrada [%s] %s — YES=%.1f¢ (%d obs)",
                    entry_type, opp["question"][:35], rt_yes * 100, obs_count,
                )
                clob_verified.append(opp)
            elif ENTRY_YES_MIN <= rt_yes <= ENTRY_YES_MAX:
                log.info(
                    "Pendiente %s — YES=%.1f¢ en rango, %d obs (esperando trend o ≥%d)",
                    opp["question"][:35], rt_yes * 100, obs_count, TREND_MIN_OBSERVATIONS,
                )

        display_opps.extend(candidates[MAX_CLOB_VERIFY:MAX_CLOB_VERIFY + (20 - len(display_opps))])

        self.last_opportunities = [
            {
                "question":  o["question"],
                "yes_price": o["yes_price"],
                "no_price":  o["no_price"],
                "volume":    o["volume"],
                "profit_cents": o.get("profit_cents", 0),
                "trend_obs": o.get("trend_obs", 0),
                "has_trend": o.get("has_trend", False),
            }
            for o in display_opps[:20]
        ]

        # 4. Precios posiciones abiertas — CLOB → Gamma fallback
        with portfolio.lock:
            pos_data = [
                (cid, pos.get("yes_token_id"), pos.get("slug"))
                for cid, pos in portfolio.positions.items()
            ]

        price_map     = {}
        clob_ok_pos   = True
        clob_fail_pos = 0
        for cid, yes_tid, slug in pos_data:
            if self._stop_event.is_set():
                return
            yes_p, no_p = None, None
            if clob_ok_pos and yes_tid:
                yes_p, no_p = fetch_yes_price_clob(yes_tid)
                if yes_p is not None and yes_p > 0.50:
                    yes_p, no_p = None, None
                if yes_p is None:
                    clob_fail_pos += 1
                    if clob_fail_pos >= 2:
                        clob_ok_pos = False
            if yes_p is None:
                yes_p, no_p = fetch_live_prices(slug)
            if yes_p is not None and no_p is not None:
                price_map[cid] = (yes_p, no_p)

        # 5. Portfolio operations (con lock)
        with portfolio.lock:
            for opp in clob_verified:
                if not portfolio.can_open_position():
                    break
                city = opp.get("city", "")
                if not portfolio.region_has_capacity(city):
                    log.info("Región llena, skip %s (%s)", city, opp["question"][:30])
                    continue
                amount = calc_position_size(portfolio.capital_disponible, opp["yes_price"])
                if amount >= 1:
                    portfolio.open_position(opp, amount)
                    log.info(
                        "Abierta YES: %s @ %.1f¢  $%.2f",
                        opp["question"][:40], opp["yes_price"] * 100, amount,
                    )

            if price_map:
                portfolio.apply_price_updates(price_map)

            # Auto-liquidar posiciones fuera del rango de entrada
            for cid, pos in list(portfolio.positions.items()):
                entry_yes = pos.get("entry_yes", 0.0)
                if not (ENTRY_YES_MIN <= entry_yes <= ENTRY_YES_MAX):
                    current_yes = pos.get("current_yes", entry_yes)
                    pnl = round(pos["tokens"] * current_yes - pos["allocated"], 2)
                    log.warning(
                        "Auto-liquidar %s — entrada YES=%.1f¢ fuera de rango",
                        pos["question"][:40], entry_yes * 100,
                    )
                    portfolio._close_position(
                        cid, "LIQUIDATED", pnl,
                        resolution=(
                            f"Auto-liquidación: YES entrada {entry_yes*100:.1f}¢ "
                            f"fuera del rango ({ENTRY_YES_MIN*100:.0f}–{ENTRY_YES_MAX*100:.0f}¢)"
                        ),
                    )

            portfolio.check_progressive_exits()
            portfolio.record_capital()

        tracker.purge_old()

    # ── Price update loop ──────────────────────────────────────────────────────

    def _run_prices(self):
        log.info("Price updater V5 iniciado")
        while not self._stop_event.is_set():
            self._stop_event.wait(PRICE_UPDATE_INTERVAL)
            if self._stop_event.is_set():
                break
            try:
                self._refresh_prices()
            except Exception:
                log.exception("Error actualizando precios")
        log.info("Price updater V5 detenido")

    def _refresh_prices(self):
        with self.portfolio.lock:
            pos_data = [
                (cid, pos.get("yes_token_id"), pos.get("slug"))
                for cid, pos in self.portfolio.positions.items()
            ]

        clob_ok       = True
        clob_failures = 0

        for cid, yes_tid, slug in pos_data:
            if self._stop_event.is_set():
                return

            yes_p, no_p = None, None
            source = "Gamma"

            if clob_ok and yes_tid:
                yes_p, no_p = fetch_yes_price_clob(yes_tid)
                if yes_p is not None:
                    if yes_p > 0.50:
                        yes_p, no_p = None, None
                        clob_failures += 1
                    else:
                        source = "CLOB"
                        clob_failures = 0
                else:
                    clob_failures += 1

                if clob_failures >= 2:
                    clob_ok = False
                    log.warning("CLOB no confiable — usando Gamma para posiciones restantes")

            if yes_p is None:
                yes_p, no_p = fetch_live_prices(slug)

            if yes_p is None:
                continue

            with self.portfolio.lock:
                if cid in self.portfolio.positions:
                    pos = self.portfolio.positions[cid]
                    old = pos["current_yes"]
                    pos["current_yes"] = yes_p
                    if abs(yes_p - old) >= 0.001:
                        log.info(
                            "Precio YES [%s] %s: %.4f → %.4f",
                            source, slug[:30] if slug else cid[:20], old, yes_p,
                        )

        self.last_price_update = datetime.now(timezone.utc)
