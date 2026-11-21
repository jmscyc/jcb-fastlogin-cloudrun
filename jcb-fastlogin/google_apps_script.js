/**
 * JCB FastLogin - Google 試算表雙向同步專用腳本 (Google Apps Script)
 * 
 * 設定說明：
 * 1. 打開您的 Google 試算表，第一行填入欄位名稱：
 *    A: 卡片暱稱 | B: 前6碼 | C: 後4碼 | D: 悠遊卡16碼 | E: 優先權 | F: 當前狀態 | G: 更新時間
 * 2. 點擊頂部選單「擴充功能」 -> 「Apps Script」
 * 3. 清空原有代碼，將本檔案內容全部複製貼上。
 * 4. 點擊右上角「部署」 -> 「新增部署」 -> 點齒輪選「網頁應用程式 (Web App)」：
 *    - 執行身分：我 (您的 Google 帳號)
 *    - 誰可以存取：任何人 (Anyone)
 * 5. 點擊部署後複製產生的「網頁應用程式網址」，貼回 JCB 控制台即可秒同步！
 */

const SYNC_SECRET_KEY = "888"; // 您的專屬金鑰 (預設 888)

function doGet(e) {
  const params = e.parameter || {};
  const action = params.action;
  const key = params.key;

  if (key !== SYNC_SECRET_KEY) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: "金鑰錯誤 (Unauthorized)" }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const rows = sheet.getDataRange().getValues();
  
  if (action === "get_cards") {
    const cards = [];
    // 從第 2 列開始讀取 (第 1 列為標題)
    for (let i = 1; i < rows.length; i++) {
      const r = rows[i];
      if (!r[0]) continue; // 卡名為空則跳過
      cards.push({
        id: i,
        name: String(r[0]),
        credit_card_prefix: String(r[1]).padStart(6, '0'),
        credit_card_suffix: String(r[2]).padStart(4, '0'),
        easycard_number: String(r[3]),
        priority: parseInt(r[4]) || 10,
        status: String(r[5] || "嘗試中"),
        is_selected: 1
      });
    }
    return ContentService.createTextOutput(JSON.stringify({ status: "ok", cards: cards }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  return ContentService.createTextOutput(JSON.stringify({ status: "ok", message: "JCB Sync API Ready" }))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const key = data.key;

    if (key !== SYNC_SECRET_KEY) {
      return ContentService.createTextOutput(JSON.stringify({ status: "error", message: "金鑰錯誤 (Unauthorized)" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    const action = data.action;

    if (action === "save_cards") {
      const cards = data.cards || [];
      // 保留第一行標題，清除下方所有舊資料
      const lastRow = sheet.getLastRow();
      if (lastRow > 1) {
        sheet.getRange(2, 1, lastRow - 1, 7).clearContent();
      }

      if (cards.length > 0) {
        const rows = cards.map(c => [
          c.name,
          "'" + c.credit_card_prefix, // 加引號防止 0 開頭被轉成數字
          "'" + c.credit_card_suffix,
          "'" + c.easycard_number,
          c.priority || 10,
          c.status || "嘗試中",
          new Date().toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })
        ]);
        sheet.getRange(2, 1, rows.length, 7).setValues(rows);
      }
      return ContentService.createTextOutput(JSON.stringify({ status: "ok", message: `成功儲存 ${cards.length} 張卡片！` }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (action === "update_status") {
      // 供雲端搶登程式自動回寫單張卡片狀態
      const cardName = data.card_name;
      const status = data.status;
      const rows = sheet.getDataRange().getValues();
      for (let i = 1; i < rows.length; i++) {
        if (rows[i][0] === cardName) {
          sheet.getRange(i + 1, 6).setValue(status);
          sheet.getRange(i + 1, 7).setValue(new Date().toLocaleString("zh-TW", { timeZone: "Asia/Taipei" }));
          break;
        }
      }
      return ContentService.createTextOutput(JSON.stringify({ status: "ok", message: "狀態已更新" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
