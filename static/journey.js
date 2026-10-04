(() => {
  "use strict";
  const status = document.querySelector("#journey-status");
  const announce = (message) => { if (status) status.textContent = message; };
  const key = () => crypto.randomUUID();
  const resetKey = (form) => { const input = form.elements.namedItem("mutation_key"); if (input) input.value = key(); };
  async function post(form, submitter = null) {
    let response;
    try {
      response = await fetch(form.action, {method: "POST", body: new FormData(form, submitter), headers: {Accept: "application/json"}, credentials: "same-origin"});
    } catch {
      throw new Error("Chưa kết nối được với ứng dụng. Bản nháp vẫn giữ trên máy; hãy thử lưu lại khi có kết nối.");
    }
    if (!response.headers.get("Content-Type")?.includes("application/json")) throw new Error("Phiên làm việc đã thay đổi. Đăng nhập lại; bản nháp vẫn được giữ trên máy.");
    const result = await response.json();
    if (!response.ok) { const error = new Error(result.error || "Thao tác chưa hoàn tất."); error.status = response.status; throw error; }
    return result;
  }
  document.querySelectorAll("[data-go-back]").forEach(button => button.addEventListener("click", () => history.back()));
  document.querySelectorAll(".routine-track").forEach(track => {
    const minute = value => { const [hour, minute] = value.split(":").map(Number); return hour * 60 + minute; };
    const start = minute(track.dataset.routineStart), end = minute(track.dataset.routineEnd);
    const add = (from, until) => { const span = document.createElement("span"); span.className = "sleep-segment"; span.style.left = `${from / 1440 * 100}%`; span.style.width = `${(until - from) / 1440 * 100}%`; track.append(span); };
    if (end < start) { add(start, 1440); add(0, end); } else add(start, end);
  });
  const deck = document.querySelector("[data-swipe-deck]");
  if (deck) {
    const cards = [...deck.querySelectorAll("[data-person-card]")];
    let index = 0, busy = false;
    const show = () => { cards.forEach((card, i) => card.hidden = i !== index); deck.querySelector("[data-deck-empty]").hidden = index < cards.length; };
    show();
    deck.addEventListener("submit", async event => {
      const form = event.target.closest("[data-deck-action]");
      if (!form) return;
      event.preventDefault();
      if (busy) return;
      busy = true;
      deck.setAttribute("aria-busy", "true");
      const controls = [...deck.querySelectorAll("button")];
      controls.forEach(button => button.disabled = true);
      try {
        const result = await post(form, event.submitter);
        resetKey(form);
        if (form.dataset.deckAction === "save") {
          const saved = form.elements.saved;
          saved.value = saved.value === "1" ? "0" : "1";
          const button = form.querySelector("button");
          button.textContent = saved.value === "0" ? "Bỏ lưu" : "Lưu xem sau";
          button.setAttribute("aria-label", saved.value === "0" ? `Bỏ lưu ${form.dataset.candidateName}` : `Lưu ${form.dataset.candidateName} để xem sau`);
          announce(saved.value === "0" ? "Đã lưu riêng, chưa gửi lượt quan tâm." : "Đã bỏ lưu.");
        } else {
          if (result.redirect.includes("/chat/")) { location.assign(result.redirect); return; }
          if (form.dataset.deckAction === "like") { location.assign(result.redirect); return; }
          index += 1; show();
          announce("Đã bỏ qua. Có thể hoàn tác lượt cuối chưa match.");
          const next = document.querySelector("[data-next-candidates]");
          if (next) { const url = new URL(next.href); url.searchParams.delete("cursor"); next.href = url; }
          cards[index]?.querySelector("button")?.focus({preventScroll: true});
        }
      } catch (error) { announce(error.message); }
      finally { busy = false; deck.setAttribute("aria-busy", "false"); controls.forEach(button => button.disabled = false); cards.forEach(card => card.style.transform = ""); }
    });
    cards.forEach(card => {
      let origin = null, distance = 0;
      card.addEventListener("pointerdown", event => {
        if (busy || event.target.closest("a,button,input,textarea,select,summary")) return;
        origin = {x: event.clientX, y: event.clientY}; distance = 0;
        card.setPointerCapture(event.pointerId);
      });
      card.addEventListener("pointermove", event => {
        if (!origin) return;
        distance = event.clientX - origin.x;
        if (Math.abs(distance) > Math.abs(event.clientY - origin.y)) card.style.transform = `translateX(${distance}px) rotate(${distance / 30}deg)`;
      });
      const finish = event => {
        if (!origin) return;
        const horizontal = Math.abs(distance) > Math.abs(event.clientY - origin.y);
        origin = null; card.style.transform = "";
        if (horizontal && Math.abs(distance) > 100) card.querySelector(`[data-deck-action="${distance > 0 ? "like" : "pass"}"]`).requestSubmit();
      };
      card.addEventListener("pointerup", finish);
      card.addEventListener("pointercancel", () => { origin = null; card.style.transform = ""; });
    });
  }
  document.querySelectorAll("[data-pin-surface]").forEach(surface => {
    const form = surface.closest("figure").querySelector("[data-pin-form]");
    surface.addEventListener("click", event => {
      if (!form || event.target.closest("a")) return;
      const rect = surface.getBoundingClientRect();
      form.elements.x.value = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)).toFixed(5);
      form.elements.y.value = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)).toFixed(5);
      announce("Đã chọn vị trí trên ảnh. Nhập câu hỏi rồi bấm Ghim."); form.elements.question.focus();
    });
  });
  document.querySelectorAll("[data-add-cost]").forEach(button => button.addEventListener("click", () => {
    const form = button.closest("form"), total = form.elements["costs-TOTAL_FORMS"];
    if (Number(total.value) >= 20) { announce("Mỗi căn có tối đa 20 khoản tiền."); return; }
    const markup = form.querySelector("[data-cost-empty]").innerHTML.replaceAll("__prefix__", total.value);
    form.querySelector("[data-cost-formset]").insertAdjacentHTML("beforeend", markup);
    total.value = String(Number(total.value) + 1);
  }));
  const account = document.body.dataset.account;
  const prefix = `roomora-draft:${account}:`;
  const storage = {
    get: name => { try { const draft = JSON.parse(localStorage.getItem(prefix + name)); return draft && Array.isArray(draft.values) ? draft : null; } catch { return null; } },
    set: (name, value) => { try { localStorage.setItem(prefix + name, JSON.stringify(value)); } catch { announce("Trình duyệt không cho lưu bản nháp trên máy. Hãy lưu trên server trước khi rời trang."); } },
    remove: name => { try { localStorage.removeItem(prefix + name); } catch {} }
  };
  const drafts = new Map();
  document.querySelectorAll("form[data-draft]").forEach(form => {
    const name = form.dataset.draft, label = form.querySelector(".save-status");
    let timer = null, busy = false, changed = false, blocked = false;
    const fields = () => [...form.elements].filter(input => input.name && !["csrfmiddlewaretoken", "mutation_key", "client_id"].includes(input.name) && !["file", "submit", "button"].includes(input.type));
    const snapshot = () => ({version: form.elements.namedItem("expected_version")?.value ?? null,
      client_id: form.hasAttribute("data-chat-send") ? form.elements.client_id.value : undefined,
      last_attempt_body: form.dataset.lastAttemptBody,
      values: fields().map(input => ({name: input.name, value: input.value, checked: input.checked, type: input.type}))});
    const persist = () => { storage.set(name, snapshot()); if (label) label.textContent = "Bản nháp đang được giữ trên máy."; };
    drafts.set(form, {remove: () => storage.remove(name), canSubmit: () => !blocked, persist});
    const pending = storage.get(name);
    if (pending) {
      blocked = true;
      const banner = document.createElement("div"); banner.className = "draft-banner";
      const copy = document.createElement("p"); copy.textContent = "Có bản nháp chưa lưu từ lần trước. Bạn có thể khôi phục để tiếp tục hoặc giữ nội dung hiện tại trên server.";
      const restore = document.createElement("button"); restore.type = "button"; restore.textContent = "Khôi phục bản nháp";
      const discard = document.createElement("button"); discard.type = "button"; discard.className = "secondary"; discard.textContent = "Bỏ bản nháp cũ";
      restore.addEventListener("click", () => {
        const server = snapshot(), stale = pending.version !== server.version;
        const serverFields = fields().map(input => ({...server.values.find(value => value.name === input.name), label: input.labels?.[0]?.textContent.trim() || input.name}));
        const total = form.elements["costs-TOTAL_FORMS"];
        const pendingTotal = pending.values.find(value => value.name === "costs-TOTAL_FORMS");
        const rowCount = Math.min(20, Number(pendingTotal?.value || total?.value || 0));
        if (total && Number.isInteger(rowCount)) {
          while (Number(total.value) < rowCount) {
            const markup = form.querySelector("[data-cost-empty]").innerHTML.replaceAll("__prefix__", total.value);
            form.querySelector("[data-cost-formset]").insertAdjacentHTML("beforeend", markup);
            total.value = String(Number(total.value) + 1);
          }
        }
        pending.values.forEach(value => { const input = fields().find(input => input.name === value.name); if (input) { if (["checkbox", "radio"].includes(input.type)) input.checked = value.checked; else input.value = value.value; } });
        if (form.hasAttribute("data-chat-send") && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(pending.client_id || "")) {
          form.elements.client_id.value = pending.client_id;
          if (typeof pending.last_attempt_body === "string") form.dataset.lastAttemptBody = pending.last_attempt_body;
        }
        changed = true; blocked = stale;
        copy.textContent = stale ? "Bản nháp dựa trên nội dung cũ; chưa tự ghi đè bản mới. Hãy đọc nội dung hiện tại trước khi chủ động lưu thay thế." : "Đã khôi phục bản nháp. Bạn có thể sửa và lưu tiếp.";
        if (stale) {
          const comparison = document.createElement("details"), summary = document.createElement("summary");
          summary.textContent = "Nội dung server hiện tại để đối chiếu"; comparison.append(summary);
          serverFields.filter(value => value.type !== "hidden").forEach(value => {
            const row = document.createElement("p"); row.textContent = `${value.label}: ${value.type === "checkbox" ? (value.checked ? "Có" : "Không") : (value.value || "Chưa nhập")}`;
            comparison.append(row);
          });
          const allow = document.createElement("button"); allow.type = "button"; allow.textContent = "Tôi đã đối chiếu, lưu bản nháp thay thế";
          allow.addEventListener("click", () => { blocked = false; if (server.version != null) form.elements.expected_version.value = server.version; resetKey(form); persist(); banner.remove(); form.requestSubmit(); });
          banner.append(comparison, allow);
        } else { banner.remove(); persist(); }
        restore.disabled = true;
      });
      discard.addEventListener("click", () => { storage.remove(name); location.reload(); });
      banner.append(copy, restore, discard); form.before(banner);
    }
    async function autosave() {
      if (!form.hasAttribute("data-autosave") || busy || !changed || blocked || !form.checkValidity()) return;
      busy = true; changed = false;
      const sent = JSON.stringify(snapshot());
      if (label) label.textContent = "Đang lưu…";
      try {
        const result = await post(form);
        if (result.version != null) form.elements.expected_version.value = result.version;
        resetKey(form);
        const current = snapshot();
        const before = JSON.parse(sent); before.version = current.version;
        before.values.forEach(value => { if (value.name === "expected_version") value.value = current.version; });
        if (JSON.stringify(before) === JSON.stringify(current)) storage.remove(name); else { changed = true; storage.set(name, current); }
        if (label) label.textContent = "Đã lưu trên server.";
        if (form.action.includes("agreement-save")) {
          const note = document.createElement("a"); note.href = result.redirect; note.textContent = "Xem bản mới và các điều cần xác nhận"; note.className = "detail-link";
          label?.replaceChildren(document.createTextNode("Đã lưu bản mới. "), note);
        }
      } catch (error) { changed = true; if (error.status === 409 || error.status === 403) blocked = true; persist(); if (label) label.textContent = error.message.includes("Bản nháp") ? error.message : `${error.message} Bản nháp vẫn giữ trên máy.`; clearTimeout(timer); return; }
      finally { busy = false; }
      if (changed && !blocked && navigator.onLine) timer = setTimeout(autosave, 1800);
    }
    form.addEventListener("input", () => { changed = true; persist(); clearTimeout(timer); if (form.hasAttribute("data-autosave")) timer = setTimeout(autosave, 1000); });
    form.addEventListener("change", () => { changed = true; persist(); });
    form.addEventListener("submit", async event => {
      if (blocked) { event.preventDefault(); announce("Có bản nháp hoặc phiên bản cần đối chiếu trước khi lưu."); return; }
      if (form.hasAttribute("data-autosave")) { event.preventDefault(); changed = true; clearTimeout(timer); autosave(); return; }
      if (form.hasAttribute("data-chat-send")) return;
      event.preventDefault(); if (busy) return; busy = true;
      try { const result = await post(form, event.submitter); storage.remove(name); location.assign(result.redirect); }
      catch (error) { persist(); announce(error.message); if (error.status === 409) blocked = true; }
      finally { busy = false; }
    });
    window.addEventListener("online", () => { if (changed && !blocked) autosave(); });
  });
  document.querySelectorAll('form[action$="/logout/"]').forEach(form => form.addEventListener("submit", () => {
    try { Object.keys(localStorage).filter(name => name.startsWith(prefix)).forEach(name => localStorage.removeItem(name)); } catch {}
  }));
  const widget = document.querySelector("[data-connection-widget]");
  if (widget) {
    const panel = widget.querySelector("[data-chat-panel]");
    const toggle = widget.querySelector("[data-chat-toggle]");
    const close = widget.querySelector("[data-chat-close]");
    const heading = widget.querySelector("[data-chat-heading]");
    const state = widget.querySelector("[data-chat-state]");
    const log = widget.querySelector("[data-chat-widget-log]");
    const form = widget.querySelector("[data-chat-widget-form]");
    const error = widget.querySelector("[data-chat-widget-error]");
    let selected = null, lastId = 0, loadingVersion = null, sending = false, selectionVersion = 0;
    const showPanel = () => { panel.hidden = false; toggle.hidden = true; toggle.setAttribute("aria-expanded", "true"); };
    const hidePanel = () => { panel.hidden = true; toggle.hidden = false; toggle.setAttribute("aria-expanded", "false"); };
    const render = message => {
      if (log.querySelector(`[data-widget-message-id="${message.id}"]`)) return;
      const item = document.createElement("div");
      item.className = `connection-widget-message${message.mine ? " mine" : ""}`;
      item.dataset.widgetMessageId = message.id;
      const author = document.createElement("strong"); author.textContent = message.mine ? "Bạn" : message.sender;
      const body = document.createElement("p"); body.textContent = message.body;
      const time = document.createElement("time"); time.textContent = new Date(message.created_at).toLocaleString("vi-VN", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"});
      item.append(author, body, time); log.append(item);
    };
    async function refresh() {
      if (!selected || loadingVersion === selectionVersion) return;
      const version = selectionVersion;
      loadingVersion = version;
      try {
        let more = true;
        while (more) {
          const response = await fetch(`${selected.url}?after=${lastId}`, {headers: {Accept: "application/json"}, credentials: "same-origin"});
          const result = await response.json();
          if (!response.ok) { const failure = new Error(result.error || "Không tải được tin nhắn."); failure.status = response.status; throw failure; }
          if (version !== selectionVersion) return;
          state.textContent = result.connected ? "Đã kết nối" : "Đang chờ đồng ý kết nối";
          log.querySelector("[data-widget-empty]")?.remove();
          const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
          result.messages.forEach(message => { render(message); lastId = message.id; });
          more = result.messages.length === 50;
          if (atBottom) log.scrollTop = log.scrollHeight;
        }
        if (!log.children.length) { const empty = document.createElement("p"); empty.className = "muted"; empty.dataset.widgetEmpty = ""; empty.textContent = "Chưa có tin nhắn. Hãy gửi lời chào đầu tiên."; log.append(empty); }
        error.textContent = "";
      } catch (failure) {
        if (version === selectionVersion) { error.textContent = failure.message; if (failure.status === 403) { form.elements.body.disabled = true; form.querySelector("button[type=submit]").disabled = true; } }
      } finally { if (loadingVersion === version) loadingVersion = null; }
    }
    const openChat = button => {
      if (sending) return;
      selectionVersion += 1;
      selected = {id: button.dataset.chatPerson, url: button.dataset.chatUrl};
      lastId = 0; log.replaceChildren(); error.textContent = "";
      heading.textContent = button.dataset.chatName;
      state.textContent = "Đang tải cuộc trò chuyện…";
      form.elements.target.value = selected.id;
      form.elements.body.value = "";
      form.elements.body.disabled = false;
      form.querySelector("button[type=submit]").disabled = false;
      form.elements.client_id.value = key(); resetKey(form);
      showPanel(); refresh(); form.elements.body.focus();
    };
    document.querySelectorAll("[data-chat-person]").forEach(button => button.addEventListener("click", () => openChat(button)));
    toggle.addEventListener("click", () => panel.hidden ? showPanel() : hidePanel());
    close.addEventListener("click", hidePanel);
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (!selected || sending || !form.reportValidity()) return;
      sending = true;
      const button = form.querySelector("button[type=submit]"); button.disabled = true;
      const body = form.elements.body.value;
      try {
        await post(form);
        form.elements.body.value = "";
        form.elements.client_id.value = key(); resetKey(form);
        await refresh();
      } catch (failure) { error.textContent = failure.message; form.elements.body.value = body; }
      finally { sending = false; button.disabled = false; }
    });
    const initial = new URLSearchParams(location.search).get("chat");
    const initialButton = [...document.querySelectorAll("[data-chat-person]")].find(button => button.dataset.chatPerson === initial);
    if (initialButton) openChat(initialButton);
    setInterval(() => { if (!panel.hidden && selected) refresh(); }, 4000);
  }
  const chatLog = document.querySelector("[data-chat-log]");
  if (chatLog) {
    const send = document.querySelector("[data-chat-send]"); let polling = false;
    const renderMessage = (message, prepend = false) => {
      if (chatLog.querySelector(`[data-message-id="${message.id}"]`)) return;
      chatLog.querySelector("[data-chat-empty]")?.remove();
      const div = document.createElement("div"); div.className = `chat-message${message.mine ? " mine" : ""}`; div.dataset.messageId = message.id; div.id = `message-${message.id}`;
      const sender = document.createElement("strong"); sender.textContent = message.sender;
      const body = document.createElement("p"); body.textContent = message.body;
      const time = document.createElement("time"); time.textContent = new Date(message.created_at).toLocaleString("vi-VN");
      const details = document.createElement("details"), summary = document.createElement("summary"); summary.textContent = "Ghim điều cần thống nhất";
      const pinForm = document.createElement("form"); pinForm.method = "post"; pinForm.action = "/together/action/fact-pin/";
      const hidden = (name, value) => { const input = document.createElement("input"); input.type = "hidden"; input.name = name; input.value = value; pinForm.append(input); };
      hidden("csrfmiddlewaretoken", send.elements.csrfmiddlewaretoken.value); hidden("mutation_key", key()); hidden("conversation", send.elements.conversation.value); hidden("source", message.id);
      const label = document.createElement("label"); label.textContent = "Thông tin hoặc câu hỏi"; const input = document.createElement("input"); input.name = "body"; input.maxLength = 1000; input.required = true; input.value = message.body.slice(0, 1000); label.append(input);
      const button = document.createElement("button"); button.textContent = "Ghim"; pinForm.append(label, button); details.append(summary, pinForm);
      div.append(sender, body, time, details); prepend ? chatLog.prepend(div) : chatLog.append(div);
    };
    async function poll() {
      if (polling || document.hidden) return;
      polling = true;
      try {
        let after = Math.max(0, ...[...chatLog.querySelectorAll("[data-message-id]")].map(row => Number(row.dataset.messageId)));
        let more = true;
        while (more) {
          const response = await fetch(`${chatLog.dataset.url}?after=${after}`, {headers: {Accept: "application/json"}});
          const result = await response.json(); if (!response.ok) { const error = new Error(result.error); error.status = response.status; throw error; }
          const atBottom = chatLog.scrollHeight - chatLog.scrollTop - chatLog.clientHeight < 70;
          result.messages.forEach(message => renderMessage(message));
          more = result.messages.length === 50; after = result.messages.at(-1)?.id ?? after;
          if (atBottom) chatLog.scrollTop = chatLog.scrollHeight;
        }
      } catch (error) { announce(error.message || "Chưa tải được tin mới. Bạn có thể thử lại."); if (error.status === 403) { clearInterval(interval); send.querySelector("button").disabled = true; } }
      finally { polling = false; }
    }
    const interval = setInterval(poll, 4000);
    const sourceMessage = location.hash.startsWith("#message-") ? document.getElementById(location.hash.slice(1)) : null;
    if (sourceMessage && chatLog.contains(sourceMessage)) sourceMessage.scrollIntoView({block: "nearest"});
    else chatLog.scrollTop = chatLog.scrollHeight;
    send.querySelector("[data-opener]")?.addEventListener("click", event => { send.elements.body.value = event.target.dataset.opener; send.elements.body.dispatchEvent(new Event("input", {bubbles: true})); send.elements.body.focus(); });
    let sending = false;
    send.addEventListener("submit", async event => {
      event.preventDefault(); if (!drafts.get(send)?.canSubmit() || !send.reportValidity() || sending) return; sending = true;
      const sentBody = send.elements.body.value;
      if (send.dataset.lastAttemptBody != null && send.dataset.lastAttemptBody !== sentBody.trim()) { send.elements.client_id.value = key(); resetKey(send); }
      send.dataset.lastAttemptBody = sentBody.trim(); drafts.get(send)?.persist();
      try {
        await post(send, event.submitter);
        resetKey(send); send.elements.client_id.value = key(); delete send.dataset.lastAttemptBody;
        if (send.elements.body.value === sentBody) { send.elements.body.value = ""; drafts.get(send)?.remove(); }
        else drafts.get(send)?.persist();
        await poll();
      }
      catch (error) { announce(error.message); }
      finally { sending = false; }
    });
    document.querySelector("[data-older-messages]")?.addEventListener("click", async event => {
      const button = event.target; button.disabled = true;
      try { const response = await fetch(`${chatLog.dataset.url}?before=${button.dataset.olderMessages}`, {headers: {Accept: "application/json"}}); const result = await response.json(); if (!response.ok) throw new Error(result.error); [...result.messages].reverse().forEach(message => renderMessage(message, true)); if (result.next_before) button.dataset.olderMessages = result.next_before; else button.hidden = true; }
      catch (error) { announce(error.message); }
      finally { button.disabled = false; }
    });
  }
})();
