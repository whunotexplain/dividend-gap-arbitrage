import requests
import pandas as pd

def get_tickers_df():
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    r = requests.get(url, params={"iss.meta": "off", "iss.only": "securities"})
    data = r.json()["securities"]
    return pd.DataFrame(data=data["data"], columns=data["columns"])

df = get_tickers_df()
print(df[["SECID", "SHORTNAME", "PREVPRICE"]].head(10))
