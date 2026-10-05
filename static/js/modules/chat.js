/**
 * Chat module: handles resilient 4s message polling, optimistic rendering,
 * and client UUID message deduplication.
 */
import { announce, generateUUID } from "../api.js?v=5";
import { connectChatRealtime } from "./realtime.js";

export function initChat(postFn, draftsMap) {
  const chatLog = document.querySelector("[data-chat-log]");
  if (!chatLog || chatLog.dataset.initialized) return;
  chatLog.dataset.initialized = "true";

  const send = document.querySelector("[data-chat-send]");
  let polling = false;

  const renderMessage = (message, prepend = false) => {
    if (chatLog.querySelector(`[data-message-id="${message.id}"]`)) return;
    chatLog.querySelector("[data-chat-empty]")?.remove();

    const div = document.createElement("div");
    const system = message.system || message.type === "chat.system";
    div.className = `chat-message${message.mine ? " mine" : ""}${system ? " system" : ""}`;
    div.dataset.messageId = message.id;
    div.id = `message-${message.id}`;

    const sender = document.createElement("strong");
    sender.textContent = system ? "ROOMORA" : message.sender;

    const body = document.createElement("p");
    body.textContent = message.body;

    const time = document.createElement("time");
    time.textContent = new Date(message.created_at).toLocaleString("vi-VN");

    if (system) {
      div.append(sender, body, time);
      if (prepend) chatLog.prepend(div);
      else chatLog.append(div);
      return;
    }

    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Ghim điều cần thống nhất";

    const pinForm = document.createElement("form");
    pinForm.method = "post";
    pinForm.action = "/roommates/action/fact-pin/";

    const hidden = (name, value) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = value;
      pinForm.append(input);
    };

    if (send) {
      hidden("csrfmiddlewaretoken", send.elements.csrfmiddlewaretoken.value);
      hidden("mutation_key", generateUUID());
      hidden("conversation", send.elements.conversation.value);
      hidden("source", message.id);
    }

    const label = document.createElement("label");
    label.textContent = "Thông tin hoặc câu hỏi";
    const input = document.createElement("input");
    input.name = "body";
    input.maxLength = 1000;
    input.required = true;
    input.value = message.body.slice(0, 1000);
    label.append(input);

    const button = document.createElement("button");
    button.textContent = "Ghim";
    pinForm.append(label, button);
    details.append(summary, pinForm);

    div.append(sender, body, time, details);
    if (prepend) chatLog.prepend(div);
    else chatLog.append(div);
  };

  async function poll() {
    if (polling || document.hidden) return;
    polling = true;
    try {
      let after = Math.max(
        0,
        ...[...chatLog.querySelectorAll("[data-message-id]")].map(row => Number(row.dataset.messageId))
      );
      let more = true;
      while (more) {
        const response = await fetch(`${chatLog.dataset.url}?after=${after}`, {
          headers: { Accept: "application/json" }
        });
        const result = await response.json();
        if (!response.ok) {
          const error = new Error(result.error || "Lỗi tải tin nhắn");
          error.status = response.status;
          throw error;
        }

        const atBottom = chatLog.scrollHeight - chatLog.scrollTop - chatLog.clientHeight < 70;
        result.messages.forEach(message => renderMessage(message));
        more = result.messages.length === 50;
        after = result.messages.at(-1)?.id ?? after;
        if (atBottom) chatLog.scrollTop = chatLog.scrollHeight;
      }
    } catch (error) {
      announce(error.message || "Chưa tải được tin mới. Bạn có thể thử lại.");
      if (error.status === 403 && send) {
        clearInterval(interval);
        const submitBtn = send.querySelector("button");
        if (submitBtn) submitBtn.disabled = true;
      }
    } finally {
      polling = false;
    }
  }

  const interval = setInterval(poll, 4000);
  const chatWsUrl = chatLog.dataset.wsUrl || (send?.elements.conversation ? `/ws/chat/${send.elements.conversation.value}/` : "");
  connectChatRealtime(chatWsUrl, message => {
    const atBottom = chatLog.scrollHeight - chatLog.scrollTop - chatLog.clientHeight < 70;
    renderMessage(message);
    if (atBottom) chatLog.scrollTop = chatLog.scrollHeight;
  });

  const sourceMessage = location.hash.startsWith("#message-")
    ? document.getElementById(location.hash.slice(1))
    : null;
  if (sourceMessage && chatLog.contains(sourceMessage)) {
    sourceMessage.scrollIntoView({ block: "nearest" });
  } else {
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  if (send) {
    send.querySelector("[data-opener]")?.addEventListener("click", event => {
      send.elements.body.value = event.target.dataset.opener;
      send.elements.body.dispatchEvent(new Event("input", { bubbles: true }));
      send.elements.body.focus();
    });

    let sending = false;
    send.addEventListener("submit", async event => {
      event.preventDefault();
      const draftHandler = draftsMap ? draftsMap.get(send) : null;
      if ((draftHandler && !draftHandler.canSubmit()) || !send.reportValidity() || sending) return;
      sending = true;

      const sentBody = send.elements.body.value;
      if (send.dataset.lastAttemptBody != null && send.dataset.lastAttemptBody !== sentBody.trim()) {
        send.elements.client_id.value = generateUUID();
        const mutKey = send.elements.namedItem("mutation_key");
        if (mutKey) mutKey.value = generateUUID();
      }
      send.dataset.lastAttemptBody = sentBody.trim();
      draftHandler?.persist();

      try {
        await postFn(send, event.submitter);
        const mutKey = send.elements.namedItem("mutation_key");
        if (mutKey) mutKey.value = generateUUID();
        send.elements.client_id.value = generateUUID();
        delete send.dataset.lastAttemptBody;
        if (send.elements.body.value === sentBody) {
          send.elements.body.value = "";
          draftHandler?.remove();
        } else {
          draftHandler?.persist();
        }
        await poll();
      } catch (error) {
        announce(error.message);
      } finally {
        sending = false;
      }
    });
  }

  document.querySelector("[data-older-messages]")?.addEventListener("click", async event => {
    const button = event.target;
    button.disabled = true;
    try {
      const response = await fetch(`${chatLog.dataset.url}?before=${button.dataset.olderMessages}`, {
        headers: { Accept: "application/json" }
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      [...result.messages].reverse().forEach(message => renderMessage(message, true));
      if (result.next_before) {
        button.dataset.olderMessages = result.next_before;
      } else {
        button.hidden = true;
      }
    } catch (error) {
      announce(error.message);
    } finally {
      button.disabled = false;
    }
  });
}

export function initConnectionWidget(postFn) {
  const widget = document.querySelector("[data-connection-widget]");
  if (!widget || widget.dataset.initialized) return;
  widget.dataset.initialized = "true";

  const panel = widget.querySelector("[data-chat-panel]");
  const toggle = widget.querySelector("[data-chat-toggle]");
  const close = widget.querySelector("[data-chat-close]");
  const heading = widget.querySelector("[data-chat-heading]");
  const state = widget.querySelector("[data-chat-state]");
  const log = widget.querySelector("[data-chat-widget-log]");
  const form = widget.querySelector("[data-chat-widget-form]");
  const error = widget.querySelector("[data-chat-widget-error]");
  const contacts = widget.querySelectorAll("[data-chat-person]");
  const toolsToggle = widget.querySelector("[data-chat-tools-toggle]");
  const toolsMenu = widget.querySelector("[data-chat-tools-menu]");
  const workspaceFeatureButton = widget.querySelector('[data-chat-feature="workspace"]');
  const featureContents = widget.querySelectorAll("[data-chat-feature-content]");
  const composerInput = form?.elements.body;

  const resizeComposer = () => {
    if (!composerInput) return;
    composerInput.style.height = "36px";
    const height = Math.min(composerInput.scrollHeight, 110);
    composerInput.style.height = `${height}px`;
    composerInput.style.overflowY = composerInput.scrollHeight > 110 ? "auto" : "hidden";
  };
  let selected = null, lastId = 0, loadingVersion = null, sending = false, selectionVersion = 0, closeRealtime = null;

  const showPanel = () => {
    panel.hidden = false;
    toggle.hidden = true;
    toggle.setAttribute("aria-expanded", "true");
  };

  const hidePanel = () => {
    panel.hidden = true;
    toggle.hidden = false;
    toggle.setAttribute("aria-expanded", "false");
  };

  const showFeature = feature => {
    if (!selected) return;
    const content = [...featureContents].find(item => item.dataset.chatFeatureContent === selected.id);
    if (!content) return;
    if (feature === "workspace") {
      if (selected.workspaceUrl) {
        window.location.assign(selected.workspaceUrl);
        return;
      }
      const workspaceForm = content.querySelector("[data-chat-workspace-form]");
      toolsMenu.hidden = true;
      toolsToggle.setAttribute("aria-expanded", "false");
      if (workspaceForm) workspaceForm.requestSubmit();
      else announce("Lời mời cùng tìm nhà đã được gửi hoặc không gian đã mở.");
      return;
    }
    featureContents.forEach(item => { item.hidden = item !== content; });
    content.querySelectorAll("[data-chat-feature-section]").forEach(section => {
      section.hidden = section.dataset.chatFeatureSection !== feature;
    });
    toolsMenu.hidden = true;
    toolsToggle.setAttribute("aria-expanded", "false");
  };

  const render = message => {
    if (log.querySelector(`[data-widget-message-id="${message.id}"]`)) return;
    const item = document.createElement("div");
    const system = message.system || message.type === "chat.system";
    item.className = `connection-widget-message${message.mine ? " mine" : ""}${system ? " system" : ""}`;
    item.dataset.widgetMessageId = message.id;
    const author = document.createElement("strong");
    author.textContent = system ? "ROOMORA" : (message.mine ? "Bạn" : message.sender);
    const body = document.createElement("p");
    body.textContent = message.body;
    const time = document.createElement("time");
    time.textContent = new Date(message.created_at).toLocaleString("vi-VN", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"
    });
    item.append(author, body, time);
    if (system && message.status === "pending" && String(message.invitee_id) === String(widget.dataset.chatActorId)) {
      const responseForm = document.createElement("form");
      responseForm.className = "connection-widget-system-actions";
      responseForm.method = "post";
      responseForm.action = widget.dataset.chatWorkspaceResponseUrl;
      const csrf = form?.elements.csrfmiddlewaretoken?.value || "";
      responseForm.innerHTML = `<input type="hidden" name="csrfmiddlewaretoken" value="${csrf}"><input type="hidden" name="mutation_key" value="${generateUUID()}"><input type="hidden" name="workspace" value="${message.workspace_id}"><button type="submit">Xác nhận cùng tìm nhà</button>`;
      responseForm.addEventListener("submit", async event => {
        event.preventDefault();
        const submit = event.submitter || responseForm.querySelector("button");
        if (submit) submit.disabled = true;
        try {
          await postFn(responseForm, submit);
          body.textContent = message.body.replace("Lời mời cùng tìm nhà:", "Lời mời cùng tìm nhà đã được đồng ý:");
          responseForm.remove();
          announce("Đã xác nhận cùng tìm nhà.");
        } catch (failure) {
          announce(failure.message);
          if (submit) submit.disabled = false;
        }
      });
      item.append(responseForm);
    }
    log.append(item);
  };

  async function refresh() {
    if (!selected || loadingVersion === selectionVersion) return;
    const version = selectionVersion;
    loadingVersion = version;
    try {
      let more = true;
      while (more) {
        const response = await fetch(`${selected.url}?after=${lastId}`, {
          headers: { Accept: "application/json" },
          credentials: "same-origin"
        });
        const result = await response.json();
        if (!response.ok) {
          const failure = new Error(result.error || "Không tải được tin nhắn.");
          failure.status = response.status;
          throw failure;
        }
        if (version !== selectionVersion) return;
        state.textContent = result.connected ? "Đã kết nối" : "Đang chờ đồng ý kết nối";
        log.querySelector("[data-widget-empty]")?.remove();
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
        result.messages.forEach(message => {
          render(message);
          if (Number.isFinite(Number(message.id))) lastId = Math.max(lastId, Number(message.id));
        });
        more = result.messages.length === 50;
        if (atBottom) log.scrollTop = log.scrollHeight;
      }
      if (!log.children.length) {
        const empty = document.createElement("p");
        empty.className = "muted";
        empty.dataset.widgetEmpty = "";
        empty.textContent = "Chưa có tin nhắn. Hãy gửi lời chào đầu tiên.";
        log.append(empty);
      }
      if (error) error.textContent = "";
    } catch (failure) {
      if (version === selectionVersion && error) {
        error.textContent = failure.message;
        if (failure.status === 403) {
          form.elements.body.disabled = true;
          form.querySelector("button[type=submit]").disabled = true;
        }
      }
    } finally {
      if (loadingVersion === version) loadingVersion = null;
    }
  }

  const openChat = button => {
    if (sending) return;
    selectionVersion += 1;
    closeRealtime?.();
    selected = { id: button.dataset.chatPerson, url: button.dataset.chatUrl };
    selected.wsUrl = button.dataset.chatWsUrl;
    selected.workspaceUrl = button.dataset.chatWorkspaceUrl || "";
    lastId = 0;
    log.replaceChildren();
    if (error) error.textContent = "";
    heading.textContent = button.dataset.chatName;
    if (workspaceFeatureButton) workspaceFeatureButton.textContent = selected.workspaceUrl ? "Không gian chung" : "Cùng tìm nhà";
    contacts.forEach(contact => contact.classList.toggle("is-active", contact === button));
    featureContents.forEach(content => { content.hidden = true; });
    toolsMenu.hidden = true;
    toolsToggle.setAttribute("aria-expanded", "false");
    state.textContent = "Đang tải cuộc trò chuyện…";
    form.elements.target.value = selected.id;
    form.elements.body.value = "";
    form.elements.body.disabled = false;
    form.querySelector("button[type=submit]").disabled = false;
    form.elements.client_id.value = generateUUID();
    showPanel();
    closeRealtime = connectChatRealtime(selected.wsUrl, message => {
      const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
      render(message);
      if (Number.isFinite(Number(message.id))) lastId = Math.max(lastId, Number(message.id));
      if (atBottom) log.scrollTop = log.scrollHeight;
    });
    refresh();
    form.elements.body.focus();
  };

  document.querySelectorAll("[data-chat-person]").forEach(button => {
    button.addEventListener("click", () => openChat(button));
  });

  toggle?.addEventListener("click", () => panel.hidden ? showPanel() : hidePanel());
  close?.addEventListener("click", hidePanel);
  composerInput?.addEventListener("input", resizeComposer);
  resizeComposer();
  toolsToggle?.addEventListener("click", () => {
    toolsMenu.hidden = !toolsMenu.hidden;
    toolsToggle.setAttribute("aria-expanded", String(!toolsMenu.hidden));
  });
  widget.querySelectorAll("[data-chat-feature]").forEach(button => {
    button.addEventListener("click", () => showFeature(button.dataset.chatFeature));
  });

  widget.querySelectorAll("[data-chat-feature-form]").forEach(featureForm => {
    featureForm.addEventListener("submit", async event => {
      event.preventDefault();
      const submit = event.submitter || featureForm.querySelector("button[type=submit]");
      if (submit) submit.disabled = true;
      try {
        await postFn(featureForm, submit);
        if (featureForm.action.includes("workspace-invite")) {
          featureForm.replaceWith(Object.assign(document.createElement("p"), {
            className: "muted",
            textContent: "Đã gửi lời mời cùng tìm nhà."
          }));
          await refresh();
        } else if (submit) {
          submit.textContent = "Đã xác nhận";
        }
        announce("Đã cập nhật trong cuộc trò chuyện.");
      } catch (failure) {
        announce(failure.message);
        if (submit) submit.disabled = false;
      }
    });
  });

  form?.addEventListener("submit", async event => {
    event.preventDefault();
    if (!selected || sending || !form.reportValidity()) return;
    sending = true;
    const button = form.querySelector("button[type=submit]");
    if (button) button.disabled = true;
    const body = form.elements.body.value;
    try {
      await postFn(form);
    form.elements.body.value = "";
    resizeComposer();
      form.elements.client_id.value = generateUUID();
      await refresh();
    } catch (failure) {
      if (error) error.textContent = failure.message;
      form.elements.body.value = body;
    } finally {
      sending = false;
      if (button) button.disabled = false;
    }
  });

  const initial = new URLSearchParams(location.search).get("chat");
  const initialButton = [...document.querySelectorAll("[data-chat-person]")].find(
    button => button.dataset.chatPerson === initial
  );
  if (initialButton) openChat(initialButton);

  setInterval(() => {
    if (!panel.hidden && selected) refresh();
  }, 4000);
}
