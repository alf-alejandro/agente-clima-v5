import logging
from flask import Flask

from app.config import INITIAL_CAPITAL, AUTO_START
from app.portfolio import AutoPortfolio
from app.trend_tracker import TrendTracker
from app.bot import BotRunner
from app.routes import bp, init_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app():
    app = Flask(__name__)

    portfolio = AutoPortfolio(INITIAL_CAPITAL)
    tracker   = TrendTracker()
    bot       = BotRunner(portfolio, tracker)

    init_routes(bot, portfolio, tracker)
    app.register_blueprint(bp)

    if AUTO_START:
        bot.start()

    return app
