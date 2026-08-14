"""
Walk-forward (time-series) разбиение на train/test.

НИКОГДА не используем shuffle=True для этой задачи — train должен
состоять только из событий СТРОГО РАНЬШЕ по времени, чем test,
иначе модель имплицитно "подглядывает" в будущее относительно
того момента, для которого делается прогноз (look-ahead bias).
"""
import pandas as pd

from config import N_WALK_FORWARD_SPLITS, MIN_TRAIN_SIZE


def walk_forward_splits(
    df_events: pd.DataFrame,
    date_col: str = "cutoff_date",
    n_splits: int = N_WALK_FORWARD_SPLITS,
    min_train_size: int = MIN_TRAIN_SIZE,
) -> list[tuple[pd.Index, pd.Index]]:
    """
    Возвращает список (train_index, test_index) пар — по одной на фолд.

    Логика: сортируем события по дате, делим оставшуюся (после
    min_train_size) часть на n_splits последовательных блоков.
    Для фолда i: train = все события ДО начала блока i,
                 test  = события внутри блока i.

    Каждый следующий фолд имеет БОЛЬШЕ train-данных (расширяющееся
    окно, "expanding window") — так же, как в реальности: чем позже
    момент прогноза, тем больше истории у модели накоплено.
    """
    df_sorted = df_events.sort_values(date_col).reset_index(drop=False)  # 'index' = исходный индекс
    n = len(df_sorted)

    if n <= min_train_size:
        raise ValueError(
            f"Событий ({n}) не больше min_train_size ({min_train_size}) — "
            f"walk-forward невозможен, нечего тестировать."
        )

    testable_size = n - min_train_size
    fold_size = testable_size // n_splits
    if fold_size < 1:
        raise ValueError(
            f"Слишком много фолдов ({n_splits}) для {testable_size} доступных "
            f"тестовых событий — уменьшите n_splits."
        )

    splits = []
    for i in range(n_splits):
        train_end = min_train_size + i * fold_size
        test_end = train_end + fold_size if i < n_splits - 1 else n  # последний фолд забирает остаток

        train_pos = range(0, train_end)
        test_pos = range(train_end, test_end)

        train_idx = df_sorted.loc[list(train_pos), "index"]
        test_idx = df_sorted.loc[list(test_pos), "index"]

        splits.append((train_idx, test_idx))

    return splits


if __name__ == "__main__":
    from config import EVENTS_FEATURES_FILE

    df = pd.read_parquet(EVENTS_FEATURES_FILE)
    folds = walk_forward_splits(df)

    for i, (train_idx, test_idx) in enumerate(folds):
        train_dates = df.loc[train_idx, "cutoff_date"]
        test_dates = df.loc[test_idx, "cutoff_date"]
        print(
            f"Фолд {i}: train {len(train_idx)} событий "
            f"({train_dates.min().date()} .. {train_dates.max().date()})  |  "
            f"test {len(test_idx)} событий "
            f"({test_dates.min().date()} .. {test_dates.max().date()})"
        )