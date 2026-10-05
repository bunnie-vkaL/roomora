/**
 * Drafts module: manages local draft persistence, conflict resolution banners,
 * and debounced autosaving.
 */
import { announce, generateUUID } from "../api.js?v=5";

export function initDrafts(postFn) {
  const account = document.body.dataset.account;
  const prefix = `roomora-draft:${account}:`;

  const storage = {
    get: name => {
      try {
        const draft = JSON.parse(localStorage.getItem(prefix + name));
        return draft && Array.isArray(draft.values) ? draft : null;
      } catch {
        return null;
      }
    },
    set: (name, value) => {
      try {
        localStorage.setItem(prefix + name, JSON.stringify(value));
      } catch {
        announce("Trình duyệt không cho lưu bản nháp trên máy. Hãy lưu trên server trước khi rời trang.");
      }
    },
    remove: name => {
      try {
        localStorage.removeItem(prefix + name);
      } catch {}
    }
  };

  const drafts = new Map();

  document.querySelectorAll("form[data-draft]").forEach(form => {
    if (form.dataset.draftInitialized) return;
    form.dataset.draftInitialized = "true";

    const name = form.dataset.draft;
    const label = form.querySelector(".save-status");
    let timer = null;
    let busy = false;
    let changed = false;
    let blocked = false;

    const fields = () => [
      ...form.elements
    ].filter(
      input => input.name &&
        !["csrfmiddlewaretoken", "mutation_key", "client_id"].includes(input.name) &&
        !["file", "submit", "button"].includes(input.type)
    );

    const snapshot = () => ({
      version: form.elements.namedItem("expected_version")?.value ?? null,
      client_id: form.hasAttribute("data-chat-send") ? form.elements.client_id.value : undefined,
      last_attempt_body: form.dataset.lastAttemptBody,
      values: fields().map(input => ({
        name: input.name,
        value: input.value,
        checked: input.checked,
        type: input.type
      }))
    });

    const persist = () => {
      storage.set(name, snapshot());
      if (label) label.textContent = "Bản nháp đang được giữ trên máy.";
    };

    drafts.set(form, {
      remove: () => storage.remove(name),
      canSubmit: () => !blocked,
      persist
    });

    const pending = storage.get(name);
    if (pending) {
      blocked = true;
      const banner = document.createElement("div");
      banner.className = "draft-banner";
      const copy = document.createElement("p");
      copy.textContent = "Có bản nháp chưa lưu từ lần trước. Bạn có thể khôi phục để tiếp tục hoặc giữ nội dung hiện tại trên server.";
      const restore = document.createElement("button");
      restore.type = "button";
      restore.textContent = "Khôi phục bản nháp";
      const discard = document.createElement("button");
      discard.type = "button";
      discard.className = "secondary";
      discard.textContent = "Bỏ bản nháp cũ";

      restore.addEventListener("click", () => {
        const server = snapshot();
        const stale = pending.version !== server.version;
        const serverFields = fields().map(input => ({
          ...server.values.find(v => v.name === input.name),
          label: input.labels?.[0]?.textContent.trim() || input.name
        }));
        const total = form.elements["costs-TOTAL_FORMS"];
        const pendingTotal = pending.values.find(v => v.name === "costs-TOTAL_FORMS");
        const rowCount = Math.min(20, Number(pendingTotal?.value || total?.value || 0));
        if (total && Number.isInteger(rowCount)) {
          while (Number(total.value) < rowCount) {
            const markup = form.querySelector("[data-cost-empty]").innerHTML.replaceAll("__prefix__", total.value);
            form.querySelector("[data-cost-formset]").insertAdjacentHTML("beforeend", markup);
            total.value = String(Number(total.value) + 1);
          }
        }
        pending.values.forEach(val => {
          const input = fields().find(i => i.name === val.name);
          if (input) {
            if (["checkbox", "radio"].includes(input.type)) input.checked = val.checked;
            else input.value = val.value;
          }
        });
        if (form.hasAttribute("data-chat-send") && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(pending.client_id || "")) {
          form.elements.client_id.value = pending.client_id;
          if (typeof pending.last_attempt_body === "string") form.dataset.lastAttemptBody = pending.last_attempt_body;
        }
        changed = true;
        blocked = stale;
        copy.textContent = stale
          ? "Bản nháp dựa trên nội dung cũ; chưa tự ghi đè bản mới. Hãy đọc nội dung hiện tại trước khi chủ động lưu thay thế."
          : "Đã khôi phục bản nháp. Bạn có thể sửa và lưu tiếp.";
        if (stale) {
          const comparison = document.createElement("details");
          const summary = document.createElement("summary");
          summary.textContent = "Nội dung server hiện tại để đối chiếu";
          comparison.append(summary);
          serverFields.filter(val => val.type !== "hidden").forEach(val => {
            const row = document.createElement("p");
            row.textContent = `${val.label}: ${val.type === "checkbox" ? (val.checked ? "Có" : "Không") : (val.value || "Chưa nhập")}`;
            comparison.append(row);
          });
          const allow = document.createElement("button");
          allow.type = "button";
          allow.textContent = "Tôi đã đối chiếu, lưu bản nháp thay thế";
          allow.addEventListener("click", () => {
            blocked = false;
            if (server.version != null) form.elements.expected_version.value = server.version;
            const mutInput = form.elements.namedItem("mutation_key");
            if (mutInput) mutInput.value = generateUUID();
            persist();
            banner.remove();
            form.requestSubmit();
          });
          banner.append(comparison, allow);
        } else {
          banner.remove();
          persist();
        }
        restore.disabled = true;
      });

      discard.addEventListener("click", () => {
        storage.remove(name);
        location.reload();
      });

      banner.append(copy, restore, discard);
      form.before(banner);
    }

    async function autosave() {
      if (!form.hasAttribute("data-autosave") || busy || !changed || blocked || !form.checkValidity()) return;
      busy = true;
      changed = false;
      const sent = JSON.stringify(snapshot());
      if (label) label.textContent = "Đang lưu…";
      try {
        const result = await postFn(form);
        if (result.version != null) form.elements.expected_version.value = result.version;
        const mutInput = form.elements.namedItem("mutation_key");
        if (mutInput) mutInput.value = generateUUID();

        const current = snapshot();
        const before = JSON.parse(sent);
        before.version = current.version;
        before.values.forEach(v => {
          if (v.name === "expected_version") v.value = current.version;
        });
        if (JSON.stringify(before) === JSON.stringify(current)) {
          storage.remove(name);
        } else {
          changed = true;
          storage.set(name, current);
        }
        if (label) label.textContent = "Đã lưu trên server.";
        if (form.action.includes("agreement-save")) {
          const note = document.createElement("a");
          note.href = result.redirect;
          note.textContent = "Xem bản mới và các điều cần xác nhận";
          note.className = "detail-link";
          label?.replaceChildren(document.createTextNode("Đã lưu bản mới. "), note);
        }
      } catch (error) {
        changed = true;
        if (error.status === 409 || error.status === 403) blocked = true;
        persist();
        if (label) {
          label.textContent = error.message.includes("Bản nháp")
            ? error.message
            : `${error.message} Bản nháp vẫn giữ trên máy.`;
        }
        clearTimeout(timer);
        return;
      } finally {
        busy = false;
      }
      if (changed && !blocked && navigator.onLine) timer = setTimeout(autosave, 1800);
    }

    form.addEventListener("input", () => {
      changed = true;
      persist();
      clearTimeout(timer);
      if (form.hasAttribute("data-autosave")) timer = setTimeout(autosave, 1000);
    });

    form.addEventListener("change", () => {
      changed = true;
      persist();
    });

    form.addEventListener("submit", async event => {
      if (blocked) {
        event.preventDefault();
        announce("Có bản nháp hoặc phiên bản cần đối chiếu trước khi lưu.");
        return;
      }
      if (form.hasAttribute("data-autosave")) {
        event.preventDefault();
        changed = true;
        clearTimeout(timer);
        autosave();
        return;
      }
      if (form.hasAttribute("data-chat-send")) return;
      event.preventDefault();
      if (busy) return;
      busy = true;
      try {
        const result = await postFn(form, event.submitter);
        storage.remove(name);
        location.assign(result.redirect);
      } catch (error) {
        persist();
        announce(error.message);
        if (error.status === 409) blocked = true;
      } finally {
        busy = false;
      }
    });

    window.addEventListener("online", () => {
      if (changed && !blocked) autosave();
    });
  });

  document.querySelectorAll('form[action$="/logout/"]').forEach(form => {
    form.addEventListener("submit", () => {
      try {
        Object.keys(localStorage)
          .filter(n => n.startsWith(prefix))
          .forEach(n => localStorage.removeItem(n));
      } catch {}
    });
  });

  return drafts;
}
