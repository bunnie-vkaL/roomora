/**
 * Room Pins Module: handles interactive image pin placement on photos.
 */
import { announce } from "../api.js?v=4";

export function initRoomPins() {
  document.querySelectorAll("[data-pin-surface]").forEach(surface => {
    if (surface.dataset.initialized) return;
    surface.dataset.initialized = "true";

    const form = surface.closest("figure")?.querySelector("[data-pin-form]");
    surface.addEventListener("click", event => {
      if (!form || event.target.closest("a")) return;
      const rect = surface.getBoundingClientRect();
      const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)).toFixed(5);
      const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)).toFixed(5);

      form.elements.x.value = x;
      form.elements.y.value = y;
      announce("Đã chọn vị trí trên ảnh. Nhập câu hỏi rồi bấm Ghim.");
      form.elements.question.focus();
    });
  });
}
