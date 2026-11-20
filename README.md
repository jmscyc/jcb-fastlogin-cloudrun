# JCB 悠遊卡自動搶登錄系統 Pro (JCB FastLogin Pro)

專為台灣 JCB 晶緻卡/極緻卡悠遊卡「自動加值 10% 現金回饋」活動打造的極速搶登錄與卡片庫管理系統。
針對悠遊卡官方活動登錄入口：`https://ezweb.easycard.com.tw/Event01/JCBLoginServlet`。

---

## 🎯 未來 AI 改版快速指南 (重要！下載與修改指引)

為了讓您在日後將程式碼下載並交給其他 AI 進行改版時最為省心，系統核心功能已經**高度收斂整併為單一核心檔案**，您不需要下載一堆零散的小檔案：

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

## 🌟 核心特色功能

1. **極速核心整併為單一引擎 (`login_engine.py`)**：
   - 杜絕過度拆檔，把所有高難度的非同步探測、防檢測 Stealth、NTP 校時、OCR 打碼、防休眠與截圖存證**全部收斂在 `login_engine.py`**，AI 能在單一上下文中一眼看穿全貌，改版不容易出 Bug！
2. **三段式變速衝刺與 NTP 毫秒校時**：
   - 連線台灣國家時間伺服器（`time.stdtime.gov.tw`）校正本機偏差。
   - 08:55 起節能低頻巡邏，倒數 5 秒自動切換至 **120ms~150ms 極限搶衝**！
3. **離線 OCR 圖形驗證碼辨識**：
   - 內建 `ddddocr` 毫秒級本機離線推論；環境未安裝時自動平滑降級為人工輸入，絕不閃退。
4. **原生 JS Alert 彈窗自動攔截**：
   - 自動捕獲並確認瀏覽器原生彈窗（如「驗證碼錯誤」、「本月已登錄」），徹底杜絕無聲卡死 180 秒的隱患。
5. **Windows 智慧防休眠鎖 (Sleep Guard)**：
   - 在預約倒數與搶登期間，直接透過 Windows API 鎖定電源狀態，防止電腦睡著或螢幕黑屏，任務結束自動釋放。
6. **全真演練模擬模式 (Dry-Run)**：
   - 控制台隨時可一鍵點擊「🧪 演練模擬搶登」，載入本機全真模擬 JCB 登錄網頁，立即驗證填寫速度與截圖留底。
7. **視覺快照留底與 Web Audio 和弦提示音**：
   - 搶登成功瞬間自動保存高解析度全頁截圖；瀏覽器端透過 Web Audio API 合成輕快登登登和弦音。

---

## 🚀 快速啟動

### Windows 使用者
雙擊專案目錄下的 **`start.bat`** 即可：
- 自動檢查 Python 與 Playwright 瀏覽器環境
- 自動啟動本機後台伺服器
- 自動打開瀏覽器前往：`http://localhost:8088`

### macOS / Linux 使用者
```bash
chmod +x run.sh
./run.sh
```

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
