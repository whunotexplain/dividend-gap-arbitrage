import requests


def fetch_moex_tickers():
    """
    Получает список акций с Т+2 (основной режим TQBR) через MOEX ISS API.
    """
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    
    params = {
        "iss.meta": "off",
        "iss.only": "securities",  # Только таблица securities, без marketdata
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        columns = data["securities"]["columns"]
        rows = data["securities"]["data"]
        
        # Индексы колонок (проверяем наличие, чтобы не упасть с ValueError)
        col_map = {}
        for idx, col in enumerate(columns):
            col_map[col] = idx
        
        # Обязательные поля
        secid_idx = col_map.get("SECID")
        name_idx = col_map.get("SHORTNAME") or col_map.get("NAME")
        prevprice_idx = col_map.get("PREVPRICE")
        
        if secid_idx is None:
            raise ValueError("SECID не найден в ответе")
        
        print(f"Всего инструментов: {len(rows)}\n")
        print(f"{'Тикер':<10} | {'Название':<25} | {'Цена пред. дня'}")
        print("-" * 60)
        
        for row in rows[:10]:
            secid = row[secid_idx]
            name = row[name_idx] if name_idx is not None else "N/A"
            price = row[prevprice_idx] if prevprice_idx is not None else "N/A"
            print(f"{secid:<10} | {str(name):<25} | {price}")
            
        return rows, columns
        
    except requests.exceptions.RequestException as e:
        print(f"Ошибка сети: {e}")
    except (KeyError, ValueError) as e:
        print(f"Ошибка данных: {e}")


if __name__ == "__main__":
    fetch_moex_tickers()