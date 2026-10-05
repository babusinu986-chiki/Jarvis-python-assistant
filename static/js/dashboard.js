const elements = {
  commandForm: document.querySelector("#commandForm"),
  commandInput: document.querySelector("#commandInput"),
  sendButton: document.querySelector("#sendButton"),
  micButton: document.querySelector("#micButton"),
  conversation: document.querySelector("#conversation"),
  statusText: document.querySelector("#statusText"),
  statusDot: document.querySelector("#statusDot"),
  voiceSupport: document.querySelector("#voiceSupport"),
  voiceStatus: document.querySelector("#voiceStatus"),
  speakReplies: document.querySelector("#speakReplies"),
  liveTime: document.querySelector("#liveTime"),
  liveDate: document.querySelector("#liveDate"),
  connectionBadge: document.querySelector("#connectionBadge"),
  geminiStatus: document.querySelector("#geminiStatus"),
  defaultCity: document.querySelector("#defaultCity"),
  startDayHero: document.querySelector("#startDayHero"),
  reminderForm: document.querySelector("#reminderForm"),
  reminderInput: document.querySelector("#reminderInput"),
  reminderList: document.querySelector("#reminderList"),
  reminderCount: document.querySelector("#reminderCount"),
  toast: document.querySelector("#toast"),
};

let isBusy = false;
let toastTimer;
let recognition;
let recognitionActive = false;
let recognitionStarting = false;
let voiceModeEnabled = false;
let commandCaptured = false;
let voiceTranscript = "";
let voiceCommitTimer;
let isSpeaking = false;
let voiceRestartTimer;
let desktopVoiceAvailable = false;
let desktopVoicePollTimer;
let desktopVoiceEventCursor = 0;
const completedFollowUps = new Set();

function setStatus(label, state = "ready") {
  elements.statusText.textContent = label;
  elements.statusDot.className = `status-dot ${state}`;
}

function setBusy(busy) {
  isBusy = busy;
  elements.sendButton.disabled = busy;
  elements.commandInput.disabled = busy;
  elements.startDayHero.disabled = busy;
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("visible");
  }, 3200);
}

function addMessage(role, message) {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "assistant" ? "J" : "Y";

  const body = document.createElement("div");
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "assistant" ? "Jarvis" : "You";
  const text = document.createElement("p");
  text.textContent = message;

  body.append(label, text);
  article.append(avatar, body);
  elements.conversation.append(article);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function speak(text) {
  return new Promise((resolve) => {
    if (!elements.speakReplies.checked || !("speechSynthesis" in window)) {
      resolve();
      return;
    }

    window.speechSynthesis.cancel();
    isSpeaking = true;
    setStatus("Speaking", "thinking");

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-IN";
    utterance.rate = 1.02;

    let finished = false;
    let started = false;
    let stoppedChecks = 0;
    const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
    const safetyTimeout = window.setTimeout(
      () => {
        window.speechSynthesis.cancel();
        finish();
      },
      Math.min(90000, Math.max(3500, 2000 + wordCount * 650)),
    );
    const completionCheck = window.setInterval(() => {
      if (window.speechSynthesis.speaking) started = true;
      if (!started || window.speechSynthesis.speaking || window.speechSynthesis.pending) {
        stoppedChecks = 0;
        return;
      }
      // Some browsers do not fire onend after a short reply. Confirm that
      // playback has stopped before letting the microphone listen again.
      stoppedChecks += 1;
      if (stoppedChecks >= 2) finish();
    }, 250);

    function finish() {
      if (finished) return;
      finished = true;
      window.clearTimeout(safetyTimeout);
      window.clearInterval(completionCheck);
      isSpeaking = false;
      resolve();
    }

    utterance.onstart = () => { started = true; };
    utterance.onend = finish;
    utterance.onerror = finish;
    window.speechSynthesis.speak(utterance);
  });
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function completeDeferredAction(followUp) {
  if (
    !followUp ||
    followUp.action !== "complete_start_my_day" ||
    !followUp.token ||
    completedFollowUps.has(followUp.token)
  ) {
    return;
  }

  completedFollowUps.add(followUp.token);
  setStatus("Preparing workspace", "thinking");
  // A short natural pause keeps the first browser tab or music from starting
  // on the exact final syllable of the spoken briefing.
  await wait(900);

  const response = await fetch("/api/start-day/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: followUp.token }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Could not finish the morning setup.");
  }

  addMessage("assistant", data.message);
  showToast("Morning workspace is ready.");
}

async function sendCommand(rawCommand) {
  const command = rawCommand.trim();
  if (!command || isBusy) return;

  await pauseVoiceInput();
  addMessage("user", command);
  elements.commandInput.value = "";
  setBusy(true);
  setStatus(command.toLowerCase().includes("start my day") ? "Running routine" : "Thinking", "thinking");

  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Command failed.");

    addMessage("assistant", data.message);
    await speak(data.message);
    await completeDeferredAction(data.follow_up);
    if (data.action === "sleep_mode") {
      disableVoiceMode();
      showToast("Voice mode is off. Click the microphone to listen again.");
      setStatus("Voice mode off", "ready");
    }
    if (["add_reminder", "list_reminders", "start_my_day"].includes(data.action)) {
      await loadReminders();
    }
    if (data.action !== "sleep_mode") setStatus("Ready", "ready");
  } catch (error) {
    addMessage("assistant", error.message || "Jarvis is unavailable.");
    setStatus("Needs attention", "error");
  } finally {
    setBusy(false);
    if (voiceModeEnabled) {
      if (desktopVoiceAvailable) {
        await resumeDesktopVoice();
        scheduleDesktopVoicePoll();
      } else {
        scheduleVoiceRestart();
      }
    } else {
      elements.commandInput.focus();
    }
  }
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("Dashboard unavailable");
    const data = await response.json();
    elements.connectionBadge.textContent = "Online";
    elements.geminiStatus.textContent = data.ai_available ? "Connected" : "Local only";
    elements.defaultCity.textContent = data.default_city;
    desktopVoiceAvailable = Boolean(data.desktop_voice_available);
    elements.micButton.disabled = !desktopVoiceAvailable && !recognition;
    updateVoiceModeUi();
  } catch {
    elements.connectionBadge.textContent = "Offline";
    elements.connectionBadge.style.color = "var(--danger)";
  }
}

async function loadReminders() {
  try {
    const response = await fetch("/api/reminders");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load reminders.");
    renderReminders(data.reminders);
  } catch (error) {
    showToast(error.message);
  }
}

function renderReminders(reminders) {
  elements.reminderList.textContent = "";
  elements.reminderCount.textContent = String(reminders.length);
  if (!reminders.length) {
    const empty = document.createElement("li");
    empty.className = "empty-state";
    empty.textContent = "No reminders saved yet.";
    elements.reminderList.append(empty);
    return;
  }

  reminders.forEach((reminder, index) => {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent = reminder;
    const remove = document.createElement("button");
    remove.className = "delete-reminder";
    remove.type = "button";
    remove.textContent = "×";
    remove.title = `Remove ${reminder}`;
    remove.setAttribute("aria-label", `Remove reminder: ${reminder}`);
    remove.addEventListener("click", () => removeReminder(index, reminder));
    item.append(text, remove);
    elements.reminderList.append(item);
  });
}

async function addReminder(text) {
  const response = await fetch("/api/reminders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not save reminder.");
  showToast(data.message);
  await loadReminders();
}

async function removeReminder(index, reminder) {
  if (!window.confirm(`Remove this reminder?\n\n${reminder}`)) return;
  try {
    const response = await fetch(`/api/reminders/${index}`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not remove reminder.");
    showToast(data.message);
    await loadReminders();
  } catch (error) {
    showToast(error.message);
  }
}

function updateClock() {
  const now = new Date();
  elements.liveTime.textContent = now.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  elements.liveDate.textContent = now.toLocaleDateString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

function updateVoiceModeUi() {
  elements.micButton.classList.toggle("voice-enabled", voiceModeEnabled);
  elements.micButton.setAttribute("aria-pressed", String(voiceModeEnabled));

  if (voiceModeEnabled) {
    elements.micButton.setAttribute("aria-label", "Stop continuous voice input");
    elements.micButton.title = "Stop continuous voice input";
    elements.voiceStatus.textContent = "ON";
    elements.voiceSupport.textContent = isBusy || isSpeaking
      ? "Voice mode is on. Listening resumes after Jarvis replies."
      : "Voice mode is ON. Say a command at any time.";
  } else {
    elements.micButton.setAttribute("aria-label", "Start continuous voice input");
    elements.micButton.title = "Start continuous voice input";
    elements.voiceStatus.textContent = "Off";
    elements.voiceSupport.textContent = desktopVoiceAvailable
      ? "Click once to start the same desktop voice engine used by the terminal."
      : "Click the microphone once for always-on listening.";
  }
}

async function enableVoiceMode() {
  if (voiceModeEnabled) return;

  elements.micButton.disabled = true;
  setStatus("Starting microphone", "thinking");

  if (desktopVoiceAvailable) {
    try {
      const response = await fetch("/api/voice/start", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Desktop voice could not start.");
      desktopVoiceEventCursor = Number(data.latest_event_id || 0);
      voiceModeEnabled = true;
      elements.micButton.disabled = false;
      updateVoiceModeUi();
      setStatus(data.state === "calibrating" ? "Calibrating" : "Listening", "listening");
      scheduleDesktopVoicePoll(150);
      return;
    } catch (error) {
      elements.micButton.disabled = false;
      showToast(error.message || "Desktop microphone could not start.");
      setStatus("Microphone error", "error");
      return;
    }
  }

  if (!recognition) {
    elements.micButton.disabled = false;
    showToast("Voice recognition is unavailable in this browser.");
    setStatus("Voice unavailable", "error");
    return;
  }

  try {
    if (navigator.mediaDevices?.getUserMedia) {
      const permissionStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
      // SpeechRecognition manages its own microphone capture. Release this
      // permission-check stream immediately so two capture sessions do not
      // compete for the same Windows microphone.
      permissionStream.getTracks().forEach((track) => track.stop());
    }
  } catch {
    showToast("Allow microphone access to use continuous voice mode.");
    setStatus("Microphone blocked", "error");
    elements.micButton.disabled = false;
    return;
  }

  voiceModeEnabled = true;
  elements.micButton.disabled = false;
  updateVoiceModeUi();
  startVoiceRecognition();
}

function disableVoiceMode() {
  voiceModeEnabled = false;
  window.clearTimeout(voiceRestartTimer);
  window.clearTimeout(voiceCommitTimer);
  window.clearTimeout(desktopVoicePollTimer);
  voiceTranscript = "";
  if (desktopVoiceAvailable) {
    void fetch("/api/voice/stop", { method: "POST" });
  } else {
    pauseVoiceRecognition();
  }
  elements.micButton.classList.remove("recording");
  updateVoiceModeUi();
  if (!isBusy) setStatus("Ready", "ready");
}

async function pauseVoiceInput() {
  if (desktopVoiceAvailable && voiceModeEnabled) {
    window.clearTimeout(desktopVoicePollTimer);
    try {
      await fetch("/api/voice/pause", { method: "POST" });
    } catch {
      // Command processing can continue; polling will report engine state.
    }
    return;
  }
  pauseVoiceRecognition();
}

async function resumeDesktopVoice() {
  if (!desktopVoiceAvailable || !voiceModeEnabled) return;
  try {
    const response = await fetch("/api/voice/resume", { method: "POST" });
    if (!response.ok) throw new Error("Could not resume voice mode.");
    setStatus("Listening", "listening");
  } catch (error) {
    showToast(error.message || "Could not resume voice mode.");
    setStatus("Voice needs attention", "error");
  }
}

function scheduleDesktopVoicePoll(delay = 500) {
  window.clearTimeout(desktopVoicePollTimer);
  if (!desktopVoiceAvailable || !voiceModeEnabled) return;
  desktopVoicePollTimer = window.setTimeout(pollDesktopVoice, delay);
}

async function pollDesktopVoice() {
  if (!desktopVoiceAvailable || !voiceModeEnabled || isBusy) return;

  try {
    const response = await fetch(
      `/api/voice/events?after=${desktopVoiceEventCursor}`,
      { cache: "no-store" },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Voice status is unavailable.");

    if (!data.enabled && voiceModeEnabled) {
      const restartResponse = await fetch("/api/voice/start", { method: "POST" });
      const restarted = await restartResponse.json();
      if (!restartResponse.ok) {
        throw new Error(restarted.error || "Desktop voice could not restart.");
      }
      desktopVoiceEventCursor = Number(restarted.latest_event_id || 0);
      setStatus(
        restarted.state === "calibrating" ? "Calibrating" : "Listening",
        "listening",
      );
      return;
    }

    if (data.state === "calibrating") {
      setStatus("Calibrating", "thinking");
    } else if (data.state === "transcribing") {
      setStatus("Converting speech to text", "thinking");
    } else if (data.state === "listening") {
      setStatus("Listening", "listening");
    }

    for (const event of data.events || []) {
      desktopVoiceEventCursor = Math.max(desktopVoiceEventCursor, Number(event.id || 0));
      if (event.type === "error") {
        showToast(event.message || "Speech recognition error.");
        continue;
      }
      if (event.type === "transcript" && event.transcript) {
        elements.commandInput.value = event.transcript;
        await sendCommand(event.transcript);
        return;
      }
    }
  } catch (error) {
    showToast(error.message || "Could not read the microphone.");
  } finally {
    if (voiceModeEnabled && !isBusy) scheduleDesktopVoicePoll();
  }
}

function pauseVoiceRecognition() {
  window.clearTimeout(voiceRestartTimer);
  window.clearTimeout(voiceCommitTimer);
  voiceTranscript = "";
  if (!recognition || (!recognitionActive && !recognitionStarting)) return;
  try {
    recognition.abort();
  } catch {
    // The browser may already be ending this recognition session.
  }
}

function commitVoiceCommand(rawTranscript) {
  const command = rawTranscript.trim();
  if (!command || commandCaptured || isBusy || isSpeaking) return;

  commandCaptured = true;
  window.clearTimeout(voiceCommitTimer);
  voiceTranscript = "";
  try {
    if (recognitionActive) recognition.stop();
  } catch {
    // The final speech result is already captured, so sending can continue.
  }
  void sendCommand(command);
}

function scheduleVoiceRestart(delay = 250) {
  window.clearTimeout(voiceRestartTimer);
  if (!voiceModeEnabled) return;
  voiceRestartTimer = window.setTimeout(startVoiceRecognition, delay);
}

function startVoiceRecognition() {
  if (
    !recognition ||
    desktopVoiceAvailable ||
    !voiceModeEnabled ||
    recognitionActive ||
    recognitionStarting ||
    isBusy ||
    isSpeaking
  ) {
    return;
  }

  try {
    recognitionStarting = true;
    commandCaptured = false;
    voiceTranscript = "";
    recognition.start();
  } catch (error) {
    recognitionStarting = false;
    if (error?.name === "InvalidStateError") {
      scheduleVoiceRestart(600);
      return;
    }
    voiceModeEnabled = false;
    updateVoiceModeUi();
    showToast("The microphone could not be started.");
  }
}

function configureVoiceRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    elements.voiceSupport.textContent = "Checking the desktop voice engine…";
    elements.voiceStatus.textContent = "Checking";
    return;
  }

  recognition = new Recognition();
  recognition.lang = "en-IN";
  recognition.interimResults = true;
  // One phrase per recognition session is more reliable in Chrome/Edge than
  // continuous mode. The session restarts automatically while voice mode is ON.
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    recognitionStarting = false;
    recognitionActive = true;
    commandCaptured = false;
    voiceTranscript = "";
    elements.micButton.classList.add("recording");
    elements.voiceStatus.textContent = "Listening";
    elements.voiceSupport.textContent = "Always listening is on. Speak a command.";
    setStatus("Listening", "listening");
  };
  recognition.onresult = (event) => {
    if (commandCaptured || isBusy || isSpeaking) return;

    let transcript = "";
    let hasFinalResult = false;
    for (let index = 0; index < event.results.length; index += 1) {
      const piece = event.results[index][0].transcript;
      transcript += `${piece} `;
      if (event.results[index].isFinal) hasFinalResult = true;
    }

    voiceTranscript = transcript.trim();
    elements.commandInput.value = voiceTranscript;
    if (!voiceTranscript) return;

    if (hasFinalResult) {
      commitVoiceCommand(voiceTranscript);
    } else {
      window.clearTimeout(voiceCommitTimer);
      // Some Chromium builds never mark the last transcript as final. A short
      // silence timeout still submits the visible transcript automatically.
      voiceCommitTimer = window.setTimeout(
        () => commitVoiceCommand(voiceTranscript),
        1400,
      );
    }
  };
  recognition.onspeechend = () => {
    if (!commandCaptured && voiceTranscript) {
      try {
        recognition.stop();
      } catch {
        // The browser is already finalizing the phrase.
      }
    }
  };
  recognition.onerror = (event) => {
    recognitionStarting = false;
    if (event.error === "aborted" || event.error === "no-speech") return;

    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      disableVoiceMode();
      showToast("Microphone permission is required for voice mode.");
      setStatus("Microphone blocked", "error");
      return;
    }

    showToast(`Voice input: ${event.error}`);
    if (!isBusy) setStatus("Reconnecting voice", "thinking");
  };
  recognition.onend = () => {
    const pendingTranscript = voiceTranscript;
    recognitionStarting = false;
    recognitionActive = false;
    elements.micButton.classList.remove("recording");
    updateVoiceModeUi();

    if (pendingTranscript && !commandCaptured && !isBusy && !isSpeaking) {
      commitVoiceCommand(pendingTranscript);
      return;
    }

    if (voiceModeEnabled) {
      if (!isBusy && !isSpeaking) setStatus("Listening", "listening");
      scheduleVoiceRestart();
    } else if (!isBusy) {
      setStatus("Ready", "ready");
    }
  };

  updateVoiceModeUi();
  elements.micButton.addEventListener("click", () => {
    if (voiceModeEnabled) {
      disableVoiceMode();
    } else {
      void enableVoiceMode();
    }
  });
}

elements.commandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendCommand(elements.commandInput.value);
});

elements.startDayHero.addEventListener("click", () => sendCommand("start my day"));

document.querySelectorAll("[data-command]").forEach((button) => {
  button.addEventListener("click", () => sendCommand(button.dataset.command || ""));
});

elements.reminderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = elements.reminderInput.value.trim();
  if (!text) return;
  try {
    await addReminder(text);
    elements.reminderInput.value = "";
  } catch (error) {
    showToast(error.message);
  }
});

window.addEventListener("pagehide", () => {
  const desktopWasEnabled = desktopVoiceAvailable && voiceModeEnabled;
  voiceModeEnabled = false;
  window.clearTimeout(voiceRestartTimer);
  window.clearTimeout(desktopVoicePollTimer);
  if (desktopWasEnabled) {
    navigator.sendBeacon("/api/voice/stop");
  }
  if (recognition && (recognitionActive || recognitionStarting)) {
    try {
      recognition.abort();
    } catch {
      // The page is closing, so no further recovery is needed.
    }
  }
});

updateClock();
window.setInterval(updateClock, 1000);
configureVoiceRecognition();
loadHealth();
loadReminders();
