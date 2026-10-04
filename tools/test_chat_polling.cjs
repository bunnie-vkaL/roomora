const test = require("node:test");
const assert = require("node:assert/strict");
const createPolling = require("../static/chat-polling.js");

function fixture(task) {
  let eligible = true, counter = 0;
  const timers = new Map(), errors = [];
  const poller = createPolling({task, canRun: () => eligible, onError: error => errors.push(error),
    schedule: (callback, ms) => { const id = ++counter; timers.set(id, {callback, ms}); return id; },
    cancel: id => timers.delete(id)});
  return {poller, timers, errors, setEligible: value => eligible = value,
    nextDelay: () => [...timers.values()].map(value => value.ms)};
}

test("idle intervals grow to 30 seconds; incoming messages restore four seconds", async () => {
  let changed = false;
  const state = fixture(async () => ({changed, more: false}));
  for (const expected of [8000, 16000, 30000, 30000]) {
    await state.poller.refresh();
    assert.deepEqual(state.nextDelay(), [expected]);
  }
  changed = true;
  await state.poller.refresh();
  assert.deepEqual(state.nextDelay(), [4000]);
});

test("parallel refreshes share one request; catch-up schedules a bounded next cycle", async () => {
  let resolve, calls = 0;
  const state = fixture(() => { calls++; return new Promise(done => resolve = done); });
  const first = state.poller.refresh(), second = state.poller.refresh();
  assert.equal(first, second);
  await Promise.resolve();
  assert.equal(calls, 1);
  resolve({changed: true, more: true});
  await first;
  assert.deepEqual(state.nextDelay(), [1000]);
});

test("hidden or offline state aborts in-flight work and makes no new request until resume", async () => {
  let calls = 0, aborted = false;
  const state = fixture(signal => {
    calls++;
    return new Promise((resolve, reject) => signal.addEventListener("abort", () => {
      aborted = true; reject(new Error("abort fixture"));
    }, {once: true}));
  });
  const pending = state.poller.refresh();
  await Promise.resolve();
  state.setEligible(false); state.poller.pause();
  await pending;
  await state.poller.refresh();
  assert.equal(aborted, true); assert.equal(calls, 1);
  assert.equal(state.errors.length, 0); assert.equal(state.timers.size, 0);
  state.setEligible(true); state.poller.resume();
  assert.deepEqual(state.nextDelay(), [0]);
});

test("network failures back off to one minute without retrying in a tight loop", async () => {
  const state = fixture(async () => { throw new Error("network fixture"); });
  for (const expected of [8000, 16000, 32000, 60000, 60000]) {
    await state.poller.refresh();
    assert.deepEqual(state.nextDelay(), [expected]);
  }
  assert.equal(state.errors.length, 5);
});

test("twelve-second deadline aborts a hung request and releases the next poll", async () => {
  const state = fixture(signal => new Promise((resolve, reject) => signal.addEventListener("abort", () => reject(new Error("timeout fixture")), {once: true})));
  const pending = state.poller.refresh();
  await Promise.resolve();
  const [id, timeout] = [...state.timers].find(([, value]) => value.ms === 12000);
  state.timers.delete(id); timeout.callback();
  await pending;
  assert.deepEqual(state.nextDelay(), [8000]);
  assert.equal(state.errors.length, 0);
});

test("terminal stop cancels polling permanently even after resume and manual refresh", async () => {
  let calls = 0;
  const state = fixture(async () => { calls++; return {changed: false, more: false}; });
  await state.poller.refresh();
  state.poller.stop(); state.poller.resume();
  await state.poller.refresh();
  assert.equal(calls, 1); assert.equal(state.timers.size, 0);
});
