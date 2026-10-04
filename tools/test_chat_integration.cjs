const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function integration(fetch) {
  let config, stopped = false;
  const button = {disabled: false}, status = {textContent: ""};
  const chat = {dataset: {url: "/together/chat/1/messages/"}, scrollHeight: 100, scrollTop: 0, clientHeight: 100,
    querySelectorAll: () => [], querySelector: () => ({})};
  const send = {querySelector: selector => selector === "button" ? button : null, addEventListener() {}};
  const document = {body: {dataset: {account: "fixture"}}, hidden: false,
    querySelector: selector => ({"#journey-status": status, "[data-chat-log]": chat, "[data-chat-send]": send})[selector] || null,
    querySelectorAll: () => [], addEventListener() {}};
  const navigator = {onLine: true};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/journey.js"), "utf8"), {
    document, window: {addEventListener() {}}, location: {hash: ""}, navigator, fetch,
    createRoomoraPolling: options => { config = options; return {resume() {}, stop() {stopped = true;}}; }
  });
  return {config, button, status, document, navigator, stopped: () => stopped};
}

test("catch-up cycle fetches at most three pages of fifty messages", async () => {
  let calls = 0;
  const state = integration(async url => {
    const after = Number(new URL(url, "https://fixture.invalid").searchParams.get("after"));
    calls++;
    return {ok: true, headers: {get: () => "application/json"}, json: async () => ({messages: Array.from({length: 50}, (_, i) => ({id: after + i + 1}))})};
  });
  const result = await state.config.task(new AbortController().signal);
  assert.equal(calls, 3); assert.equal(result.changed, true); assert.equal(result.more, true);
});

test("expired login redirect stops polling and disables send without parsing HTML as messages", async () => {
  const state = integration(async () => ({ok: true, status: 200, redirected: true, headers: {get: () => "text/html"}}));
  await assert.rejects(state.config.task(new AbortController().signal), error => {
    assert.equal(error.status, 401); state.config.onError(error); return true;
  });
  assert.equal(state.stopped(), true); assert.equal(state.button.disabled, true);
  assert.match(state.status.textContent, /Đăng nhập lại/);
});

test("revoked consent response stops polling and disables send", async () => {
  const state = integration(async () => ({ok: false, status: 403, headers: {get: () => "application/json"}, json: async () => ({error: "Không còn quyền chat."})}));
  await assert.rejects(state.config.task(new AbortController().signal), error => {
    assert.equal(error.status, 403); state.config.onError(error); return true;
  });
  assert.equal(state.stopped(), true); assert.equal(state.button.disabled, true);
});

test("hidden or offline pages are ineligible for polling", () => {
  const state = integration(async () => { throw new Error("must not fetch in fixture setup"); });
  assert.equal(state.config.canRun(), true);
  state.document.hidden = true;
  assert.equal(state.config.canRun(), false);
  state.document.hidden = false;
  state.navigator.onLine = false;
  assert.equal(state.config.canRun(), false);
});
