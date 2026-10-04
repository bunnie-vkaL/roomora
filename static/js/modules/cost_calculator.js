/**
 * Cost calculator module: handles dynamic cost line additions and live budget warnings.
 */
import { announce } from "../api.js";

export function initCostCalculator() {
  document.querySelectorAll("[data-add-cost]").forEach(button => {
    if (button.dataset.initialized) return;
    button.dataset.initialized = "true";

    button.addEventListener("click", () => {
      const form = button.closest("form");
      const total = form.elements["costs-TOTAL_FORMS"];
      if (Number(total.value) >= 20) {
        announce("Mỗi căn có tối đa 20 khoản tiền.");
        return;
      }
      const markup = form.querySelector("[data-cost-empty]").innerHTML.replaceAll("__prefix__", total.value);
      form.querySelector("[data-cost-formset]").insertAdjacentHTML("beforeend", markup);
      total.value = String(Number(total.value) + 1);
    });
  });
}
