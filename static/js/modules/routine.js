/**
 * Routine track module: visualizes 24-hour sleep/wake cycles.
 */

export function initRoutineTracks() {
  document.querySelectorAll(".routine-track").forEach(track => {
    if (track.dataset.initialized) return;
    track.dataset.initialized = "true";

    const minute = value => {
      const [hour, min] = value.split(":").map(Number);
      return hour * 60 + min;
    };

    const start = minute(track.dataset.routineStart);
    const end = minute(track.dataset.routineEnd);

    const addSegment = (from, until) => {
      const span = document.createElement("span");
      span.className = "sleep-segment";
      span.style.left = `${(from / 1440) * 100}%`;
      span.style.width = `${((until - from) / 1440) * 100}%`;
      track.append(span);
    };

    if (end < start) {
      addSegment(start, 1440);
      addSegment(0, end);
    } else {
      addSegment(start, end);
    }
  });
}
