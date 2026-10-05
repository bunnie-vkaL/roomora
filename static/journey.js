/**
 * Roomora Journey Orchestrator
 * Modular entry point coordinating native ES modules.
 */
import { announce, generateUUID } from "./js/api.js?v=4";
import { initRoutineTracks } from "./js/modules/routine.js";
import { initSwipeDeck } from "./js/modules/swipe_deck.js?v=4";
import { initRoomPins } from "./js/modules/room_pins.js";
import { initCostCalculator } from "./js/modules/cost_calculator.js";
import { initDrafts } from "./js/modules/drafts.js";
import { initChat, initConnectionWidget } from "./js/modules/chat.js";

async function post(form, submitter = null) {
  let response;
  try {
    response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form, submitter),
      headers: { Accept: "application/json" },
      credentials: "same-origin"
    });
  } catch {
    throw new Error("Chưa kết nối được với ứng dụng. Bản nháp vẫn giữ trên máy; hãy thử lưu lại khi có kết nối.");
  }
  if (!response.headers.get("Content-Type")?.includes("application/json")) {
    throw new Error("Phiên làm việc đã thay đổi. Đăng nhập lại; bản nháp vẫn được giữ trên máy.");
  }
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || result.detail || "Thao tác chưa hoàn tất.");
    error.status = response.status;
    throw error;
  }
  return result;
}

function initAll() {
  initDiscoveryView();
  initSavedView();
  initSavedCompare();
  initProfilePreviews();
  initAreaTagNavigation();
  document.querySelectorAll("[data-go-back]").forEach(button => {
    button.addEventListener("click", () => history.back());
  });

  initRoutineTracks();
  initSwipeDeck(post);
  initRoomPins();
  initCostCalculator();
  const drafts = initDrafts(post);
  initChat(post, drafts);
  initConnectionWidget(post);
}

function initSavedCompare() {
  const form = document.querySelector("[data-compare-form]");
  const content = document.querySelector("[data-compare-content]");
  if (!form || !content) return;

  const initialMarkup = content.innerHTML;
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const submit = form.querySelector("button[type='submit'], button:not([type])");
    if (submit) submit.disabled = true;
    try {
      const params = new URLSearchParams(new FormData(form));
      const response = await fetch(`${form.action}?${params}`, {
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "text/html" },
        credentials: "same-origin"
      });
      if (!response.ok) throw new Error("Không tải được phần so sánh.");
      content.innerHTML = await response.text();
      content.querySelector("[data-compare-reset]")?.addEventListener("click", () => {
        content.innerHTML = initialMarkup;
        initSavedCompare();
      }, { once: true });
    } catch {
      if (submit) submit.disabled = false;
    }
  });
}

function initSavedView() {
  const links = [...document.querySelectorAll("[data-saved-view]")];
  const panels = [...document.querySelectorAll("[data-saved-panel]")];
  if (!links.length || !panels.length) return;

  const storageKey = "roomora-saved-view";
  const availableViews = new Set(links.map(link => link.dataset.savedView));

  const setView = view => {
    if (!availableViews.has(view)) return;
    links.forEach(link => {
      const active = link.dataset.savedView === view;
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    panels.forEach(panel => {
      panel.hidden = panel.dataset.savedPanel !== view;
    });
    try {
      localStorage.setItem(storageKey, view);
    } catch {
      // Storage can be disabled; the current view still works in memory.
    }
  };

  let initialView = "list";
  try {
    const savedView = localStorage.getItem(storageKey);
    if (availableViews.has(savedView)) initialView = savedView;
  } catch {
    // Private browsing or disabled storage should not block view switching.
  }
  setView(initialView);

  links.forEach(link => {
    link.addEventListener("click", () => setView(link.dataset.savedView));
  });
}

function initAreaTagNavigation() {
  const updateAreaGuide = async url => {
    const response = await fetch(url, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    });
    if (!response.ok) throw new Error("Không tải được gợi ý theo khu vực.");

    const html = await response.text();
    const nextDocument = new DOMParser().parseFromString(html, "text/html");
    const nextAreaGuide = nextDocument.querySelector(".area-guide");
    const currentAreaGuide = document.querySelector(".area-guide");
    if (!nextAreaGuide || !currentAreaGuide) throw new Error("Không cập nhật được danh sách khu vực.");

    currentAreaGuide.replaceWith(nextAreaGuide);
    window.history.pushState({}, "", url);
    initAreaTagNavigation();
  };

  document.querySelectorAll("[data-discovery-area-link]").forEach(link => {
    if (link.dataset.areaNavigationInitialized) return;
    link.dataset.areaNavigationInitialized = "true";
    link.addEventListener("click", async event => {
      event.preventDefault();
      if (link.dataset.areaLoading === "true") return;
      link.dataset.areaLoading = "true";

      try {
        await updateAreaGuide(link.href);
      } catch (error) {
        announce(error.message);
      } finally {
        link.dataset.areaLoading = "false";
      }
    });
  });

  document.querySelectorAll("[data-area-guide-form]").forEach(form => {
    if (form.dataset.areaNavigationInitialized) return;
    form.dataset.areaNavigationInitialized = "true";
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (form.dataset.areaLoading === "true") return;
      form.dataset.areaLoading = "true";
      const url = new URL(form.action || window.location.href, window.location.origin);
      url.search = new URLSearchParams(new FormData(form)).toString();

      try {
        await updateAreaGuide(url.toString());
      } catch (error) {
        announce(error.message);
      } finally {
        form.dataset.areaLoading = "false";
      }
    });
  });
}

function initProfilePreviews() {
  const triggers = [
    ...document.querySelectorAll("[data-profile-preview]"),
    ...document.querySelectorAll("[data-compare-open]")
  ];
  if (!triggers.length) return;

  let activeModal = null;
  let activeTrigger = null;

  const close = () => {
    if (!activeModal) return;
    activeModal.hidden = true;
    document.body.classList.remove("profile-preview-open");
    activeTrigger?.focus({ preventScroll: true });
    activeModal = null;
    activeTrigger = null;
  };

  triggers.forEach(trigger => {
    trigger.addEventListener("click", () => {
      const modalId = trigger.dataset.profilePreview || trigger.dataset.compareOpen;
      const modal = document.getElementById(modalId);
      if (!modal) return;
      if (activeModal && activeModal !== modal) close();
      // Cards use transform for swipe/fade animations. Mount the preview at
      // body level so position: fixed is relative to the full viewport.
      if (modal.parentElement !== document.body) {
        document.body.appendChild(modal);
      }
      activeModal = modal;
      activeTrigger = trigger;
      modal.hidden = false;
      document.body.classList.add("profile-preview-open");
      modal.querySelector("[data-profile-preview-close]")?.focus({ preventScroll: true });
    });
  });

  document.querySelectorAll("[data-profile-preview-close]").forEach(button => {
    button.addEventListener("click", close);
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && activeModal) close();
  });
}

function initDiscoveryView() {
  const links = [...document.querySelectorAll("[data-discovery-view]")];
  const panels = [...document.querySelectorAll("[data-discovery-panel]")];
  if (!links.length || !panels.length) return;

  const storageKey = "roomora-discovery-view";
  const availableViews = new Set(links.map(link => link.dataset.discoveryView));

  const setView = view => {
    if (!availableViews.has(view)) return;
    links.forEach(link => {
      const active = link.dataset.discoveryView === view;
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    panels.forEach(panel => {
      panel.hidden = panel.dataset.discoveryPanel !== view;
    });
    try {
      localStorage.setItem(storageKey, view);
    } catch {
      // Storage can be disabled; the current view still works in memory.
    }
  };

  let initialView = "swipe";
  try {
    const savedView = localStorage.getItem(storageKey);
    if (availableViews.has(savedView)) initialView = savedView;
  } catch {
    // Private browsing or disabled storage should not block view switching.
  }
  setView(initialView);

  links.forEach(link => {
    link.addEventListener("click", event => {
      event.preventDefault();
      setView(link.dataset.discoveryView);
    });
  });
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
}
