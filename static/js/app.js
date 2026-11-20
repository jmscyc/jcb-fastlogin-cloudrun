let pollTimer = null;
let isEngineRunning = false;

document.addEventListener("DOMContentLoaded", () => {
    loadCards();
    startStatusPolling();
    loadSettings();
    
    // 悠遊卡輸入自動格式化
    const easyInput = document.getElementById("card-easycard");
    if (easyInput) {
        easyInput.addEventListener("input", (e) => {
            let val = e.target.value.replace(/\D/g, "");
            if (val.length > 16) val = val.substring(0, 16);
            let formatted = val.replace(/(\d{4})(?=\d)/g, "$1 ");
            e.target.value = formatted;
        });
    }
});

async function loadCards() {
    try {
        const res = await fetch("/api/cards");
        const data = await res.json();
        renderCardsTable(data.cards);
    } catch (err) {
        console.error("載入卡片失敗:", err);
    }
}

function renderCardsTable(cards) {
    const tbody = document.getElementById("cards-tbody");
    if (!cards || cards.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:#94a3b8; padding: 24px;">尚未新增任何 JCB 卡片，請點選上方「新增卡片」或「批次匯入」</td></tr>`;
        return;
    }

    let allChecked = true;
    tbody.innerHTML = cards.map(c => {
        if (!c.is_selected) allChecked = false;
        
        let statusBadge = "";
        switch (c.current_session_status) {
            case "SUCCESS":
                statusBadge = `<span class="status-tag success">✓ 本次成功</span>`;
                break;
            case "ALREADY_REGISTERED":
                statusBadge = `<span class="status-tag registered">ⓘ 本月已登錄</span>`;
                break;
            case "FULL":
                statusBadge = `<span class="status-tag full">⚠ 額滿</span>`;
                break;
            case "FAILED":
                statusBadge = `<span class="status-tag failed" title="${c.current_session_message}">✕ 失敗 (${c.current_session_message})</span>`;
                break;
            default:
                statusBadge = `<span class="status-tag waiting">未執行</span>`;
                break;
        }

        return `
            <tr>
                <td><input type="checkbox" class="card-select" data-id="${c.id}" ${c.is_selected ? "checked" : ""} onchange="toggleSelect(${c.id}, this.checked)"></td>
                <td><span class="badge" style="background:#f1f5f9; color:#475569; font-weight:bold;">${c.priority || 0}</span></td>
                <td class="card-title-cell">${escapeHtml(c.name)}</td>
                <td><code>${c.masked_credit}</code></td>
                <td><code>${c.masked_easycard}</code></td>
                <td><span class="stat-pill">${c.year_success_count} 次</span></td>
                <td>
                    ${statusBadge}
                    ${c.current_session_screenshot ? `<div style="margin-top:4px;"><a href="${c.current_session_screenshot}" target="_blank" class="btn-secondary" style="display:inline-block; padding:2px 6px; font-size:11px; text-decoration:none;">📸 檢視截圖</a></div>` : ''}
                </td>
                <td>
                    <button class="btn-secondary" style="padding: 4px 8px; font-size: 12px; color: #ef4444;" onclick="deleteCard(${c.id}, '${escapeHtml(c.name)}')">刪除</button>
                </td>
            </tr>
        `;
    }).join("");

    const checkAll = document.getElementById("check-all");
    if (checkAll) checkAll.checked = allChecked && cards.length > 0;
}

function openModal(id) {
    document.getElementById(id).classList.add("show");
}

function closeModal(id) {
    document.getElementById(id).classList.remove("show");
}

function openAddModal() { openModal("add-modal"); }
function openSettingsModal() { openModal("settings-modal"); }
function openImportModal() { openModal("import-modal"); }

async function saveCard(e) {
    e.preventDefault();
    const name = document.getElementById("card-name").value.trim();
    const prefix = document.getElementById("card-prefix").value.trim();
    const suffix = document.getElementById("card-suffix").value.trim();
    const easy = document.getElementById("card-easycard").value.replace(/\s+/g, "");
    const priority = parseInt(document.getElementById("card-priority").value) || 0;

    try {
        const res = await fetch("/api/cards", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: name,
                credit_card_prefix: prefix,
                credit_card_suffix: suffix,
                easycard_number: easy,
                priority: priority
            })
        });

        const data = await res.json();
        if (res.ok) {
            closeModal("add-modal");
            document.getElementById("add-card-form").reset();
            loadCards();
        } else {
            alert(data.detail || "新增卡片失敗");
        }
    } catch (err) {
        alert("連線錯誤: " + err.message);
    }
}

async function deleteCard(cardId, name) {
    if (!confirm(`確定要刪除卡片「${name}」及其相關登錄紀錄嗎？`)) return;
    try {
        await fetch(`/api/cards/${cardId}`, { method: "DELETE" });
        loadCards();
    } catch (err) {
        alert("刪除失敗: " + err.message);
    }
}

async function toggleSelect(cardId, isChecked) {
    try {
        await fetch("/api/cards/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ card_id: cardId, is_selected: isChecked })
        });
    } catch (err) {
        console.error("更新選取狀態失敗:", err);
    }
}

function toggleSelectAll(masterCheckbox) {
    const isChecked = masterCheckbox.checked;
    const checkboxes = document.querySelectorAll(".card-select");
    checkboxes.forEach(cb => {
        cb.checked = isChecked;
        const id = parseInt(cb.getAttribute("data-id"));
        toggleSelect(id, isChecked);
    });
}

async function exportCards() {
    try {
        const res = await fetch("/api/cards/export");
        const jsonText = await res.text();
        const blob = new Blob([jsonText], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `jcb_cards_backup_${new Date().toISOString().slice(0,10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        alert("匯出失敗: " + err.message);
    }
}

async function importCards() {
    const raw = document.getElementById("import-json").value.trim();
    if (!raw) return alert("請貼上 JSON 格式資料");
    try {
        const res = await fetch("/api/cards/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ json_data: raw })
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            closeModal("import-modal");
            document.getElementById("import-json").value = "";
            loadCards();
        } else {
            alert(data.detail || "匯入失敗");
        }
    } catch (err) {
        alert("匯入錯誤: " + err.message);
    }
}

async function loadSettings() {
    try {
        const res = await fetch("/api/settings");
        const data = await res.json();
        if (data.settings) {
            document.getElementById("set-tg-token").value = data.settings.tg_bot_token || "";
            document.getElementById("set-tg-chatid").value = data.settings.tg_chat_id || "";
            document.getElementById("set-webhook").value = data.settings.webhook_url || "";
        }
    } catch (err) {
        console.error("載入設定失敗:", err);
    }
}

async function saveSettings(e) {
    e.preventDefault();
    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                tg_bot_token: document.getElementById("set-tg-token").value,
                tg_chat_id: document.getElementById("set-tg-chatid").value,
                webhook_url: document.getElementById("set-webhook").value
            })
        });
        const data = await res.json();
        alert(data.message);
        closeModal("settings-modal");
    } catch (err) {
        alert("儲存設定失敗: " + err.message);
    }
}

async function testNotify() {
    try {
        const res = await fetch("/api/settings/test-notify", { method: "POST" });
        const data = await res.json();
        alert(data.message);
    } catch (err) {
        alert("發送測試通知失敗: " + err.message);
    }
}

async function clearRecords(type) {
    let confirmMsg = "";
    let endpoint = "";
    if (type === "session") {
        confirmMsg = "確定要清除「本次執行」的登錄結果狀態嗎？";
        endpoint = "/api/records/clear-session";
    } else if (type === "yearly") {
        confirmMsg = "確定要重置「今年度已登錄次數」歸零嗎？";
        endpoint = "/api/records/clear-yearly";
    } else {
        confirmMsg = "確定要清除「全部卡片的所有歷史紀錄」嗎？此操作不可復原！";
        endpoint = "/api/records/clear-all";
    }

    if (!confirm(confirmMsg)) return;

    try {
        const res = await fetch(endpoint, { method: "POST" });
        const data = await res.json();
        alert(data.message);
        loadCards();
    } catch (err) {
        alert("清除失敗: " + err.message);
    }
}

async function startTask() {
    const retryInterval = parseInt(document.getElementById("cfg-retry-interval").value) || 500;
    const workers = parseInt(document.getElementById("cfg-workers").value) || 2;
    const headless = document.getElementById("cfg-browser-mode").value === "true";
    const scheduleTime = document.getElementById("cfg-schedule").value.trim() || null;

    const autoCaptcha = document.getElementById("cfg-auto-captcha") ? document.getElementById("cfg-auto-captcha").checked : true;
    const enableNtp = document.getElementById("cfg-enable-ntp") ? document.getElementById("cfg-enable-ntp").checked : true;
    const sprintMode = document.getElementById("cfg-sprint-mode") ? document.getElementById("cfg-sprint-mode").checked : true;

    try {
        const res = await fetch("/api/task/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                retry_interval_ms: retryInterval,
                max_concurrent_workers: workers,
                headless: headless,
                scheduled_time: scheduleTime,
                auto_captcha: autoCaptcha,
                enable_ntp: enableNtp,
                sprint_mode: sprintMode
            })
        });
        const data = await res.json();
        if (data.status === "ok") {
            appendLog(`[系統] ${data.message}`);
        } else {
            alert(data.message);
        }
    } catch (err) {
        alert("啟動任務失敗: " + err.message);
    }
}

async function stopTask() {
    try {
        const res = await fetch("/api/task/stop", { method: "POST" });
        const data = await res.json();
        appendLog(`[系統] ${data.message}`);
    } catch (err) {
        alert("停止任務失敗: " + err.message);
    }
}

async function startDryRun() {
    const autoCaptcha = document.getElementById("cfg-auto-captcha") ? document.getElementById("cfg-auto-captcha").checked : true;
    
    appendLog("🧪 正在啟動演練模擬模式 (Dry-Run)... 預計 5 秒內完成模擬填表與送出！");
    try {
        const res = await fetch("/api/task/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                retry_interval_ms: 300,
                max_concurrent_workers: 1,
                headless: false,
                auto_captcha: autoCaptcha,
                enable_ntp: false,
                sprint_mode: false,
                dry_run: true
            })
        });
        const data = await res.json();
        if (data.status === "ok") {
            appendLog(`[系統] ${data.message}`);
        } else {
            alert(data.message);
        }
    } catch (err) {
        alert("啟動模擬失敗: " + err.message);
    }
}

// 🔊 搶登成功專屬清脆和弦音 (使用標準 Web Audio API，無需外載 mp3)
function playSuccessSound() {
    const audioToggle = document.getElementById("cfg-enable-audio");
    if (audioToggle && !audioToggle.checked) return;
    
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        const ctx = new AudioContext();
        
        const notes = [523.25, 659.25, 783.99, 1046.50];
        notes.forEach((freq, i) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = "triangle";
            osc.frequency.setValueAtTime(freq, ctx.currentTime + i * 0.12);
            
            gain.gain.setValueAtTime(0.15, ctx.currentTime + i * 0.12);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.12 + 0.35);
            
            osc.connect(gain);
            gain.connect(ctx.destination);
            
            osc.start(ctx.currentTime + i * 0.12);
            osc.stop(ctx.currentTime + i * 0.12 + 0.35);
        });
    } catch (e) {
        console.warn("無法播放提示音:", e);
    }
}

let lastKnownSuccessCount = 0;

function startStatusPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const res = await fetch("/api/task/status");
            const data = await res.json();
            updateEngineUI(data.is_running);
            if (data.logs && data.logs.length > 0) {
                renderLogs(data.logs);
            }
            if (data.is_running || isEngineRunning !== data.is_running) {
                const cRes = await fetch("/api/cards");
                const cData = await cRes.json();
                renderCardsTable(cData);
                const curSuccess = cData.filter(c => c.current_session_status === "SUCCESS").length;
                if (curSuccess > lastKnownSuccessCount) {
                    playSuccessSound();
                    lastKnownSuccessCount = curSuccess;
                }
            }
            isEngineRunning = data.is_running;
        } catch (err) {
            console.error("輪詢狀態失敗", err);
        }
    }, 1500);
}

function updateEngineUI(isRunning) {
    const indicator = document.getElementById("engine-status");
    const btnStart = document.getElementById("btn-start");
    const btnStop = document.getElementById("btn-stop");

    if (isRunning) {
        indicator.className = "status-indicator running";
        indicator.querySelector(".text").textContent = "搶登執行中...";
        btnStart.disabled = true;
        btnStop.disabled = false;
    } else {
        indicator.className = "status-indicator idle";
        indicator.querySelector(".text").textContent = "待命中";
        btnStart.disabled = false;
        btnStop.disabled = true;
    }
}

function renderLogs(logs) {
    const container = document.getElementById("log-container");
    const badge = document.getElementById("log-count");
    badge.textContent = `${logs.length} 則訊息`;
    
    container.innerHTML = logs.map(line => `<div class="log-line">${escapeHtml(line)}</div>`).join("");
    container.scrollTop = container.scrollHeight;
}

function appendLog(line) {
    const container = document.getElementById("log-container");
    const div = document.createElement("div");
    div.className = "log-line";
    div.textContent = line;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
    if (!text) return "";
    return text.replace(/[&<>"']/g, function(m) {
        return {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        }[m];
    });
}

// 📅 一鍵帶入下個搶登日 (每月 1, 11, 21 日 08:59:55)
function fillNextSchedule() {
    const now = new Date();
    const candidateDays = [1, 11, 21];
    let target = null;
    
    for (let day of candidateDays) {
        const d = new Date(now.getFullYear(), now.getMonth(), day, 8, 59, 55);
        if (d > now) {
            target = d;
            break;
        }
    }
    
    // 若本月已過 21 號，則指向下個月 1 號
    if (!target) {
        target = new Date(now.getFullYear(), now.getMonth() + 1, 1, 8, 59, 55);
    }
    
    const pad = (n) => String(n).padStart(2, "0");
    const formatted = `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(target.getDate())} ${pad(target.getHours())}:${pad(target.getMinutes())}:${pad(target.getSeconds())}`;
    
    const scheduleInput = document.getElementById("cfg-schedule");
    if (scheduleInput) {
        scheduleInput.value = formatted;
        appendLog(`[系統] 已自動設定下個搶登目標時刻: ${formatted}`);
    }
}

// ⚡ 智慧快速貼上自動解析卡號
function parseSmartPaste(text) {
    if (!text || text.trim().length < 6) return;
    
    // 1. 匹配悠遊卡 16 碼 (連續 16 位數字或以空格分隔)
    const easyMatch = text.match(/\b\d{16}\b/) || text.match(/\b\d{4}\s\d{4}\s\d{4}\s\d{4}\b/);
    if (easyMatch) {
        const rawEasy = easyMatch[0].replace(/\s/g, "");
        const formatted = rawEasy.replace(/(\d{4})(?=\d)/g, "$1 ");
        document.getElementById("card-easycard").value = formatted;
    }
    
    // 2. 匹配信用卡卡號 (若有 16 碼 JCB: 35 開頭)
    const jcbMatch = text.match(/\b35\d{14}\b/) || text.match(/\b35\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/);
    if (jcbMatch) {
        const rawCard = jcbMatch[0].replace(/[-\s]/g, "");
        document.getElementById("card-prefix").value = rawCard.substring(0, 6);
        document.getElementById("card-suffix").value = rawCard.substring(12, 16);
    } else {
        // 分別嘗試抓 6 碼前綴 (35xxxx)
        const prefixMatch = text.match(/\b35\d{4}\b/);
        if (prefixMatch) document.getElementById("card-prefix").value = prefixMatch[0];
        
        // 嘗試抓後 4 碼 (例如: 尾號 1234 或末四碼 1234)
        const suffixMatch = text.match(/(?:末|尾|後|碼)[\s:：]*(\d{4})/i) || text.match(/[-*]{2,}(\d{4})/);
        if (suffixMatch) document.getElementById("card-suffix").value = suffixMatch[1];
    }
    
    // 3. 嘗試猜測卡名 (排除數字與特定符號)
    const nameMatch = text.match(/(富邦|玉山|聯邦|中信|國泰|台新|吉鶴|熊本熊|魔BUY|現金回饋)[a-zA-Z0-9\u4e00-\u9fa5]*/);
    if (nameMatch && !document.getElementById("card-name").value) {
        document.getElementById("card-name").value = nameMatch[0];
    }
}
