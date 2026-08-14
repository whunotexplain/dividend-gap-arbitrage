"""
Определение таргетов для модели — регрессионного и классификационного.

Стратегия: продать акцию перед last_buy_day, откупить после гэпа.
    прибыль (до издержек) = -actual_gap - div_yield

Знак минус перед actual_gap — потому что actual_gap отрицательный
(цена падает), а мы на этом падении зарабатываем как шортист.
Если |гэп| > дивиденда — стратегия в плюсе; если |гэп| < дивиденда — в минусе.

ВАЖНО: на наших реальных данных средний actual_gap = -3.67%, средний
div_yield = +5.65% — то есть рынок в среднем НЕДООЦЕНИВАЕТ гэп относительно
дивиденда (edge отрицательный в среднем). Это противоречит исходной
гипотезе из README ("рынок переоценивает гэп") — гипотеза не подтвердилась
на реальных данных, значит README тоже нужно будет поправить.
"""
import pandas as pd

from config import EVENTS_FEATURES_FILE, TOTAL_TRADE_COST


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Добавляет:
    - edge: прибыль стратегии ДО издержек (регрессионный таргет — что ближе
      к сути дела, чем сырой actual_gap, потому что явно учитывает дивиденд)
    - edge_after_costs: прибыль ПОСЛЕ комиссии и слиппеджа
    - profitable: бинарный таргет для классификации — выгодна ли сделка
      ПОСЛЕ издержек (а не просто "гэп больше дивиденда" без учёта costs,
      как было в первоначальной формулировке README)
    """
    df = df.copy()
    df["edge"] = -df["actual_gap"] - df["div_yield"]
    df["edge_after_costs"] = df["edge"] - TOTAL_TRADE_COST
    df["profitable"] = (df["edge_after_costs"] > 0).astype(int)
    return df


if __name__ == "__main__":
    df = pd.read_parquet(EVENTS_FEATURES_FILE)
    df = add_targets(df)

    print(f"Всего событий: {len(df)}")
    print(f"Средний edge (до издержек): {df['edge'].mean():.2%}")
    print(f"Средний edge (после издержек): {df['edge_after_costs'].mean():.2%}")
    print(f"Доля прибыльных сделок (после издержек): {df['profitable'].mean():.1%}")
    print(f"  ({df['profitable'].sum()} прибыльных из {len(df)})")

    print("\n--- Топ-5 самых прибыльных сделок ---")
    print(df.nlargest(5, "edge_after_costs")[["ticker", "cutoff_date", "actual_gap", "div_yield", "edge_after_costs"]])

    print("\n--- Топ-5 самых убыточных сделок ---")
    print(df.nsmallest(5, "edge_after_costs")[["ticker", "cutoff_date", "actual_gap", "div_yield", "edge_after_costs"]])