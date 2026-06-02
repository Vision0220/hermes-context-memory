/**
 * Hermes Context Memory — Popup 脚本
 *
 * 主动查询后端 /health 和 /api/status，同时读取 storage 缓存。
 * 如果后端不可用，显示明确的断开信息和错误原因。
 */

const API_BASES = ["http://127.0.0.1:1833", "http://localhost:1833"];

document.addEventListener("DOMContentLoaded", async () => {
  const statusEl = document.getElementById("status");
  const dotEl = document.getElementById("dot");
  const statusTextEl = document.getElementById("statusText");
  const detailsEl = document.getElementById("details");
  const lastUrlEl = document.getElementById("lastUrl");
  const debugEl = document.getElementById("debugOutput");

  // 1. 先从 storage 读缓存（快速显示）
  try {
    const cached = await chrome.storage.local.get([
      "connected", "lastUrl", "lastTitle", "lastSent", "lastError",
    ]);
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
  } catch (e) {
    // storage 可能不可用
  }

  // 2. 主动查询后端（真实状态）
  await queryBackend();

  // 3. Test Connection 按钮
  const testBtn = document.getElementById("testBtn");
  if (testBtn) {
    testBtn.addEventListener("click", async () => {
      debugEl.textContent = "Testing...";
      await queryBackend(true);
    });
  }

  async function queryBackend(showDebug = false) {
    let lastErr = "";
    for (const base of API_BASES) {
      try {
        // Health check
        const healthResp = await fetch(`${base}/health`, {
          signal: AbortSignal.timeout(5000),
        });
        if (!healthResp.ok) {
          lastErr = `HTTP ${healthResp.status}`;
          continue;
        }
        const health = await healthResp.json();

        // Status (may fail, that's ok)
        let status = null;
        try {
          const statusResp = await fetch(`${base}/api/status`, {
            signal: AbortSignal.timeout(5000),
          });
          if (statusResp.ok) status = await statusResp.json();
        } catch {}

        // Update UI
        setStatus("connected", "Service Connected");

        let details = `Status: ${health.status} | DB: ${health.database}`;
        details += ` | Events: ${health.total_events}`;
        details += ` | Sessions: ${health.total_sessions}`;
        details += ` | Capture: ${health.capture_active ? "ON" : "OFF"}`;
        details += ` | VLM: ${health.vlm_available ? "ON" : "OFF"}`;
        detailsEl.textContent = details;

        if (showDebug) {
          debugEl.textContent = JSON.stringify(health, null, 2);
        }

        // Save to storage
        chrome.storage.local.set({
          connected: true,
          lastError: "",
          apiUrl: base,
        });
        return;
      } catch (err) {
        lastErr = err.message || "Network error";
      }
    }

    // All bases failed
    setStatus("disconnected", `Disconnected: ${lastErr}`);
    detailsEl.textContent = `Tried: ${API_BASES.join(", ")}`;
    if (showDebug) {
      debugEl.textContent = `Error: ${lastErr}\nEndpoints: ${API_BASES.join(", ")}`;
    }
    chrome.storage.local.set({
      connected: false,
      lastError: lastErr,
    });
  }

  function setStatus(state, text) {
    statusEl.className = `status ${state}`;
    dotEl.className = `dot ${state === "connected" ? "green" : "red"}`;
    statusTextEl.textContent = text;
  }
});
