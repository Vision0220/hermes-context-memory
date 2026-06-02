/**
 * Hermes Context Memory — Popup 脚本
 *
 * 从 chrome.storage.local 读取连接状态和最近 URL，更新 popup UI。
 */

document.addEventListener("DOMContentLoaded", async () => {
  const statusEl = document.getElementById("status");
  const dotEl = document.getElementById("dot");
  const statusTextEl = document.getElementById("statusText");
  const lastUrlEl = document.getElementById("lastUrl");

  try {
    const data = await chrome.storage.local.get([
      "connected",
      "lastUrl",
      "lastTitle",
      "lastSent",
    ]);

    if (data.connected) {
      statusEl.className = "status connected";
      dotEl.className = "dot green";
      statusTextEl.textContent = "Service Connected";
    } else {
      statusEl.className = "status disconnected";
      dotEl.className = "dot red";
      statusTextEl.textContent = "Service Disconnected";
    }

    if (data.lastUrl) {
      const title = data.lastTitle || "";
      const url = data.lastUrl;
      const time = data.lastSent
        ? new Date(data.lastSent).toLocaleTimeString("zh-CN")
        : "";
      lastUrlEl.textContent = `${time} ${title}\n${url}`;
    }
  } catch (err) {
    statusTextEl.textContent = "无法读取状态";
  }
});
