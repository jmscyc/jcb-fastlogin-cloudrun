# JCB 悠遊卡自動搶登錄系統 Pro (JCB FastLogin Pro)

專為台灣 JCB 晶緻卡/極緻卡悠遊卡「自動加值 10% 現金回饋」活動打造的極速搶登錄與卡片庫管理系統。
針對悠遊卡官方活動登錄入口：`https://ezweb.easycard.com.tw/Event01/JCBLoginServlet`。

---

## 🚀 完整執行教學（雙軌模式：本地視窗版 vs 雲端無人值守版）

本系統提供 **兩種執行方式**，您可以自由選擇最適合您的方式：

```mermaid
graph TD
    A[JCB 搶登系統] --> B[方式一：本機圖形化介面 (推薦新手)]
    A --> C[方式二：GitHub Actions 雲端自動搶登 (免開電腦)]
    
    B --> B1[雙擊 start.bat 啟動]
    B1 --> B2[瀏覽器打開 http://localhost:8088]
    B2 --> B3[貼上卡片 / 設定預約時間 / 模擬測試]

    C --> C1[設定 GitHub Secrets 卡號]
    C1 --> C2[每月 1、11、21 日 08:58 雲端伺服器自動開機搶登]
    C2 --> C3[搶登結果自動 Telegram / Webhook 推播]
```

---

### 💻 方式一：本地電腦執行（最直覺、有視覺介面與音效）

適合放在本機電腦，搶登時可親眼看到瀏覽器分頁自動填寫，並享有專屬提示音與截圖存證。

#### 1. 初次安裝環境（只需做一次）
- 確保電腦已安裝 **Python 3.10+**（安裝時請務必勾選 `Add Python to PATH`）。
- 進入專案資料夾，安裝相依套件與瀏覽器核心：
  ```bash
  pip install fastapi uvicorn playwright jinja2 aiohttp pydantic
  playwright install chromium
  ```
  *(可選) 若需要圖形驗證碼自動辨識，可安裝：`pip install ddddocr`*

#### 2. 一鍵啟動服務
- **Windows 使用者**：直接在資料夾內**雙擊 `start.bat`** 即可！
  - 腳本會自動檢查環境並在瀏覽器中彈出主控台：`http://localhost:8088`。
- **macOS / Linux 使用者**：
  ```bash
  chmod +x run.sh
  ./run.sh
  ```
  或者手動執行：
  ```bash
  python3 -m uvicorn main:app --host 0.0.0.0 --port 8088
  ```

#### 3. 網頁操作 4 步驟（只要 30 秒）
1. **新增卡片**：點擊「智慧快速貼上」，支援直接貼上如 `富邦JCB 356800 1234 0123456789012345`，系統會自動拆解帶入。
2. **勾選卡片**：在卡片列表勾選本次欲搶登的卡片（支援多卡並行）。
3. **驗證流程（重要！）**：
   - 點擊 **「🧪 演練模擬搶登 (Dry-Run)」** 按鈕，系統會啟動本機全真模擬登錄網頁，您能親眼看到自動填入卡號、點擊送出、播放成功提示音並產出截圖。
4. **正式預約 / 開跑**：
   - **當天 08:55 前預約**：在「預約定時排程開跑」輸入開搶時間（例如 `2026-12-01 08:59:58`），點擊「開始定時搶登」。系統會自動啟用**防休眠鎖**，倒數計時並在時間到達時自動變速衝刺開搶！
   - **立即手動開跑**：清空預約時間，直接點擊「開始搶登錄任務」。

---

### ☁️ 方式二：GitHub Actions 雲端自動搶登（不用開電腦、全自動）

適合出門在外、不想開電腦，由 GitHub 雲端微型伺服器在每月 1、11、21 日早上 08:58 自動開機搶登。

#### 1. 前往雲端專案庫
- 打開您的專屬雲端執行庫：[`jcb-fastlogin-cloudrun`](https://github.com/jmscyc/jcb-fastlogin-cloudrun)

#### 2. 設定卡片與通知機密變數 (Secrets)
前往該專案的 **Settings** -> **Secrets and variables** -> **Actions** -> 點擊 **New repository secret**：
- **`JCB_CARDS_JSON`**（必填，要搶登的卡片清單 JSON）：
  ```json
  [
    {
      "name": "富邦JCB",
      "credit_card_prefix": "356890",
      "credit_card_suffix": "1234",
      "easycard_number": "0123456789012345",
      "is_selected": 1,
      "priority": 10
    }
  ]
  ```
  *(💡 小技巧：在本地網頁介面點擊「備份匯出卡片」即可一鍵複製整段 JSON 貼過來！)*
- **`TG_BOT_TOKEN`** 與 **`TG_CHAT_ID`**（選填）：搶登成功或額滿時，自動傳送 Telegram 訊息到您的手機。

#### 3. 執行時機
- **全自動排程**：每逢每月 **1日、11日、21日 台灣時間 08:58 (UTC 00:58)**，GitHub Actions 會自動開機、精密對時校正、09:00:00 衝刺搶登。
- **手動測試執行**：前往專案的 **Actions** 標籤頁 -> 點選 **`JCB FastLogin 雲端自動搶登`** -> 點擊右側 **「Run workflow」** 按鈕即可立即在雲端試跑。

---

## 🎯 未來 AI 改版快速指南 (下載與修改指引)

為了讓您在日後將程式碼下載並交給其他 AI 進行改版時最為省心，系統核心功能已經**高度收斂整併為單一核心檔案**：

### 📌 改版時只需下載以下檔案給 AI：

| 您想改版的功能領域 | 🎯 唯一只需下載的檔案 | 說明 |
| :--- | :--- | :--- |
| **搶登邏輯 / 速度 / 驗證碼 / NTP / 探測 / 推播** | **`login_engine.py`** ⭐️⭐️⭐️ | **【最核心單檔】** 整合了：<br>1. Playwright 搶登錄流程與 DOM 注入<br>2. 毫秒級三段式變速衝刺與探測<br>3. 國家標準 NTP 精準對時 (UTC+8)<br>4. 圖形驗證碼離線 OCR 辨識<br>5. Windows 防休眠鎖 (Sleep Guard)<br>6. Telegram / Webhook 即時通知<br>7. 自動全頁截圖留底與原生彈窗 Alert 攔截 |
| **網頁 API 介面 / 排程邏輯** | **`main.py`** | FastAPI 後端 API、定時排程定時器、卡片增刪改查介面。 |
| **資料庫結構 / 儲存欄位** | **`database.py`** | SQLite 資料庫結構、卡片清單、年度與當次登錄紀錄管理。 |
| **前端網頁按鈕與操作視覺** | **`templates/index.html`<br>`static/js/app.js`** | 儀表板頁面、智慧貼上解析、Web Audio 音效、即時日誌流。 |

> 💡 **AI 提示詞範例**：  
> 「請根據我上傳的 `login_engine.py`，幫我修改搶登時的重試頻率，並增加新的驗證碼解析邏輯。」

---

## 🌟 核心特色功能一覽

1. **極速核心整併為單一引擎 (`login_engine.py`)**：杜絕過度拆檔，AI 單檔即掌握全貌。
2. **大螢幕實時倒數儀表板 (HUD)**：介面頂部整合百毫秒動態倒數、NTP 校準時鐘，倒數 30 秒自動變色警戒、5 秒極速衝刺！
3. **雙門戶雙通道探測 (Dual Portal)**：同步輪詢 `JCBLoginServlet` 登錄頁與 `JCBMainServlet` 活動主頁，官方一解禁按鈕立即毫秒級切入。
4. **防封鎖 HTTP Proxy 代理支援**：設定頁面可選配填入 HTTP Proxy，遇高頻探測或 IP 暫時受阻時自動轉發。
5. **卡片庫高優先權智慧快選 (⭐ 勾選前2張)**：一鍵依優先度選取前 N 張卡片，免去手動逐一勾選的繁瑣。
6. **📸 彈窗截圖燈箱 (Lightbox Modal)**：登錄成果與報錯畫面直接在當前頁面彈窗放大檢視，毋須跳轉新分頁。
7. **三段式變速衝刺與 NTP 毫秒校時**：連線台灣標準時間，開搶前 5 秒切換至 120ms~150ms 極限衝刺。
8. **離線 OCR 圖形驗證碼辨識**：支援毫秒級自動打碼，無套件時自動優雅降級為人工輸入。
9. **原生 JS Alert 彈窗自動攔截**：自動捕獲並確認網頁對話框，杜絕無聲超時。
10. **Windows 智慧防休眠鎖**：預約排程與搶登期間防止系統睡眠，任務結束自動釋放。
11. **全真演練模擬模式 (Dry-Run)**：隨時可一鍵模擬實戰填表與截圖。
12. **視覺存證快照與成功提示音**：搶登成功自動存檔截圖至 `static/screenshots/` 並發送專屬和弦音。

---

## 📁 完整精簡目錄結構

```text
jcb-fastlogin/
├── login_engine.py        ⭐️ 【搶登核心單檔】包含 Playwright、NTP、OCR、防休眠、推播
├── main.py                🖥️ 【API與排程】FastAPI 服務與排程計時器
├── database.py            💾 【資料儲存】SQLite 卡片庫與登錄統計
├── cli_runner.py          ☁️ 【命令列工具】提供無 UI 或 GitHub Actions 快速調度
├── cards.db               🗃️ 【本地資料庫】加密/安全的卡片與歷程資料庫
├── start.bat              ⚡ 【啟動腳本】Windows 一鍵啟動
├── run.sh                 ⚡ 【啟動腳本】Linux / macOS 一鍵啟動
├── templates/
│   └── index.html         🎨 本機 Web 控制面板
└── static/
    ├── css/style.css      💅 現代化玻璃擬物深色主題樣式
    ├── js/app.js          ⚡ 前端互動、智慧貼上、Web Audio 音效
    └── screenshots/       📸 搶登成果與歷程截圖留底存放區
```
