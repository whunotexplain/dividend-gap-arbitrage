# src/data/moex_parser.py
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime


# --- Конфигурация ---
TARGET_TICKERS = [
    "SBER", "GAZP", "LKOH", "GMKN", "NVTK", "TATN", "TATNP",
    "YNDX", "TCSG", "PLZL", "CHMF", "MGNT", "MTSS", "ALRS",
    "PHOR", "PIKK", "FIVE", "AFLT", "MAGN", "HYDR", "FEES",
    "TRNFP", "BSPB", "CBOM", "VTBR", "SNGS", "SNGSP", "NLMK",
    "AFKS", "RUAL", "UPRO", "EUTR"
]


# --- Парсер списка тикеров ---
def fetch_target_prices(tickers: list = TARGET_TICKERS):
    """
    Загружает текущие цены только нужных тикеров с MOEX (TQBR).
    """
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    params = {"iss.meta": "off", "iss.only": "securities"}
    
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()["securities"]
    
    df = pd.DataFrame(data=data["data"], columns=data["columns"])
    df = df[df["SECID"].isin(tickers)].copy()
    
    cols = ["SECID", "SHORTNAME", "PREVPRICE", "LOTSIZE"]
    df = df[[c for c in cols if c in df.columns]]
    
    df = df.rename(columns={
        "SECID": "ticker",
        "SHORTNAME": "name",
        "PREVPRICE": "prev_price",
        "LOTSIZE": "lot_size"
    })
    
    missing = set(tickers) - set(df["ticker"].unique())
    if missing:
        print(f"Не найдены на TQBR: {missing}")
    
    return df.sort_values("ticker").reset_index(drop=True)


# --- Парсер свечей (OHLCV) ---
def fetch_ohlcv(ticker: str, start: str, end: str, interval: int = 24) -> pd.DataFrame:
    """
    Загружает исторические свечи с МосБиржи.
    interval: 1 (1 мин), 10, 60, 24 (день), 7 (неделя), 31 (месяц)
    """
    with requests.Session() as session:
        data = requests.get(
            f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/candles.json",
            params={"iss.meta": "off", "from": start, "till": end, "interval": interval},
            timeout=30
        ).json()["candles"]
    
    if not data or not data["data"]:
        raise ValueError(f"Нет свечей для {ticker}")
    
    df = pd.DataFrame(data=data["data"], columns=data["columns"])
    df["begin"] = pd.to_datetime(df["begin"]).dt.tz_localize(None)
    
    df = df.rename(columns={
        "begin": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "value": "turnover"
    })
    df["ticker"] = ticker
    return df.sort_values("date").reset_index(drop=True)


# --- Парсер дивидендов (MOEX fallback) ---
def fetch_moex_dividends(ticker: str) -> pd.DataFrame:
    """
    Дивиденды с MOEX (неполные, используй как fallback).
    """
    url = f"https://iss.moex.com/iss/securities/{ticker}/dividends.json"
    r = requests.get(url, params={"iss.meta": "off"}, timeout=30)
    
    if r.status_code != 200:
        return pd.DataFrame()
    
    data = r.json().get("dividends", {})
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
def ingest_moex_data(output_dir: str = "data/raw"):
    """
    Парсит цены и дивиденды для всех TARGET_TICKERS.
    """
    Path(f"{output_dir}/prices").mkdir(parents=True, exist_ok=True)
    Path(f"{output_dir}/dividends").mkdir(parents=True, exist_ok=True)
    
    all_dividends = []
    
    for ticker in TARGET_TICKERS:
        print(f"{ticker}...")
        
        # Цены
        try:
            df_price = fetch_ohlcv(ticker, "2019-01-01", "2025-12-31")
            df_price.to_parquet(f"{output_dir}/prices/{ticker}.parquet", index=False)
            print(f" {len(df_price)} свечей")
        except Exception as e:
            print(f"цены: {e}")
            continue
        
        # Дивиденды (MOEX)
        try:
            df_div = fetch_moex_dividends(ticker)
            if len(df_div) > 0:
                all_dividends.append(df_div)
                print(f"{len(df_div)} дивидендов")
        except Exception as e:
            print(f"дивиденды: {e}")
    
    if all_dividends:
        df_all = pd.concat(all_dividends, ignore_index=True)
        df_all.to_parquet(f"{output_dir}/dividends/moex_dividends.parquet", index=False)
        print(f"\nВсего дивидендов: {len(df_all)}")


if __name__ == "__main__":
    # Тест: список тикеров
    df = fetch_target_prices()
    print(df.to_string(index=False))
    
    # Полная загрузка (раскомментируй):
    # ingest_moex_data()