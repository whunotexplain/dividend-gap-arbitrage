import pandas as pd
import numpy as np
from pathlib import Path


def build_dividend_events(
    prices_dir: str = "data/raw/prices",
    dividends_path: str = "data/raw/dividends/moex_dividends.parquet",
    output_path: str = "data/processed/dividend_events.parquet"
):
    """
    Собирает таблицу событий: для каждой отсечки находит цену закрытия
    в день отсечки и цену открытия на следующий день. Считает гэп.
    """
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    
    df_div = pd.read_parquet(dividends_path)
    df_div["cutoff_date"] = pd.to_datetime(df_div["cutoff_date"]).dt.normalize()
    
    events = []
    
    for ticker in df_div["ticker"].unique():
        price_file = Path(prices_dir) / f"{ticker}.parquet"
        if not price_file.exists():
            print(f"Нет цен для {ticker}")
            continue
        
        df_price = pd.read_parquet(price_file)
        df_price["date"] = pd.to_datetime(df_price["date"]).dt.normalize()
        df_price = df_price.sort_values("date").set_index("date")
        
        
        divs = df_div[df_div["ticker"] == ticker].sort_values("cutoff_date")
        
        for _, row in divs.iterrows():
            cutoff = row["cutoff_date"]
            
            
            try:
                close_before = df_price.loc[cutoff, "close"]
            except KeyError:
                continue
            
            
            future_dates = df_price.index[df_price.index > cutoff]
            if len(future_dates) == 0:
                continue
            
            next_date = future_dates[0]
            open_after = df_price.loc[next_date, "open"]
            
            
            gap = (open_after - close_before) / close_before
            div_yield = row["dividend_per_share"] / close_before
            
            events.append({
                "ticker": ticker,
                "cutoff_date": cutoff,
                "next_date": next_date,
                "close_before": close_before,
                "open_after": open_after,
                "dividend_per_share": row["dividend_per_share"],
                "currency": row.get("currency", "RUB"),
                "actual_gap": gap,
                "div_yield": div_yield,
                "gap_minus_div": gap - div_yield,  
                "days_to_cutoff": None,  
            })
    
    df_events = pd.DataFrame(events)
    
    
    df_events = df_events[
        (df_events["actual_gap"].between(-0.5, 0.5)) &  
        (df_events["div_yield"].between(0, 0.5))        
    ].copy()
    
    
    df_events = df_events.sort_values(["ticker", "cutoff_date"]).reset_index(drop=True)
    
    
    df_events.to_parquet(output_path, index=False)
    
    print(f"Событий: {len(df_events)}")
    print(f"Средний гэп: {df_events['actual_gap'].mean():.2%}")
    print(f"Средний дивиденд: {df_events['div_yield'].mean():.2%}")
    print(f"Средний (гэп - див): {df_events['gap_minus_div'].mean():.2%}")
    print(f"\nСохранено: {output_path}")
    
    return df_events





if __name__ == "__main__":
    df = build_dividend_events()
    
    # Быстрый анализ
    print("\n--- Топ-5 самых больших гэпов ---")
    print(df.nlargest(5, "actual_gap")[["ticker", "cutoff_date", "actual_gap", "div_yield"]])
    
    print("\n--- Топ-5 самых глубоких падений ---")
    print(df.nsmallest(5, "actual_gap")[["ticker", "cutoff_date", "actual_gap", "div_yield"]])
    
    print("\n--- Статистика по тикерам ---")
    print(df.groupby("ticker")["actual_gap"].agg(["mean", "std", "count"]).sort_values("mean"))