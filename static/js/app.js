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
                <td>${statusBadge}</td>
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
                loadCards();
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
