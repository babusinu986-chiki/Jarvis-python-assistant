const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function makeElement() {
  return {
    checked: true,
    disabled: false,
    value: "",
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {},
    append() {},
    focus() {},
    setAttribute() {},
  };
}

function response(data) {
  return { ok: true, json: async () => data };
}

test("dashboard sleep keeps the desktop microphone in wake-only standby", async () => {
  const elements = new Map();
  const spoken = [];
  const calls = [];
  const voice = { enabled: false, paused: false, standby: false, state: "off" };
  const events = [];

  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, makeElement());
      return elements.get(selector);
    },
    querySelectorAll: () => [],
    createElement: makeElement,
  };
  const window = {
    setTimeout: () => 1,
    clearTimeout() {},
    setInterval: () => 1,
    clearInterval() {},
    addEventListener() {},
    speechSynthesis: {
      cancel() {},
      speak(utterance) {
        spoken.push(utterance.text);
        utterance.onstart?.();
        utterance.onend?.();
      },
    },
  };
  async function fetch(url) {
    calls.push(url);
    if (url === "/api/health") {
      return response({ ai_available: false, default_city: "Cuttack", desktop_voice_available: true });
    }
    if (url === "/api/reminders") return response({ reminders: [] });
    if (url === "/api/command") {
      return response({ action: "sleep_mode", message: "Going to sleep.", follow_up: null });
    }
    if (url === "/api/voice/start") {
      Object.assign(voice, { enabled: true, paused: false, standby: false, state: "listening" });
      return response({ ...voice, latest_event_id: 0 });
    }
    if (url === "/api/voice/pause") {
      Object.assign(voice, { paused: true, state: "paused" });
      return response(voice);
    }
    if (url === "/api/voice/standby") {
      Object.assign(voice, { paused: false, standby: true, state: "standby" });
      return response(voice);
    }
    if (url === "/api/voice/resume") {
      Object.assign(voice, { paused: false, standby: false, state: "listening" });
      return response(voice);
    }
    if (url === "/api/voice/stop") {
      Object.assign(voice, { enabled: false, paused: false, standby: false, state: "off" });
      return response(voice);
    }
    if (url.startsWith("/api/voice/events")) {
      const after = Number(new URL(`http://localhost${url}`).searchParams.get("after"));
      return response({ ...voice, events: events.filter((event) => event.id > after) });
    }
    throw new Error(`Unexpected request: ${url}`);
  }

  const context = vm.createContext({
    document, window, fetch,
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
  });
  const script = fs.readFileSync(path.join(__dirname, "../static/js/dashboard.js"), "utf8");
  vm.runInContext(script, context);
  await new Promise(setImmediate);

  await vm.runInContext("enableVoiceMode()", context);
  await vm.runInContext("sendCommand('sleep')", context);
  assert.equal(vm.runInContext("voiceStandby", context), true);
  assert.equal(voice.standby, true);
  assert.equal(voice.enabled, true);
  assert.equal(spoken.at(-1), "Goodbye. Say Hey Jarvis to wake me.");
  assert.equal(calls.includes("/api/voice/stop"), false);

  Object.assign(voice, { paused: true, standby: false, state: "paused" });
  events.push({ id: 1, type: "wake" });
  await vm.runInContext("pollDesktopVoice()", context);
  assert.equal(vm.runInContext("voiceStandby", context), false);
  assert.equal(spoken.at(-1), "Yes boss, I'm listening.");
  assert.equal(voice.paused, false);

  await vm.runInContext("sendCommand('सो जाओ')", context);
  assert.equal(vm.runInContext("voiceStandby", context), true);
  assert.equal(voice.standby, true);

  Object.assign(voice, { paused: true, standby: false, state: "paused" });
  events.push({ id: 2, type: "wake" });
  await vm.runInContext("pollDesktopVoice()", context);
  assert.equal(vm.runInContext("voiceStandby", context), false);

  await vm.runInContext("sendCommand('stop listening')", context);
  assert.equal(vm.runInContext("voiceModeEnabled", context), false);
  assert.equal(voice.enabled, false);
  assert.equal(calls.includes("/api/voice/stop"), true);
});
