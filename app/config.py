import os

# --- Strategy V5: Momentum YES (espejo de V2) ---
# V2 compra NO a 73-78¢ cuando detecta uptrend en NO.
# V5 compra YES a 22-27¢ cuando detecta uptrend en YES.
# Mismos mercados, lado opuesto.

ENTRY_YES_MIN = float(os.environ.get("ENTRY_YES_MIN", 0.22))   # Entry lower bound
ENTRY_YES_MAX = float(os.environ.get("ENTRY_YES_MAX", 0.27))   # Entry upper bound

# Trend filter (mismo que V2 pero sobre YES price)
TREND_MIN_RISE         = float(os.environ.get("TREND_MIN_RISE", 0.05))   # +5¢ total rise
TREND_MIN_OBSERVATIONS = int(os.environ.get("TREND_MIN_OBSERVATIONS", 4))

# Stop loss: si YES cae 5¢ desde entrada
STOP_LOSS_DROP = float(os.environ.get("STOP_LOSS_DROP", 0.05))

# Progressive 3-stage exits (espejo de V2: NO 0.82/0.88/0.94 → YES 0.31/0.37/0.43)
EXIT_1_THRESHOLD = float(os.environ.get("EXIT_1_THRESHOLD", 0.31))  # vender 50%
EXIT_2_THRESHOLD = float(os.environ.get("EXIT_2_THRESHOLD", 0.37))  # vender 50% restante
EXIT_3_THRESHOLD = float(os.environ.get("EXIT_3_THRESHOLD", 0.43))  # cerrar todo

# Price history
PRICE_HISTORY_TTL = int(os.environ.get("PRICE_HISTORY_TTL", 3600))  # 1h sin update → purge

# Shared scan parameters
MIN_VOLUME        = float(os.environ.get("MIN_VOLUME", 200))
MONITOR_INTERVAL  = int(os.environ.get("MONITOR_INTERVAL", 30))
SCAN_DAYS_AHEAD   = int(os.environ.get("SCAN_DAYS_AHEAD", 1))
MIN_LOCAL_HOUR    = int(os.environ.get("MIN_LOCAL_HOUR", 11))
MAX_POSITIONS     = int(os.environ.get("MAX_POSITIONS", 20))

# Position sizing — 5%-10% de capital_disponible, proporcional al YES price
# YES=0.22 → 5% | YES=0.27 → 10%
POSITION_SIZE_MIN = float(os.environ.get("POSITION_SIZE_MIN", 0.05))
POSITION_SIZE_MAX = float(os.environ.get("POSITION_SIZE_MAX", 0.10))

# Price update thread
PRICE_UPDATE_INTERVAL = int(os.environ.get("PRICE_UPDATE_INTERVAL", 10))

# Geographic correlation limits
MAX_REGION_EXPOSURE = float(os.environ.get("MAX_REGION_EXPOSURE", 0.25))

REGION_MAP = {
    "chicago": "midwest",       "denver": "midwest",
    "dallas": "south",          "houston": "south",
    "atlanta": "south",         "miami": "south",         "phoenix": "south",
    "boston": "northeast",      "nyc": "northeast",
    "seattle": "pacific",       "los-angeles": "pacific",
    "london": "europe",         "paris": "europe",        "ankara": "europe",
    "wellington": "southern",   "buenos-aires": "southern", "sao-paulo": "southern",
    "seoul": "asia",            "toronto": "north_america",
}

# Capital
INITIAL_CAPITAL = float(os.environ.get("INITIAL_CAPITAL", 100.0))
AUTO_MODE       = os.environ.get("AUTO_MODE", "true").lower() == "true"
AUTO_START      = os.environ.get("AUTO_START", "false").lower() == "true"

# API
GAMMA = os.environ.get("GAMMA_API", "https://gamma-api.polymarket.com")

# City UTC offsets — hardcoded (no tzdata on Railway slim Docker)
CITY_UTC_OFFSET = {
    "chicago":      -6,
    "dallas":       -6,
    "atlanta":      -5,
    "miami":        -5,
    "nyc":          -5,
    "boston":       -5,
    "toronto":      -5,
    "seattle":      -8,
    "los-angeles":  -8,
    "houston":      -6,
    "phoenix":      -7,
    "denver":       -7,
    "london":        0,
    "paris":         1,
    "ankara":        3,
    "seoul":         9,
    "wellington":   13,
    "sao-paulo":    -3,
    "buenos-aires": -3,
}

WEATHER_CITIES = [
    "chicago", "dallas", "atlanta", "miami", "nyc",
    "seattle", "london", "wellington", "toronto", "seoul",
    "ankara", "paris", "sao-paulo", "buenos-aires",
    "los-angeles", "houston", "phoenix", "denver", "boston",
]
