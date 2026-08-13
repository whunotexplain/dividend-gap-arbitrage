
import numpy as np
import pandas as pd

from config import (
    PRICES_DIR,
    EVENTS_FILE,
    EVENTS_FEATURES_FILE,
    TREND_WINDOW_DAYS,
    VOLUME_Z_WINDOW_DAYS,
    HISTORICAL_LOOKBACK_YEARS,
)
from trading_calendar import shift_trading_days


def calculate_price_features(df_price: pd.DataFrame, last_buy_day: pd.Timestamp) -> dict:
    """
    Считает фичи, завязанные на цену/объём, за окно ПЕРЕД last_buy_day.
    Ничего не знает о гэпе/дивиденде — чистая функция от цен и одной даты.
    """
    trend_start = shift_trading_days(df_price.index, last_buy_day, TREND_WINDOW_DAYS)
    pre_cutoff_trend = np.nan
    if trend_start is not None:
        try:
            price_start = df_price.loc[trend_start, "close"]
            price_end = df_price.loc[last_buy_day, "close"]
            pre_cutoff_trend = (price_end - price_start) / price_start
        except KeyError:
            pass

    # База для z-score объёма: VOLUME_Z_WINDOW_DAYS торговых дней ДО last_buy_day,
    # не включая сам last_buy_day (иначе он попадёт и в числитель, и в базу).
    window_start = shift_trading_days(df_price.index, last_buy_day, VOLUME_Z_WINDOW_DAYS)
    pre_cutoff_volume_z = np.nan
    if window_start is not None:
        window_mask = (df_price.index >= window_start) & (df_price.index < last_buy_day)
        volumes = df_price.loc[window_mask, "volume"]
        if len(volumes) >= 2 and volumes.std() > 0:
            try:
                current_volume = df_price.loc[last_buy_day, "volume"]
                pre_cutoff_volume_z = (current_volume - volumes.mean()) / volumes.std()
            except KeyError:
                pass

    return {
        "pre_cutoff_trend": pre_cutoff_trend,
        "pre_cutoff_volume_z": pre_cutoff_volume_z,
        "month": last_buy_day.month,
    }


def add_historical_stats(df_events: pd.DataFrame, lookback_years: int = HISTORICAL_LOOKBACK_YEARS) -> pd.DataFrame:
    """
    Добавляет historical_avg_gap / historical_gap_std — среднее и std
    ФАКТИЧЕСКОГО гэпа по этому тикеру за предыдущие `lookback_years` лет.

    ВАЖНО про утечку данных (leakage): для события i используются только
    события того же тикера с cutoff_date СТРОГО РАНЬШЕ текущего. Если бы
    мы считали среднее по всей истории тикера (включая будущее относительно
    текущего события), модель на обучении "подглядывала" бы в свой же
    таргет через агрегат — типичная ошибка в такого рода задачах.
    """
    df = df_events.sort_values(["ticker", "cutoff_date"]).reset_index(drop=True)
    lookback = pd.Timedelta(days=365 * lookback_years)

    records = []
    for ticker, group in df.groupby("ticker"):
        dates = group["cutoff_date"].values
        gaps = group["actual_gap"].values

        for i in range(len(group)):
            window_start = dates[i] - lookback
            mask = (dates < dates[i]) & (dates >= window_start)
            past_gaps = gaps[mask]

            avg = past_gaps.mean() if len(past_gaps) > 0 else np.nan
            std = past_gaps.std() if len(past_gaps) > 1 else np.nan

            records.append({
                "ticker": ticker,
                "cutoff_date": dates[i],
                "historical_avg_gap": avg,
                "historical_gap_std": std,
                "historical_n_events": len(past_gaps),
            })

    df_hist = pd.DataFrame(records)
    return df.merge(df_hist, on=["ticker", "cutoff_date"], how="left")


def build_features() -> pd.DataFrame:
    """
    Читает dividend_events.parquet, добавляет фичи, сохраняет результат
    в dividend_events_features.parquet.
    """
    df_events = pd.read_parquet(EVENTS_FILE)

    # --- Ценовые фичи (per-событие, нужен df_price конкретного тикера) ---
    price_feature_rows = []
    price_cache: dict[str, pd.DataFrame] = {}

    for _, row in df_events.iterrows():
        ticker = row["ticker"]

        if ticker not in price_cache:
            df_price = pd.read_parquet(PRICES_DIR / f"{ticker}.parquet")
            df_price["date"] = pd.to_datetime(df_price["date"]).dt.normalize()
            df_price = df_price.sort_values("date").set_index("date")
            price_cache[ticker] = df_price

        feats = calculate_price_features(price_cache[ticker], row["last_buy_day"])
        price_feature_rows.append(feats)

    df_price_feats = pd.DataFrame(price_feature_rows)
    df_events = pd.concat([df_events.reset_index(drop=True), df_price_feats], axis=1)

    # --- Исторические статистики по тикеру (leakage-safe) ---
    df_events = add_historical_stats(df_events)

    df_events.to_parquet(EVENTS_FEATURES_FILE, index=False)

    print(f"Событий с фичами: {len(df_events)}")
    print(f"NaN по фичам:")
    feature_cols = [
        "pre_cutoff_trend", "pre_cutoff_volume_z", "month",
        "historical_avg_gap", "historical_gap_std",
    ]
    print(df_events[feature_cols].isna().sum())
    print(f"\nСохранено: {EVENTS_FEATURES_FILE}")

    return df_events


if __name__ == "__main__":
    df = build_features()
    print("\n--- Пример (первые 5 строк) ---")
    cols = ["ticker", "cutoff_date", "actual_gap", "pre_cutoff_trend",
            "pre_cutoff_volume_z", "historical_avg_gap", "historical_n_events"]
    print(df[cols].head().to_string())