import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import sys
import time
from datetime import datetime

# 設定檔案路徑
EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "目前持有零股.xlsx")

def show_loading(message):
    """顯示載入中的狀態，不會換行"""
    sys.stdout.write(f"\r{message}")
    sys.stdout.flush()

def clear_loading():
    """清除載入中的狀態列"""
    sys.stdout.write("\r" + " " * 50 + "\r")
    sys.stdout.flush()

def get_current_holdings(filepath):
    """
    讀取 Excel，回傳「目前真正持有」的股票代號集合。
    """
    if not os.path.exists(filepath):
        # 這裡不print錯誤，避免蓋掉 loading 狀態，僅回傳空集合
        return set()

    try:
        df = pd.read_excel(filepath, header=0, dtype=str)
        held_stocks = set()
        
        for index, row in df.iterrows():
            if len(row) < 17: continue

            stock_id = str(row.iloc[2]).strip()
            is_sold_raw = str(row.iloc[16]).strip().lower()
            
            if is_sold_raw != 'true':
                held_stocks.add(stock_id)
                
        return held_stocks

    except Exception:
        return set()

def fetch_entrust_stocks():
    """
    功能 1: 抓取「零股屋可委託股票」
    條件: 
    1. 藍色字體 
    2. 委託期限 >= 今天 
    3. 隱藏欄位包含 'ing_entrust' (進行中)
    """
    url = "https://www.stockroomtw.com/entrust_index.php"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    # --- 顯示狀態 ---
    show_loading("系統狀態：正在爬取【可委託股票】資料中，請稍後...")

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except Exception as e:
        clear_loading()
        print(f"連線失敗 (entrust_index): {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # --- 爬蟲結束，清除狀態 ---
    clear_loading()

    today = datetime.now().date()
    current_year = datetime.now().year

    print("今日抓取零股屋可委託股票")
    print("股票代號/股票名稱/委託期限/紀念品")
    print("-" * 50)

    rows = soup.find_all('tr')
    found_count = 0

    for row in rows:
        stock_id_tag = row.find('th', scope='row')
        if not stock_id_tag: continue
        stock_id = stock_id_tag.text.strip()

        tds = row.find_all('td')
        # 這裡需要確保至少有 5 個欄位 (因為隱藏狀態欄通常在後面)
        if len(tds) < 3: continue

        # --- 新增篩選條件: 檢查隱藏狀態 (ing_entrust) ---
        # 通常這個隱藏欄位在最後一個 td，我們取最後一個比較保險
        status_td_text = tds[-1].text.strip()
        
        # 如果不是進行中 (ing_entrust)，就跳過
        # 這會過濾掉 end_entrust (已結束) 的資料
        if "ing_entrust" not in status_td_text:
            continue

        # --- 顏色篩選 (藍色) ---
        name_span = tds[0].find('span')
        if not name_span: continue
        style_attr = name_span.get('style', '').lower()
        if 'color:blue' not in style_attr: continue
        stock_name = name_span.text.strip()

        # --- 日期篩選 ---
        date_str_raw = tds[1].text.strip()
        try:
            deadline_date = datetime.strptime(f"{current_year}/{date_str_raw}", "%Y/%m/%d").date()
            if deadline_date >= today:
                chinese_date_str = f"{deadline_date.month}月{deadline_date.day}號"
                souvenir = tds[2].text.strip()
                print(f"{stock_id}/{stock_name}/{chinese_date_str}/{souvenir}")
                found_count += 1
        except ValueError:
            continue

    if found_count == 0:
        print("目前無符合條件股票")

def fetch_recent_stocks(held_stocks):
    """
    功能 2: 抓取「近三日可買入股票」
    條件: 在 id="filter-body1" 區塊內 + 不在 held_stocks 清單中
    """
    url = "https://www.stockroomtw.com/index.php"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    # --- 顯示狀態 ---
    show_loading("系統狀態：正在爬取【近三日新增】資料中，請稍後...")

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response.encoding = 'utf-8'
    except Exception as e:
        clear_loading()
        print(f"連線失敗 (index): {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')

    # --- 爬蟲結束，清除狀態 ---
    clear_loading()

    print("\n近三日可買入股票")
    print("股票代號/股票名稱/股價/預計發放的紀念品")
    print("-" * 50)

    tbody = soup.find('tbody', id='filter-body1')
    
    rows = []
    if tbody:
        rows = tbody.find_all('tr')

    found_count = 0
    has_real_data = False
    
    if rows:
        if len(rows) == 1 and "無資料" in rows[0].text:
            has_real_data = False
        else:
            has_real_data = True

    if has_real_data:
        for row in rows:
            stock_id_tag = row.find('th', scope='row')
            if not stock_id_tag: continue
            stock_id = stock_id_tag.text.strip()

            if stock_id in held_stocks:
                continue

            tds = row.find_all('td')
            if len(tds) < 3: continue

            name_cell = tds[0]
            stock_name_tag = name_cell.find('span')
            if stock_name_tag:
                stock_name = stock_name_tag.text.strip()
                full_text = name_cell.get_text(strip=True)
                stock_price = full_text.replace(stock_name, "").strip()
                if not stock_price: stock_price = "詳見網頁"
            else:
                stock_name = name_cell.text.strip()
                stock_price = "未知"

            souvenir = tds[2].text.strip()
            print(f"{stock_id}/{stock_name}/{stock_price}/{souvenir}")
            found_count += 1

    if found_count == 0:
        print("目前無符合條件股票")

if __name__ == "__main__":
    # --- 顯示狀態: 讀取 Excel ---
    show_loading("系統狀態：正在讀取 Excel 檔案...")
    my_stocks = get_current_holdings(EXCEL_PATH)
    clear_loading() # 清除 Excel 讀取狀態
    
    # 執行功能
    fetch_entrust_stocks()
    fetch_recent_stocks(my_stocks)
    
    input("\n執行完畢，請按 Enter 鍵離開...")