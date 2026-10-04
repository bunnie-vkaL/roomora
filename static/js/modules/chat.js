/**
 * Chat module: handles resilient 4s message polling, optimistic rendering,
 * and client UUID message deduplication.
 */
import { announce, generateUUID } from "../api.js";

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
    div.className = `chat-message${message.mine ? " mine" : ""}`;
    div.dataset.messageId = message.id;
    div.id = `message-${message.id}`;

    const sender = document.createElement("strong");
    sender.textContent = message.sender;

    const body = document.createElement("p");
    body.textContent = message.body;

    const time = document.createElement("time");
    time.textContent = new Date(message.created_at).toLocaleString("vi-VN");

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
