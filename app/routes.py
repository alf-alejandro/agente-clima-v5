from flask import Blueprint, render_template, jsonify

bp = Blueprint("main", __name__)

bot = None
portfolio = None
tracker = None


def init_routes(bot_instance, portfolio_instance, tracker_instance):
    global bot, portfolio, tracker
    bot = bot_instance
    portfolio = portfolio_instance
    tracker = tracker_instance


@bp.route("/")
def dashboard():
    return render_template("dashboard.html")


@bp.route("/api/status")
def api_status():
    with portfolio.lock:
        snap = portfolio.snapshot()
    snap["bot_status"]   = bot.status if bot else "unknown"
    snap["scan_count"]   = bot.scan_count if bot else 0
    snap["last_opportunities"] = bot.last_opportunities if bot else []
    lpu = bot.last_price_update if bot else None
    snap["last_price_update"] = lpu.isoformat() if lpu else None
    snap["price_thread_alive"] = (
        bot._price_thread is not None and bot._price_thread.is_alive()
    ) if bot else False

    if tracker:
        tracked = tracker.all_tracked()
        snap["tracked_markets"] = len(tracked)
        snap["trend_ready"]     = sum(1 for v in tracked.values() if v["has_uptrend"])
    else:
        snap["tracked_markets"] = 0
        snap["trend_ready"]     = 0

    return jsonify(snap)


@bp.route("/api/bot/start", methods=["POST"])
def api_bot_start():
    bot.start()
    return jsonify({"status": "running"})


@bp.route("/api/bot/stop", methods=["POST"])
def api_bot_stop():
    bot.stop()
    return jsonify({"status": "stopped"})


@bp.route("/api/trends")
def api_trends():
    if not tracker:
        return jsonify({})
    return jsonify(tracker.all_tracked())
