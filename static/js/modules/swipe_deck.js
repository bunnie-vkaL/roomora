/**
 * Swipe deck module: handles candidate card touch gestures, drag physics,
 * keyboard controls, and Like/Pass/Save actions.
 */
import { announce, generateUUID } from "../api.js?v=4";

export function initSwipeDeck(postFn) {
  const deck = document.querySelector("[data-swipe-deck]");
  if (!deck || deck.dataset.initialized) return;
  deck.dataset.initialized = "true";

  const cards = [...deck.querySelectorAll("[data-person-card]")];
  let index = 0;
  let busy = false;

  const show = () => {
    cards.forEach((card, i) => {
      const visible = i === index;
      card.hidden = !visible;
      card.classList.remove("card-fade-in");
      if (visible) {
        void card.offsetWidth;
        card.classList.add("card-fade-in");
      }
    });
    const emptyNotice = deck.querySelector("[data-deck-empty]");
    if (emptyNotice) emptyNotice.hidden = index < cards.length;
  };
  show();

  deck.addEventListener("submit", async event => {
    const form = event.target.closest("[data-deck-action]");
    if (!form) return;
    event.preventDefault();
    if (busy) return;
    busy = true;

    deck.setAttribute("aria-busy", "true");
    const controls = [...deck.querySelectorAll("button")];
    controls.forEach(b => b.disabled = true);
    const card = form.closest("[data-person-card]");
    const actionClass = form.dataset.deckAction === "like"
      ? "swipe-action-right"
      : form.dataset.deckAction === "pass"
        ? "swipe-action-left"
        : "";

    try {
      if (card && actionClass) {
        card.style.transform = "";
        card.classList.add(actionClass);
        await new Promise(resolve => setTimeout(resolve, 260));
      }
      const result = await postFn(form, event.submitter);
      const keyInput = form.elements.namedItem("mutation_key");
      if (keyInput) keyInput.value = generateUUID();

      if (form.dataset.deckAction === "save") {
        const saved = form.elements.saved;
        saved.value = saved.value === "1" ? "0" : "1";
        const button = form.querySelector("button");
        const isSaved = saved.value === "0";
        button.classList.toggle("is-saved", isSaved);
        button.setAttribute("aria-label", isSaved ? `Bỏ lưu ${form.dataset.candidateName}` : `Lưu ${form.dataset.candidateName} để xem sau`);
        button.setAttribute("aria-pressed", String(isSaved));
        button.title = isSaved ? "Bỏ lưu" : "Lưu xem sau";
        const icon = button.querySelector("i");
        if (icon) icon.classList.toggle("fa-solid", isSaved);
        if (icon) icon.classList.toggle("fa-regular", !isSaved);
        if (!icon) button.textContent = isSaved ? "Bỏ lưu" : "Lưu xem sau";
        announce(saved.value === "0" ? "Đã lưu riêng, chưa gửi lượt quan tâm." : "Đã bỏ lưu.");
      } else {
        if (form.dataset.deckAction === "like") {
          announce(result.redirect && result.redirect.includes("/chat/")
            ? "Hai bạn đã kết nối. Bạn có thể bắt đầu trò chuyện trong Hub."
            : "Đã gửi lời mời kết nối. Khi cả hai cùng đồng ý, chat sẽ mở.");
        } else if (form.dataset.deckAction === "pass") {
          announce("Đã bỏ qua. Có thể hoàn tác lượt cuối chưa match.");
        }
        index += 1;
        show();
        const next = document.querySelector("[data-next-candidates]");
        if (next) {
          const url = new URL(next.href, window.location.origin);
          url.searchParams.delete("cursor");
          next.href = url.toString();
        }
        cards[index]?.querySelector("button")?.focus({ preventScroll: true });
      }
    } catch (error) {
      announce(error.message);
    } finally {
      card?.classList.remove("swipe-action-right", "swipe-action-left");
      busy = false;
      deck.setAttribute("aria-busy", "false");
      controls.forEach(b => b.disabled = false);
      cards.forEach(card => card.style.transform = "");
    }
  });

  cards.forEach(card => {
    let origin = null;
    let distance = 0;

    card.addEventListener("pointerdown", event => {
      if (busy || event.target.closest("a,button,input,textarea,select,summary")) return;
      origin = { x: event.clientX, y: event.clientY };
      distance = 0;
      card.setPointerCapture(event.pointerId);
    });

    card.addEventListener("pointermove", event => {
      if (!origin) return;
      distance = event.clientX - origin.x;
      if (Math.abs(distance) > Math.abs(event.clientY - origin.y)) {
        card.style.transform = `translateX(${distance}px) rotate(${distance / 30}deg)`;
      }
    });

    const finish = () => {
      if (!origin) return;
      const horizontal = Math.abs(distance) > 50;
      origin = null;
      card.style.transform = "";
      if (horizontal && Math.abs(distance) > 100) {
        const actionType = distance > 0 ? "like" : "pass";
        card.querySelector(`[data-deck-action="${actionType}"]`)?.requestSubmit();
      }
    };

    card.addEventListener("pointerup", finish);
    card.addEventListener("pointercancel", () => {
      origin = null;
      card.style.transform = "";
    });
  });
}
