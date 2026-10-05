import { announce } from "../api.js?v=5";

function socketUrl(path) {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}${path}`;
}

function connect(path, onMessage) {
  let socket;
  let closed = false;
  let retry = 1000;
  let timer;
  const open = () => {
    if (closed) return;
    socket = new WebSocket(socketUrl(path));
    socket.addEventListener("open", () => { retry = 1000; });
    socket.addEventListener("message", event => {
      try { onMessage(JSON.parse(event.data)); } catch { /* polling remains available */ }
    });
    socket.addEventListener("close", () => {
      if (closed) return;
      timer = window.setTimeout(open, retry);
      retry = Math.min(retry * 2, 30000);
    });
    socket.addEventListener("error", () => socket.close());
  };
  open();
  return () => { closed = true; window.clearTimeout(timer); socket?.close(); };
}

export function connectChatRealtime(path, onMessage) {
  if (!path || !window.WebSocket) return () => {};
  return connect(path, message => {
    if (message.type === "chat.message" || message.type === "chat.system") onMessage(message);
  });
}

function updateNotificationBadge() {
  const avatar = document.querySelector(".account-avatar-wrap");
  if (!avatar) return;
  let badge = avatar.querySelector(".account-notification-badge");
  const current = Number(badge?.dataset.count || badge?.textContent?.replace("+", "") || 0);
  const count = current + 1;
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "account-notification-badge";
    badge.setAttribute("aria-label", "Thông báo chưa đọc");
    avatar.append(badge);
  }
  badge.dataset.count = String(count);
  badge.textContent = count > 99 ? "99+" : String(count);
}

function addRecentNotification(message) {
  const list = document.querySelector(".account-menu__recent-notifications");
  if (!list) return;
  list.querySelector(".account-menu__empty")?.remove();
  const item = document.createElement("a");
  item.className = "account-menu__recent-item is-unread";
  item.href = message.path || "#";
  const title = document.createElement("span");
  title.textContent = message.title || "Bạn có thông báo mới";
  const time = document.createElement("small");
  time.textContent = "Vừa xong";
  item.append(title, time);
  list.prepend(item);
  while (list.children.length > 10) list.lastElementChild.remove();
}

export function initRealtime() {
  if (!document.body.dataset.account || !window.WebSocket) return;
  connect("/ws/notifications/", message => {
    if (message.type !== "notification") return;
    updateNotificationBadge();
    addRecentNotification(message);
    announce(message.title || "Bạn có thông báo mới.");
    document.dispatchEvent(new CustomEvent("roomora:notification", { detail: message }));
  });
}
