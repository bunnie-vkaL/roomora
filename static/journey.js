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
