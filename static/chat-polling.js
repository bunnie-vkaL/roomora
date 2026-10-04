(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.createRoomoraPolling = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  return function createPolling({task, canRun, onError, schedule = setTimeout, cancel = clearTimeout}) {
    let timer = null, active = null, controller = null, stopped = false, again = false, delay = 4000;
    const clear = () => { if (timer !== null) cancel(timer); timer = null; };
    const plan = milliseconds => {
      clear();
      if (!stopped && canRun()) timer = schedule(() => { timer = null; refresh(); }, milliseconds);
    };
    function refresh() {
      clear();
      if (stopped || !canRun()) return Promise.resolve();
      if (active) { again = true; return active; }
      controller = new AbortController();
      const current = controller;
      const deadline = schedule(() => current.abort(), 12000);
      active = Promise.resolve().then(() => task(current.signal)).then(result => {
        if (current.signal.aborted) return;
        delay = result.changed ? 4000 : Math.min(30000, delay * 2);
        if (result.more) { delay = 4000; again = true; }
      }).catch(error => {
        if (!current.signal.aborted) onError(error);
        delay = Math.min(60000, delay * 2);
      }).finally(() => {
        cancel(deadline);
        active = null; controller = null;
        const next = again ? 1000 : delay;
        again = false;
        plan(next);
      });
      return active;
    }
    return {
      refresh,
      resume() { if (!stopped && canRun()) { delay = 4000; if (active) again = true; else plan(0); } },
      pause() { clear(); again = false; controller?.abort(); },
      stop() { stopped = true; clear(); again = false; controller?.abort(); }
    };
  };
});
