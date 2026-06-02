/**
 * Hermes Context Memory — 浏览器扩展后台脚本 (MV3 Service Worker)
 *
 * 监听 tab 激活、tab 更新、窗口焦点变化，
 * 将事件 POST 到本地服务。
 */

const API_URLS = [
  "http://127.0.0.1:1833/api/browser/events",
  "http://localhost:1833/api/browser/events",
];
const HEALTH_URLS = [
  "http://127.0.0.1:1833/health",
  "http://localhost:1833/health",
];
const DEBOUNCE_MS = 2000;

let activeApiUrl = API_URLS[0]; // 缓存可用的 URL
const recentEvents = new Map();

/**
 * 发送浏览器事件到本地服务
 */
async function sendEvent(tab) {
  if (!tab || !tab.url) return;
  if (tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
    return;
  }

  const tabKey = `${tab.id}_${tab.url}`;
  const lastSent = recentEvents.get(tabKey);
  if (lastSent && Date.now() - lastSent < DEBOUNCE_MS) return;
  recentEvents.set(tabKey, Date.now());

  // 清理过期记录
  if (recentEvents.size > 100) {
    const now = Date.now();
    for (const [key, time] of recentEvents) {
      if (now - time > 60000) recentEvents.delete(key);
    }
  }

  const event = {
    ts: new Date().toISOString(),
    browser: detectBrowser(),
    url: tab.url,
    title: tab.title || "",
    tab_id: String(tab.id),
    window_id: String(tab.windowId || ""),
    active: tab.active !== false,
  };

  // 尝试所有 API URL
  for (const apiUrl of [activeApiUrl, ...API_URLS.filter(u => u !== activeApiUrl)]) {
    try {
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(event),
        signal: AbortSignal.timeout(5000),
      });
      if (response.ok) {
        activeApiUrl = apiUrl; // 缓存成功的 URL
        chrome.storage.local.set({
          connected: true,
          lastUrl: tab.url,
          lastTitle: tab.title,
          lastSent: new Date().toISOString(),
          lastError: "",
        });
        return;
      }
    } catch {}
  }

  // 所有 URL 都失败
  chrome.storage.local.set({ connected: false, lastError: "All endpoints unreachable" });
}

/**
 * 检测浏览器类型 (MV3 兼容)
 */
function detectBrowser() {
  // MV3 service worker: navigator.userAgentData 可用
  if (typeof navigator !== "undefined" && navigator.userAgentData) {
    const brands = navigator.userAgentData.brands.map(b => b.brand);
    if (brands.some(b => b.includes("Edge"))) return "edge";
    if (brands.some(b => b.includes("Chromium"))) return "chrome";
  }
  // Fallback
  if (typeof navigator !== "undefined" && navigator.userAgent) {
    if (navigator.userAgent.includes("Edg/")) return "edge";
    if (navigator.userAgent.includes("Chrome/")) return "chrome";
  }
  return "chrome"; // 默认
}

// ── 事件监听 ────────────────────────────────────────────────

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    sendEvent(tab);
  } catch {}
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" || changeInfo.url) {
    sendEvent(tab);
  }
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  try {
    const tabs = await chrome.tabs.query({ active: true, windowId });
    if (tabs.length > 0) sendEvent(tabs[0]);
  } catch {}
});

// ── 健康检查 ────────────────────────────────────────────────

async function checkConnection() {
  for (const url of HEALTH_URLS) {
    try {
      const response = await fetch(url, {
        method: "GET",
        signal: AbortSignal.timeout(3000),
      });
      if (response.ok) {
        chrome.storage.local.set({ connected: true, lastError: "" });
        return;
      }
    } catch {}
  }
  chrome.storage.local.set({ connected: false, lastError: "Health check failed" });
}

chrome.alarms.create("healthCheck", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "healthCheck") checkConnection();
});

checkConnection();
console.log("Hermes Context Memory extension started (MV3)");
