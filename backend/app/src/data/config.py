# backend/app/src/data/config.py
"""
Общий конфиг для парсеров и пайплайна данных.
Все пути привязаны к корню проекта (PROJECT_ROOT), а НЕ к текущей
рабочей директории — чтобы не важно было, откуда запущен скрипт
(из backend/, из backend/app/src/data/, из корня и т.д.),
данные всегда попадали в одно и то же место: <корень>/data/...
"""
from pathlib import Path

# --- Корень проекта ---
# Этот файл лежит в backend/app/src/data/config.py
# значит корень проекта = подняться на 4 уровня вверх от этого файла
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# --- Пути к данным (всегда абсолютные, всегда от корня) ---
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PRICES_DIR = RAW_DIR / "prices"
DIVIDENDS_DIR = RAW_DIR / "dividends"
PROCESSED_DIR = DATA_DIR / "processed"

DIVIDENDS_FILE = DIVIDENDS_DIR / "moex_dividends.parquet"
EVENTS_FILE = PROCESSED_DIR / "dividend_events.parquet"

# --- Тикеры ---
TARGET_TICKERS = [
    "SBER", "GAZP", "LKOH", "GMKN", "NVTK", "TATN", "TATNP",
    "YNDX", "TCSG", "PLZL", "CHMF", "MGNT", "MTSS", "ALRS",
    "PHOR", "PIKK", "FIVE", "AFLT", "MAGN", "HYDR", "FEES",
    "TRNFP", "BSPB", "CBOM", "VTBR", "SNGS", "SNGSP", "NLMK",
    "AFKS", "RUAL", "UPRO", "EUTR"
]

# --- Диапазон дат для загрузки цен ---
START_DATE = "2019-01-01"
END_DATE = "2025-12-31"

# --- HTTP настройки (запросы к MOEX ISS) ---
REQUEST_TIMEOUT = 30       # секунд на один запрос
MAX_RETRIES = 3            # попыток на один запрос перед тем как сдаться
RETRY_BACKOFF = 2          # секунд, множится на номер попытки (2с, 4с, 6с...)

# --- Фильтр выбросов при построении событий (build_events.py) ---
MAX_ABS_GAP = 0.5          # гэп больше 50% отбрасываем как аномалию/ошибку данных
MAX_DIV_YIELD = 0.5        # дивдоходность больше 50% — тоже аномалия

# --- Режим расчётов на MOEX (важно для расчёта дивидендного гэпа) ---
# 31 июля 2023 MOEX перешёл с T+2 на T+1.
# До этой даты: последний день покупки = дата закрытия реестра МИНУС 2 торговых дня.
# С этой даты (включительно): последний день покупки = дата закрытия реестра МИНУС 1 торговый день.
# Источник: https://www.moex.com/n62684
T_PLUS_1_START_DATE = "2023-07-31"

# --- Feature engineering ---
EVENTS_FEATURES_FILE = PROCESSED_DIR / "dividend_events_features.parquet"
TREND_WINDOW_DAYS = 20          # торговых дней для pre_cutoff_trend
VOLUME_Z_WINDOW_DAYS = 20       # торговых дней для базы pre_cutoff_volume_z
HISTORICAL_LOOKBACK_YEARS = 3   # окно для historical_avg_gap / historical_gap_std


def ensure_data_dirs() -> None:
    """Создаёт все нужные папки для данных, если их ещё нет."""
    for d in (PRICES_DIR, DIVIDENDS_DIR, PROCESSED_DIR):
        d.mkdir(parents=True, exist_ok=True)