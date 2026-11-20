import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Any

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 建立卡片表 (增加 priority 優先序)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        credit_card_prefix TEXT NOT NULL, -- 前 6 碼
        credit_card_suffix TEXT NOT NULL, -- 後 4 碼
        easycard_number TEXT NOT NULL,     -- 16 碼悠遊卡號
        is_selected INTEGER DEFAULT 1,     -- 預設是否勾選
        priority INTEGER DEFAULT 0,        -- 排序優先權
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 檢查並補充 priority 欄位 (相容既有資料庫)
    cursor.execute("PRAGMA table_info(cards)")
    columns = [col[1] for col in cursor.fetchall()]
    if "priority" not in columns:
        cursor.execute("ALTER TABLE cards ADD COLUMN priority INTEGER DEFAULT 0")
    
    # 建立登錄紀錄表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS login_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER NOT NULL,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        status TEXT NOT NULL,              -- 'SUCCESS', 'ALREADY_REGISTERED', 'FULL', 'FAILED'
        message TEXT,
        session_id TEXT,                   -- 本次執行的識別碼
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
    )
    """)
    
    # 建立系統設定表 (儲存 Webhook, Telegram Token, 定時搶登設定)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    conn.commit()
    conn.close()

def get_cards() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards ORDER BY priority DESC, id ASC")
    cards = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return cards

def add_card(name: str, credit_prefix: str, credit_suffix: str, easycard_number: str, priority: int = 0) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cards (name, credit_card_prefix, credit_card_suffix, easycard_number, priority)
        VALUES (?, ?, ?, ?, ?)
    """, (name.strip(), credit_prefix.strip(), credit_suffix.strip(), easycard_number.strip().replace("-", "").replace(" ", ""), priority))
    card_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return card_id

def update_card_priority(card_id: int, priority: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE cards SET priority = ? WHERE id = ?", (priority, card_id))
    conn.commit()
    conn.close()

def update_card_selection(card_id: int, is_selected: bool):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE cards SET is_selected = ? WHERE id = ?", (1 if is_selected else 0, card_id))
    conn.commit()
    conn.close()

def delete_card(card_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    cursor.execute("DELETE FROM login_records WHERE card_id = ?", (card_id,))
    conn.commit()
    conn.close()

def record_login(card_id: int, status: str, message: str, session_id: str):
    now = datetime.now()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO login_records (card_id, year, month, status, message, session_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (card_id, now.year, now.month, status, message, session_id))
    conn.commit()
    conn.close()

def get_current_session_id() -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'current_session_id'")
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else ""

def set_current_session_id(session_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('current_session_id', ?)", (session_id,))
    conn.commit()
    conn.close()

def get_settings() -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}

def update_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_cards_with_stats() -> List[Dict[str, Any]]:
    current_year = datetime.now().year
    current_session = get_current_session_id()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cards = get_cards()
    result = []
    
    for card in cards:
        card_id = card["id"]
        # 計算今年成功次數
        cursor.execute("""
            SELECT COUNT(DISTINCT month) as success_count
            FROM login_records
            WHERE card_id = ? AND year = ? AND status IN ('SUCCESS', 'ALREADY_REGISTERED')
        """, (card_id, current_year))
        year_success = cursor.fetchone()["success_count"]
        
        # 獲取本次 session 最新紀錄
        cursor.execute("""
            SELECT status, message, timestamp
            FROM login_records
            WHERE card_id = ? AND session_id = ?
            ORDER BY id DESC LIMIT 1
        """, (card_id, current_session))
        current_record = cursor.fetchone()
        
        card_data = dict(card)
        card_data["year_success_count"] = year_success
        card_data["current_session_status"] = current_record["status"] if current_record else "WAITING"
        card_data["current_session_message"] = current_record["message"] if current_record else "尚未執行"
        card_data["current_session_time"] = current_record["timestamp"] if current_record else None
        
        # 格式化顯示遮罩
        card_data["masked_credit"] = f"{card['credit_card_prefix']}******{card['credit_card_suffix']}"
        easy = card['easycard_number']
        card_data["masked_easycard"] = f"{easy[:4]} **** **** {easy[-4:]}" if len(easy) == 16 else easy
        
        result.append(card_data)
        
    conn.close()
    return result

def clear_current_session_records():
    current_session = get_current_session_id()
    if not current_session:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM login_records WHERE session_id = ?", (current_session,))
    conn.commit()
    conn.close()

def clear_card_yearly_records(card_id: Optional[int] = None):
    current_year = datetime.now().year
    conn = get_connection()
    cursor = conn.cursor()
    if card_id:
        cursor.execute("DELETE FROM login_records WHERE card_id = ? AND year = ?", (card_id, current_year))
    else:
        cursor.execute("DELETE FROM login_records WHERE year = ?", (current_year,))
    conn.commit()
    conn.close()

def clear_all_records():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM login_records")
    conn.commit()
    conn.close()

def export_cards_json() -> str:
    cards = get_cards()
    return json.dumps(cards, ensure_ascii=False, indent=2)

def import_cards_json(data_str: str) -> int:
    cards = json.loads(data_str)
    count = 0
    for c in cards:
        if "name" in c and "credit_card_prefix" in c and "credit_card_suffix" in c and "easycard_number" in c:
            add_card(c["name"], c["credit_card_prefix"], c["credit_card_suffix"], c["easycard_number"], c.get("priority", 0))
            count += 1
    return count
