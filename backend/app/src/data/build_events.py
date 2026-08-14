# backend/app/src/data/build_events.py
import pandas as pd

from config import (
    PRICES_DIR,
    DIVIDENDS_FILE,
    PROCESSED_DIR,
    EVENTS_FILE,
    MAX_ABS_GAP,
    MAX_DIV_YIELD,
    T_PLUS_1_START_DATE,
    ensure_data_dirs,
)
from trading_calendar import shift_trading_days
from corporate_actions import is_cancelled, get_split_adjustment

T_PLUS_1_START = pd.Timestamp(T_PLUS_1_START_DATE)


def calculate_gap_event(df_price: pd.DataFrame, ticker: str, cutoff: pd.Timestamp, dividend_per_share: float, currency: str) -> dict | None:
    """
    Чистая функция расчёта одного события гэпа.
    Никакого I/O внутри — только цены (уже загруженные), дата закрытия
    реестра и сумма дивиденда. Легко тестировать вручную, без файлов на диске.

    ВАЖНО: `cutoff` — это дата ЗАКРЫТИЯ РЕЕСТРА (registryclosedate с MOEX),
    а не день, в который реально падает цена. Реальный гэп происходит на
    следующий торговый день после ПОСЛЕДНЕГО ДНЯ ПОКУПКИ под дивиденды,
    который наступает раньше даты закрытия реестра — на 2 торговых дня
    в режиме T+2 (до 31.07.2023) или на 1 торговый день в режиме T+1
    (с 31.07.2023). Источник: https://www.moex.com/n62684

    Также применяет поправки из corporate_actions.py: корректирует
    dividend_per_share на коэффициент сплита, если он известен для
    этого тикера/даты (см. corporate_actions.py про причину).

    Возвращает None, если данных для расчёта не хватает, ИЛИ если это
    известный отменённый дивиденд (см. CANCELLED_DIVIDENDS).
    """
    if is_cancelled(ticker, cutoff):
        return None

    dividend_per_share = dividend_per_share / get_split_adjustment(ticker, cutoff)

    settlement_offset = 1 if cutoff >= T_PLUS_1_START else 2

    last_buy_day = shift_trading_days(df_price.index, cutoff, settlement_offset)
    if last_buy_day is None:
        return None  # не хватает истории цен до этой даты

    try:
        close_before = df_price.loc[last_buy_day, "close"]
    except KeyError:
        return None

    future_dates = df_price.index[df_price.index > last_buy_day]
    if len(future_dates) == 0:
        return None

    next_date = future_dates[0]
    open_after = df_price.loc[next_date, "open"]

    gap = (open_after - close_before) / close_before
    div_yield = dividend_per_share / close_before

    return {
        "cutoff_date": cutoff,               # дата закрытия реестра (для справки/отчётности)
        "last_buy_day": last_buy_day,        # реальный якорь для гэпа
        "next_date": next_date,
        "close_before": close_before,
        "open_after": open_after,
        "dividend_per_share": dividend_per_share,  # уже скорректирован на сплит, если применимо
        "currency": currency,
        "actual_gap": gap,
        "div_yield": div_yield,
        "gap_minus_div": gap - div_yield,
        "settlement_offset": settlement_offset,  # T+1 (1) или T+2 (2) — полезно для отладки
        # ПРИМЕЧАНИЕ: фича days_to_cutoff (из README) сознательно НЕ реализована.
        # Она требует даты ОБЪЯВЛЕНИЯ дивиденда советом директоров, а не даты
        # закрытия реестра — у нас нет источника с датами объявлений, поэтому
        # фича исключена из MVP, а не заполнена подстановкой/выдумкой.
    }


def filter_outliers(df_events: pd.DataFrame) -> pd.DataFrame:
    """
    Отсекает аномальные события (ошибки данных, а не реальные экстремумы).
    Логирует, сколько строк отвалилось и почему — чтобы не терять данные молча.
    """
    n_before = len(df_events)

    bad_gap = ~df_events["actual_gap"].between(-MAX_ABS_GAP, MAX_ABS_GAP)
    bad_yield = ~df_events["div_yield"].between(0, MAX_DIV_YIELD)

    if bad_gap.sum() > 0:
        print(f"  Отброшено по гэпу (вне [-{MAX_ABS_GAP:.0%}, {MAX_ABS_GAP:.0%}]): {bad_gap.sum()}")
    if bad_yield.sum() > 0:
        print(f"  Отброшено по див.доходности (вне [0, {MAX_DIV_YIELD:.0%}]): {bad_yield.sum()}")

    df_clean = df_events[~bad_gap & ~bad_yield].copy()

    n_dropped = n_before - len(df_clean)
    if n_dropped > 0:
        print(f"  Всего отброшено: {n_dropped} из {n_before} ({n_dropped / n_before:.1%})")

    return df_clean


def build_dividend_events() -> pd.DataFrame:
    """
    Собирает таблицу событий: для каждой отсечки находит цену закрытия
    в день отсечки и цену открытия на следующий день, считает гэп.
    Только оркестрация I/O — сам расчёт в calculate_gap_event().
    """
    ensure_data_dirs()

    df_div = pd.read_parquet(DIVIDENDS_FILE)
    df_div["cutoff_date"] = pd.to_datetime(df_div["cutoff_date"]).dt.normalize()

    events = []

    for ticker in df_div["ticker"].unique():
        price_file = PRICES_DIR / f"{ticker}.parquet"
        if not price_file.exists():
            print(f"Нет цен для {ticker}")
            continue

        df_price = pd.read_parquet(price_file)
        df_price["date"] = pd.to_datetime(df_price["date"]).dt.normalize()
        df_price = df_price.sort_values("date").set_index("date")

        divs = df_div[df_div["ticker"] == ticker].sort_values("cutoff_date")

        for _, row in divs.iterrows():
            event = calculate_gap_event(
                df_price=df_price,
                ticker=ticker,
                cutoff=row["cutoff_date"],
                dividend_per_share=row["dividend_per_share"],
                currency=row.get("currency", "RUB"),
            )
            if event is not None:
                event["ticker"] = ticker
                events.append(event)

    df_events = pd.DataFrame(events)

    if df_events.empty:
        print("Не удалось построить ни одного события — проверь данные.")
        return df_events

    df_events = filter_outliers(df_events)
    df_events = df_events.sort_values(["ticker", "cutoff_date"]).reset_index(drop=True)

    df_events.to_parquet(EVENTS_FILE, index=False)

    print(f"\nСобытий: {len(df_events)}")
    print(f"Средний гэп: {df_events['actual_gap'].mean():.2%}")
    print(f"Средний дивиденд: {df_events['div_yield'].mean():.2%}")
    print(f"Средний (гэп - див): {df_events['gap_minus_div'].mean():.2%}")
    print(f"Сохранено: {EVENTS_FILE}")

    return df_events


if __name__ == "__main__":
    df = build_dividend_events()

    if not df.empty:
        print("\n--- Топ-5 самых больших гэпов ---")
        print(df.nlargest(5, "actual_gap")[["ticker", "cutoff_date", "actual_gap", "div_yield"]])

        print("\n--- Топ-5 самых глубоких падений ---")
        print(df.nsmallest(5, "actual_gap")[["ticker", "cutoff_date", "actual_gap", "div_yield"]])

        print("\n--- Статистика по тикерам ---")
        print(df.groupby("ticker")["actual_gap"].agg(["mean", "std", "count"]).sort_values("mean"))