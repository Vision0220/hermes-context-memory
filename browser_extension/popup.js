/**
 * Hermes Context Memory — Popup 脚本
 *
 * 主动查询后端 /health 和 /api/status。
 * 防御性检查 chrome.storage 是否可用。
 */

const API_BASES = ["http://127.0.0.1:1833", "http://localhost:1833"];

// 安全读取 storage
function storageGet(keys) {
  return new Promise((resolve) => {
    try {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(keys, resolve);
      } else {
        resolve({});
      }
    } catch {
      resolve({});
    }
  });
}

// 安全写入 storage
function storageSet(data) {
  try {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set(data);
    }
  } catch {}
}

document.addEventListener("DOMContentLoaded", async () => {
  const statusEl = document.getElementById("status");
  const dotEl = document.getElementById("dot");
  const statusTextEl = document.getElementById("statusText");
  const detailsEl = document.getElementById("details");
  const lastUrlEl = document.getElementById("lastUrl");
  const debugEl = document.getElementById("debugOutput");

  // 1. 从 storage 读缓存（快速显示）
  const cached = await storageGet(["connected", "lastUrl", "lastTitle", "lastSent", "lastError"]);
  if (cached.connected) {
    setStatus("connected", "Connecting...");
  } else if (cached.lastError) {
    setStatus("disconnected", cached.lastError);
  }
  if (cached.lastUrl) {
    const time = cached.lastSent
      ? new Date(cached.lastSent).toLocaleTimeString("zh-CN")
      : "";
    lastUrlEl.textContent = `${time} ${cached.lastTitle || ""}\n${cached.lastUrl}`;
  }

  // 2. 主动查询后端
  await queryBackend();

  // 3. Test Connection 按钮
  const testBtn = document.getElementById("testBtn");
  if (testBtn) {
    testBtn.addEventListener("click", async () => {
      debugEl.textContent = "Testing...";
      await queryBackend(true);
    });
  }

  async function queryBackend(showDebug) {
    let lastErr = "";
    for (const base of API_BASES) {
      try {
        const healthResp = await fetch(base + "/health", {
          signal: AbortSignal.timeout(5000),
        });
        if (!healthResp.ok) {
          lastErr = "HTTP " + healthResp.status;
          continue;
        }
        const health = await healthResp.json();

        let statusData = null;
        try {
          const statusResp = await fetch(base + "/api/status", {
            signal: AbortSignal.timeout(5000),
          });
          if (statusResp.ok) statusData = await statusResp.json();
        } catch {}

        setStatus("connected", "Service Connected");

        var info = "Status: " + health.status + " | DB: " + health.database;
        info += " | Events: " + health.total_events;
        info += " | Sessions: " + health.total_sessions;
        info += " | Capture: " + (health.capture_active ? "ON" : "OFF");
        info += " | VLM: " + (health.vlm_available ? "ON" : "OFF");
        detailsEl.textContent = info;

        if (showDebug) {
          debugEl.textContent = JSON.stringify(health, null, 2);
        }

        storageSet({ connected: true, lastError: "", apiUrl: base });
        return;
      } catch (err) {
        lastErr = err.message || "Network error";
      }
    }

    setStatus("disconnected", "Disconnected: " + lastErr);
    detailsEl.textContent = "Tried: " + API_BASES.join(", ");
    if (showDebug) {
      debugEl.textContent = "Error: " + lastErr + "\nEndpoints: " + API_BASES.join(", ");
    }
    storageSet({ connected: false, lastError: lastErr });
  }

  function setStatus(state, text) {
    statusEl.className = "status " + state;
    dotEl.className = "dot " + (state === "connected" ? "green" : "red");
    statusTextEl.textContent = text;
  }
});
