# backend/app/src/data/moex_parser.py
import time
import requests
import pandas as pd
from config import (
    TARGET_TICKERS,
    START_DATE,
    END_DATE,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_BACKOFF,
    PRICES_DIR,
    DIVIDENDS_DIR,
    DIVIDENDS_FILE,
    ensure_data_dirs,
)


def _get_json(url: str, params: dict) -> dict:
    """
    Общая обёртка для запросов к MOEX ISS с ретраями и явной проверкой ответа.
    Все fetch_* функции идут через неё, а не зовут requests.get напрямую.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"  [retry {attempt}/{MAX_RETRIES}] {e} — жду {wait}с")
                time.sleep(wait)
    raise RuntimeError(f"Не удалось получить данные с {url}: {last_exc}")


# --- Парсер списка тикеров ---
def fetch_target_prices(tickers: list = TARGET_TICKERS) -> pd.DataFrame:
    """Загружает текущие цены только нужных тикеров с MOEX (TQBR)."""
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    params = {"iss.meta": "off", "iss.only": "securities"}

    data = _get_json(url, params)["securities"]
    df = pd.DataFrame(data=data["data"], columns=data["columns"])
    df = df[df["SECID"].isin(tickers)].copy()

    cols = ["SECID", "SHORTNAME", "PREVPRICE", "LOTSIZE"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.rename(columns={
        "SECID": "ticker", "SHORTNAME": "name",
        "PREVPRICE": "prev_price", "LOTSIZE": "lot_size"
    })

    missing = set(tickers) - set(df["ticker"].unique())
    if missing:
        print(f"Не найдены на TQBR: {missing}")

    return df.sort_values("ticker").reset_index(drop=True)


# --- Парсер свечей (OHLCV) с пагинацией ---
def fetch_ohlcv(ticker: str, start: str = START_DATE, end: str = END_DATE, interval: int = 24) -> pd.DataFrame:
    """
    Загружает исторические свечи с МосБиржи.
    MOEX ISS отдаёт максимум ~100 строк за запрос — здесь пагинация
    через параметр `start` (смещение по строкам), пока не придёт
    неполная/пустая страница.
    """
    base_url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/candles.json"

    all_rows = []
    columns = None
    offset = 0
    page_size_guess = 100

    while True:
        params = {
            "iss.meta": "off", "from": start, "till": end,
            "interval": interval, "start": offset,
        }
        payload = _get_json(base_url, params)["candles"]

        if columns is None:
            columns = payload["columns"]

        rows = payload["data"]
        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < page_size_guess:
            break

        offset += len(rows)

    if not all_rows:
        raise ValueError(f"Нет свечей для {ticker} за период {start}..{end}")

    df = pd.DataFrame(data=all_rows, columns=columns)
    df["begin"] = pd.to_datetime(df["begin"]).dt.tz_localize(None)
    df = df.rename(columns={"begin": "date", "volume": "volume", "value": "turnover"})
    df["ticker"] = ticker

    df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


# --- Парсер дивидендов (MOEX fallback) ---
def fetch_moex_dividends(ticker: str) -> pd.DataFrame:
    """Дивиденды с MOEX (неполные, используй как fallback)."""
    url = f"https://iss.moex.com/iss/securities/{ticker}/dividends.json"

    try:
        payload = _get_json(url, {"iss.meta": "off"})
    except RuntimeError as e:
        print(f"  дивиденды {ticker}: {e}")
        return pd.DataFrame()

    data = payload.get("dividends", {})
    if not data or not data.get("data"):
        return pd.DataFrame()

    df = pd.DataFrame(data["data"], columns=data["columns"])
    df["registryclosedate"] = pd.to_datetime(df["registryclosedate"], errors="coerce").dt.tz_localize(None)
    df = df.rename(columns={
        "registryclosedate": "cutoff_date",
        "value": "dividend_per_share",
        "currencyid": "currency"
    })
    df["ticker"] = ticker
    return df[["ticker", "cutoff_date", "dividend_per_share", "currency"]].dropna()


# --- Мастер-функция ---
def ingest_moex_data() -> None:
    """
    Парсит цены и дивиденды для всех TARGET_TICKERS.
    Каждый тикер сохраняется сразу после загрузки (инкрементально),
    пути всегда абсолютные (см. config.py) — не важно, откуда запущен скрипт.
    """
    ensure_data_dirs()

    all_dividends = []
    failed_tickers = []

    for ticker in TARGET_TICKERS:
        print(f"{ticker}...")

        try:
            df_price = fetch_ohlcv(ticker)
            df_price.to_parquet(PRICES_DIR / f"{ticker}.parquet", index=False)
            print(f"  {len(df_price)} свечей")
        except Exception as e:
            print(f"  цены: {e}")
            failed_tickers.append(ticker)
            continue

        try:
            df_div = fetch_moex_dividends(ticker)
            if len(df_div) > 0:
                all_dividends.append(df_div)
                print(f"  {len(df_div)} дивидендов")
        except Exception as e:
            print(f"  дивиденды: {e}")

    if all_dividends:
        df_all = pd.concat(all_dividends, ignore_index=True)
        df_all.to_parquet(DIVIDENDS_FILE, index=False)
        print(f"\nВсего дивидендов: {len(df_all)}")

    if failed_tickers:
        print(f"\nНе удалось загрузить цены: {failed_tickers}")


if __name__ == "__main__":
    df = fetch_ohlcv("SBER")
    print(f"SBER: {len(df)} свечей, {df['date'].min()} .. {df['date'].max()}")

    # Полная загрузка (раскомментируй):
    ingest_moex_data()