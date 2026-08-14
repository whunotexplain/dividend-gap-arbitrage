# backend/app/src/data/detect_anomalies.py
"""
Детектор кандидатов на неучтённый сплит/консолидацию акций.

Логика: MOEX ISS отдаёт исторические свечи, скорректированные "задним
числом" под БУДУЩИЕ сплиты/консолидации (retroactive adjustment), а
dividend_per_share из отдельного дивидендного API — нет. Из-за этого
div_yield = dividend_per_share / close_before искусственно завышается
в разы для событий ДО даты корпоративного действия.

Это не автоматический фильтр — просто список кандидатов для ручной
проверки (см. историю чата: так нашли PLZL сплит 1:10 и VTBR обратный
сплит 5000:1).
"""
import pandas as pd

from config import EVENTS_FILE, DIV_YIELD_SUSPICION_THRESHOLD


def find_suspicious_events(df: pd.DataFrame, threshold: float = DIV_YIELD_SUSPICION_THRESHOLD) -> pd.DataFrame:
    suspicious = df[df["div_yield"] > threshold].copy()
    return suspicious.sort_values("div_yield", ascending=False)


if __name__ == "__main__":
    df = pd.read_parquet(EVENTS_FILE)
    suspicious = find_suspicious_events(df)

    print(f"Порог подозрения: div_yield > {DIV_YIELD_SUSPICION_THRESHOLD:.0%}")
    print(f"Найдено кандидатов: {len(suspicious)} из {len(df)}\n")

    if len(suspicious) > 0:
        print(suspicious[["ticker", "cutoff_date", "last_buy_day", "close_before", "dividend_per_share", "div_yield"]].to_string())

        print("\n--- Уникальные тикеры-кандидаты ---")
        print(suspicious["ticker"].value_counts())
    else:
        print("Подозрительных событий не найдено.")