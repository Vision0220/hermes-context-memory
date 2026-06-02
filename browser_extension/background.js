/**
 * Hermes Context Memory — 浏览器扩展后台脚本
 *
 * 监听 tab 激活、tab 更新、窗口焦点变化，
 * 将事件 POST 到本地服务 http://127.0.0.1:1733/api/browser/events
 */

const API_URL = "http://127.0.0.1:1833/api/browser/events";
const DEBOUNCE_MS = 2000; // 去抖：同一 tab 2 秒内不重复发送

// 记录最近发送的 tab 事件，用于去抖
const recentEvents = new Map();

/**
 * 发送浏览器事件到本地服务
 */
async function sendEvent(tab) {
  if (!tab || !tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
    return; // 跳过内部页面
  }

  const tabKey = `${tab.id}_${tab.url}`;

  // 去抖检查
  const lastSent = recentEvents.get(tabKey);
  if (lastSent && Date.now() - lastSent < DEBOUNCE_MS) {
    return;
  }
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

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(event),
    });

    if (response.ok) {
      // 存储状态供 popup 显示
      chrome.storage.local.set({
        connected: true,
        lastUrl: tab.url,
        lastTitle: tab.title,
        lastSent: new Date().toISOString(),
      });
    }
  } catch (err) {
    console.warn("Hermes Context Memory: 连接失败", err.message);
    chrome.storage.local.set({ connected: false });
  }
}

/**
 * 检测浏览器类型
 */
function detectBrowser() {
  const ua = navigator.userAgent;
  if (ua.includes("Edg/")) return "edge";
  if (ua.includes("Chrome/")) return "chrome";
  if (ua.includes("Firefox/")) return "firefox";
  return "unknown";
}

// ── 事件监听 ────────────────────────────────────────────────

// Tab 激活
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    sendEvent(tab);
  } catch (e) {
    // tab 可能已关闭
  }
});

// Tab URL 更新（页面加载、导航）
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" || changeInfo.url) {
    sendEvent(tab);
  }
});

// 窗口焦点变化
chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  try {
    const tabs = await chrome.tabs.query({ active: true, windowId });
    if (tabs.length > 0) {
      sendEvent(tabs[0]);
    }
  } catch (e) {
    // 窗口可能已关闭
  }
});

// ── 定期健康检查 ──────────────────────────────────────────────

async function checkConnection() {
  try {
    const response = await fetch("http://127.0.0.1:1833/health", {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });
    chrome.storage.local.set({ connected: response.ok });
  } catch {
    chrome.storage.local.set({ connected: false });
  }
}

// 每 30 秒检查连接状态
chrome.alarms.create("healthCheck", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "healthCheck") {
    checkConnection();
  }
});

// 初始检查
checkConnection();

console.log("Hermes Context Memory 扩展已启动");
