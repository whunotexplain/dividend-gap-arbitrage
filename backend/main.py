from app.src.data.moex_parser import fetch_ohlcv

df = fetch_ohlcv("SBER", "2019-01-01", "2025-12-31")
print(len(df))
print(df["date"].min(), df["date"].max())