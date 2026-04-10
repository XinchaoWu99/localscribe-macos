const state = {
  status: null,
  session: null,
  sessions: [],
  transcript: null,
  modelCatalog: null,
  postProcessCatalog: null,
  systemAudio: null,
  socket: null,
  liveCapture: null,
  mediaStream: null,
  captureStream: null,
  sequence: 1,
  mode: "Waiting",
  chunkMillisRequestToken: 0,
  chunkMillisPersistTimer: 0,
  modelActionPending: false,
  entryMode: "microphone",
  scenarioId: "meeting",
  starterCollapsed: false,
  draftSessionId: null,
  segmentDrafts: {},
  segmentSaveTimers: {},
  systemAudioUiMessage: "",
};

let _isRenderingTranscript = false;

const ALWAYS_ENABLE_CONTEXT_LINKING = true;
const ALWAYS_ENABLE_POST_PROCESSING = true;
const LOW_INPUT_WARNING = "Input level is very low. Check the selected microphone or audio source.";
const NO_SPEECH_WARNING = "No speech detected in the latest audio chunk.";
const LIVE_FALLBACK_WARNING = "Live speech fallback used because browser audio was below the default VAD gate.";
const INPUT_LEVEL_IDLE = "Waiting for audio";
const LIVE_BOOTSTRAP_CHUNK_MILLIS = 1200;
const CAPTURE_WORKLET_NAME = "localscribe-capture-processor";

let _captureWorkletModuleUrl = null;

const ENTRY_PRESETS = {
  microphone: {
    label: "Live microphone",
    summary: "Best for room conversations, calls, interviews, and meetings happening right now.",
    actionLabel: "Start Live Microphone",
    target: "live",
  },
  "mac-system-audio": {
    label: "Current Mac sound output",
    summary: "Best for anything already playing through this Mac, including meetings, videos, streams, and apps.",
    actionLabel: "Start Mac Output",
    target: "live",
  },
  "browser-audio": {
    label: "Browser tab or shared screen audio",
    summary: "Best for tab sharing or browser playback when the browser exposes an audio track.",
    actionLabel: "Start Browser Audio",
    target: "live",
  },
};

const SCENARIO_PRESETS = {
  meeting: {
    title: "Meeting capture",
    summary: "Preserve speaker turns, names, acronyms, decisions, blockers, and follow-up actions from a team meeting.",
    prompt:
      "Team meeting transcript. Preserve names, product names, acronyms, action items, decisions, and next steps. Use clear punctuation and speaker-consistent wording.",
    chunkMillis: 2600,
    diarize: true,
    contextLink: true,
    focusHint: "Decision tracking",
  },
  podcast: {
    title: "Podcast conversation",
    summary: "Favor smooth long-form host and guest dialogue, show titles, sponsor names, and quoted references.",
    prompt:
      "Podcast transcript with host and guest speakers. Preserve show titles, guest names, sponsor names, quoted phrases, and natural conversational sentence flow.",
    chunkMillis: 3200,
    diarize: true,
    contextLink: true,
    focusHint: "Host and guest flow",
  },
  discussion: {
    title: "Roundtable discussion",
    summary: "Good for brainstorming, panels, and open discussion where several people overlap and resume ideas.",
    prompt:
      "Roundtable discussion transcript. Preserve speaker changes, technical terms, names, acronyms, and sentence continuity across interrupted turns.",
    chunkMillis: 2400,
    diarize: true,
    contextLink: true,
    focusHint: "Multi-speaker continuity",
  },
  "oral-presentation": {
    title: "Oral presentation",
    summary: "Prefer longer coherent segments for a single main speaker, while still catching audience questions cleanly.",
    prompt:
      "Oral presentation transcript. Favor coherent full sentences, presentation terminology, slide references, and audience questions when they appear.",
    chunkMillis: 4200,
    diarize: false,
    contextLink: true,
    focusHint: "Longer presenter segments",
  },
  "tv-news": {
    title: "TV news segment",
    summary: "Keep headline-style pacing, people, places, dates, organizations, and numbers as accurate as possible.",
    prompt:
      "Broadcast news transcript. Preserve anchor names, locations, dates, organizations, numbers, headlines, and proper nouns with crisp punctuation.",
    chunkMillis: 1800,
    diarize: true,
    contextLink: true,
    focusHint: "Names and numbers",
  },
  interview: {
    title: "Interview transcript",
    summary: "Good for a structured Q and A with a clearer split between interviewer and interviewee.",
    prompt:
      "Interview transcript. Preserve interviewer questions, interviewee answers, names, quoted phrases, and sentence boundaries suited for readable review.",
    chunkMillis: 2800,
    diarize: true,
    contextLink: true,
    focusHint: "Question and answer clarity",
  },
};

const els = {
  engineName: document.querySelector("#engineName"),
  engineHint: document.querySelector("#engineHint"),
  speakerState: document.querySelector("#speakerState"),
  speakerHint: document.querySelector("#speakerHint"),
  ollamaState: document.querySelector("#ollamaState"),
  ollamaHint: document.querySelector("#ollamaHint"),
  starterModePill: document.querySelector("#starterModePill"),
  starterScenarioTitle: document.querySelector("#starterScenarioTitle"),
  starterScenarioSummary: document.querySelector("#starterScenarioSummary"),
  starterSegmentHint: document.querySelector("#starterSegmentHint"),
  starterSpeakerHint: document.querySelector("#starterSpeakerHint"),
  starterFocusHint: document.querySelector("#starterFocusHint"),
  entryModeButtons: [...document.querySelectorAll("[data-entry-mode]")],
  scenarioButtons: [...document.querySelectorAll("[data-scenario]")],
  starterPanel: document.querySelector("#starterPanel"),
  starterBackButton: document.querySelector("#starterBackButton"),
  sessionStatusText: document.querySelector("#sessionStatusText"),
  sessionCaption: document.querySelector("#sessionCaption"),
  liveSummary: document.querySelector("#liveSummary"),
  helperNote: document.querySelector("#helperNote"),
  captureSource: document.querySelector("#captureSource"),
  audioInputSelect: document.querySelector("#audioInputSelect"),
  refreshInputsButton: document.querySelector("#refreshInputsButton"),
  modelSelect: document.querySelector("#modelSelect"),
  modelHeadline: document.querySelector("#modelHeadline"),
  modelMetrics: document.querySelector("#modelMetrics"),
  modelFeatureStrip: document.querySelector("#modelFeatureStrip"),
  modelPill: document.querySelector("#modelPill"),
  modelSummary: document.querySelector("#modelSummary"),
  modelDetail: document.querySelector("#modelDetail"),
  installModelButton: document.querySelector("#installModelButton"),
  switchModelButton: document.querySelector("#switchModelButton"),
  modelInstallProgress: document.querySelector("#modelInstallProgress"),
  modelInstallStatus: document.querySelector("#modelInstallStatus"),
  modelInstallMeta: document.querySelector("#modelInstallMeta"),
  modelInstallTrack: document.querySelector("#modelInstallTrack"),
  modelInstallBar: document.querySelector("#modelInstallBar"),
  modelInstallLog: document.querySelector("#modelInstallLog"),
  chunkMillis: document.querySelector("#chunkMillis"),
  chunkMillisValue: document.querySelector("#chunkMillisValue"),
  chunkMillisLiveHint: document.querySelector("#chunkMillisLiveHint"),
  languageInput: document.querySelector("#languageInput"),
  promptInput: document.querySelector("#promptInput"),
  diarizeToggle: document.querySelector("#diarizeToggle"),
  cleanupBackendSelect: document.querySelector("#cleanupBackendSelect"),
  cleanupModelInput: document.querySelector("#cleanupModelInput"),
  cleanupModelSuggestions: document.querySelector("#cleanupModelSuggestions"),
  cleanupHint: document.querySelector("#cleanupHint"),
  systemAudioPanel: document.querySelector("#systemAudioPanel"),
  systemAudioHeadline: document.querySelector("#systemAudioHeadline"),
  systemAudioPill: document.querySelector("#systemAudioPill"),
  systemAudioSummary: document.querySelector("#systemAudioSummary"),
  systemAudioCommand: document.querySelector("#systemAudioCommand"),
  systemAudioDetail: document.querySelector("#systemAudioDetail"),
  copySystemAudioCommandButton: document.querySelector("#copySystemAudioCommandButton"),
  inputLevelLabel: document.querySelector("#inputLevelLabel"),
  inputLevelFill: document.querySelector("#inputLevelFill"),
  createSessionButton: document.querySelector("#createSessionButton"),
  startButton: document.querySelector("#startButton"),
  stopButton: document.querySelector("#stopButton"),
  livePill: document.querySelector("#livePill"),
  currentSessionHeading: document.querySelector("#currentSessionHeading"),
  currentSessionHint: document.querySelector("#currentSessionHint"),
  currentSessionTitleInput: document.querySelector("#currentSessionTitleInput"),
  currentSessionTitleSave: document.querySelector("#currentSessionTitleSave"),
  modeValue: document.querySelector("#modeValue"),
  durationValue: document.querySelector("#durationValue"),
  segmentCountValue: document.querySelector("#segmentCountValue"),
  speakerCountValue: document.querySelector("#speakerCountValue"),
  exportFormatSelect: document.querySelector("#exportFormatSelect"),
  downloadExportButton: document.querySelector("#downloadExportButton"),
  copyTranscriptButton: document.querySelector("#copyTranscriptButton"),
  clearHistoryButton: document.querySelector("#clearHistoryButton"),
  sessionIdPill: document.querySelector("#sessionIdPill"),
  timelineLead: document.querySelector("#timelineLead"),
  rosterLead: document.querySelector("#rosterLead"),
  markerLead: document.querySelector("#markerLead"),
  timelineHint: document.querySelector("#timelineHint"),
  warnings: document.querySelector("#warnings"),
  speakerRoster: document.querySelector("#speakerRoster"),
  speakerMarkers: document.querySelector("#speakerMarkers"),
  timeline: document.querySelector("#timeline"),
  sessionHistory: document.querySelector("#sessionHistory"),
  timelineItemTemplate: document.querySelector("#timelineItemTemplate"),
  dialInCard: document.querySelector("#dialInCard"),
  liveWorkflowCard: document.querySelector("#liveWorkflowCard"),
  liveTranscribingPanel: document.querySelector("#liveTranscribingPanel"),
  liveTranscribingPill: document.querySelector("#liveTranscribingPill"),
  liveTranscribingCaption: document.querySelector("#liveTranscribingCaption"),
  jumpToTranscriptButton: document.querySelector("#jumpToTranscriptButton"),
  transcriptStage: document.querySelector(".transcript-stage"),
};

async function boot() {
  bindEvents();
  await refreshStatus();
  await refreshPostProcessCatalog();
  await refreshModelCatalog();
  await refreshSystemAudioStatus();
  await refreshSessionHistory();
  initializeStarter();
  renderTranscript();
  await refreshAudioInputs(false);
  window.setInterval(() => {
    if (!isModelInstallRunning()) {
      return;
    }
    void refreshModelCatalog(false);
  }, 1200);
  window.setInterval(() => {
    if (state.liveCapture) {
      return;
    }
    void refreshPostProcessCatalog(false);
    void refreshModelCatalog(false);
    void refreshSystemAudioStatus(false);
    void refreshSessionHistory();
    void refreshRemoteSession();
  }, 5000);
}

function bindEvents() {
  els.entryModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const entryMode = button.dataset.entryMode;
      if (entryMode) {
        applyEntryModePreset(entryMode);
      }
    });
  });
  els.scenarioButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const scenarioId = button.dataset.scenario;
      if (scenarioId) {
        applyScenarioPreset(scenarioId, { collapse: true, scroll: true });
      }
    });
  });
  els.starterBackButton.addEventListener("click", () => {
    toggleStarterPanel(false, { scroll: true });
  });
  els.createSessionButton.addEventListener("click", () => {
    void createSession({ focusTitleInput: true });
  });
  els.startButton.addEventListener("click", startMic);
  els.stopButton.addEventListener("click", stopMic);
  els.currentSessionTitleSave.addEventListener("click", () => {
    void saveCurrentSessionTitle();
  });
  els.currentSessionTitleInput.addEventListener("input", () => {
    updateCurrentSessionPanel();
  });
  els.currentSessionTitleInput.addEventListener("blur", () => {
    void saveCurrentSessionTitle();
  });
  els.currentSessionTitleInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void saveCurrentSessionTitle();
    }
  });
  els.downloadExportButton.addEventListener("click", downloadExport);
  els.copyTranscriptButton.addEventListener("click", copyTranscript);
  els.clearHistoryButton.addEventListener("click", () => {
    void clearLiveHistory();
  });
  els.captureSource.addEventListener("change", () => {
    state.entryMode = els.captureSource.value;
    renderStarterPanel();
    updateCaptureUi();
    void refreshSystemAudioStatus(false);
  });
  els.chunkMillis.addEventListener("input", () => {
    void handleChunkMillisChange({ immediate: false });
  });
  els.chunkMillis.addEventListener("change", () => {
    void handleChunkMillisChange({ immediate: true });
  });
  els.modelSelect.addEventListener("change", renderModelControls);
  els.diarizeToggle.addEventListener("change", () => {
    renderModelControls();
    void refreshSystemAudioStatus(false);
  });
  els.languageInput.addEventListener("change", () => {
    void refreshSystemAudioStatus(false);
  });
  els.promptInput.addEventListener("change", () => {
    void refreshSystemAudioStatus(false);
  });
  els.cleanupBackendSelect.addEventListener("change", () => {
    syncCleanupModelInput(false);
    renderPostProcessControls();
    renderModelControls();
    updateSessionChrome();
  });
  els.cleanupModelInput.addEventListener("input", () => {
    renderPostProcessControls();
    renderModelControls();
    updateSessionChrome();
    void refreshSystemAudioStatus(false);
  });
  els.copySystemAudioCommandButton.addEventListener("click", copySystemAudioCommand);
  els.jumpToTranscriptButton.addEventListener("click", () => {
    scrollToWorkflowCard(els.transcriptStage);
  });
  els.installModelButton.addEventListener("click", () => {
    void installSelectedModel();
  });
  els.switchModelButton.addEventListener("click", () => {
    void switchSelectedModel();
  });
  els.refreshInputsButton.addEventListener("click", () => {
    void refreshAudioInputs(true);
  });
}

function initializeStarter() {
  applyEntryModePreset(state.entryMode, { persist: false, scroll: false });
  applyScenarioPreset(state.scenarioId, { persist: false, scroll: false, collapse: false });
  toggleStarterPanel(false);
}

function currentEntryPreset() {
  return ENTRY_PRESETS[state.entryMode] || ENTRY_PRESETS.microphone;
}

function currentScenarioPreset() {
  return SCENARIO_PRESETS[state.scenarioId] || SCENARIO_PRESETS.meeting;
}

function applyEntryModePreset(entryMode, { persist = false, scroll = false } = {}) {
  if (!ENTRY_PRESETS[entryMode]) {
    return;
  }

  state.entryMode = entryMode;
  els.captureSource.value = entryMode;
  updateCaptureUi();

  renderStarterPanel();
  if (persist) {
    updateSessionChrome();
  }
  if (scroll) {
    scrollToWorkflowCard(state.starterCollapsed ? els.dialInCard : els.starterPanel);
  }
}

function applyScenarioPreset(scenarioId, { persist = true, scroll = false, collapse = false } = {}) {
  const preset = SCENARIO_PRESETS[scenarioId];
  if (!preset) {
    return;
  }

  state.scenarioId = scenarioId;
  els.promptInput.value = preset.prompt;
  els.diarizeToggle.checked = preset.diarize;
  els.chunkMillis.value = String(normalizeChunkMillis(preset.chunkMillis));
  renderStarterPanel();
  updateSessionChrome();
  if (collapse) {
    toggleStarterPanel(true, { scroll });
  }

  if (persist) {
    void persistChunkMillisSetting(normalizeChunkMillis(preset.chunkMillis)).catch(() => {});
  }
  if (scroll && !collapse) {
    focusDialInControls();
  }
}

function renderStarterPanel() {
  const entryPreset = currentEntryPreset();
  const scenarioPreset = currentScenarioPreset();
  const activeChunkMillis = configuredChunkMillis();

  els.entryModeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.entryMode === state.entryMode);
  });
  els.scenarioButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.scenario === state.scenarioId);
  });

  els.starterModePill.textContent = entryPreset.label;
  els.starterScenarioTitle.textContent = scenarioPreset.title;
  els.starterScenarioSummary.textContent = `${scenarioPreset.summary} ${entryPreset.summary}`;
  els.starterSegmentHint.textContent = `${formatChunkMillis(activeChunkMillis)} live segments`;
  els.starterSpeakerHint.textContent = scenarioPreset.diarize ? "Speaker labels on" : "Speaker labels off";
  els.starterFocusHint.textContent = scenarioPreset.focusHint;
  els.liveWorkflowCard.classList.add("is-guided");
}

function toggleStarterPanel(collapse, { scroll = false } = {}) {
  state.starterCollapsed = collapse;
  els.starterPanel.hidden = collapse;
  els.dialInCard.hidden = !collapse;
  if (scroll) {
    scrollToWorkflowCard(collapse ? els.dialInCard : els.starterPanel);
  }
}

function renderStarterLaunchState() {
  const liveActive = Boolean(state.liveCapture);
  const liveFinishing = liveActive && Boolean(state.liveCapture?.stopRequested);
  const isTranscribing = liveActive || liveFinishing;
  const wasAlreadyVisible = !els.liveTranscribingPanel.hidden;

  els.liveTranscribingPanel.hidden = !isTranscribing;

  if (isTranscribing) {
    els.starterPanel.hidden = true;
    els.dialInCard.hidden = true;
    els.liveTranscribingPill.textContent = liveFinishing ? "Finishing" : "Recording";
    els.liveTranscribingCaption.textContent =
      els.liveSummary.textContent ||
      "Recording is live. Transcript segments appear below and can be edited while recording.";
    if (!wasAlreadyVisible) {
      scrollToWorkflowCard(els.transcriptStage);
    }
  } else {
    els.starterPanel.hidden = state.starterCollapsed;
    els.dialInCard.hidden = !state.starterCollapsed;
  }
}

function focusDialInControls() {
  scrollToWorkflowCard(els.dialInCard);
  els.promptInput.focus();
}

function scrollToWorkflowCard(node) {
  if (!node) {
    return;
  }
  node.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  state.status = await response.json();
  state.systemAudio = state.status.systemAudio || state.systemAudio;
  const engine = state.status.engine;
  const speaker = state.status.speakerRecognition;
  els.engineName.textContent = engine.engine;
  els.engineHint.textContent = engine.warnings?.[0] || "Local engine ready.";
  els.speakerState.textContent = speaker.ready ? "Ready" : "Limited";
  els.speakerHint.textContent = speaker.warning || "Speaker embedding pipeline ready.";
  renderOllamaStatus();
  els.chunkMillis.min = String(currentChunkMillisBounds().min);
  els.chunkMillis.max = String(currentChunkMillisBounds().max);
  els.chunkMillis.value = String(state.status.settings.chunkMillis);
  renderChunkMillisControls();
  renderPostProcessControls();
  renderModelControls();
  renderStarterPanel();
  updateSessionChrome();
  updateCaptureUi();
  renderSystemAudioPanel();
}

async function refreshPostProcessCatalog(showErrors = false) {
  try {
    const response = await fetch("/api/postprocess/catalog");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not load local AI assistants.");
    }
    state.postProcessCatalog = data;
    syncCleanupBackendSelect();
    syncCleanupModelInput(true);
    renderPostProcessControls();
    renderModelControls();
    renderOllamaStatus();
  } catch (error) {
    if (showErrors) {
      window.alert(error.message || "Could not load local AI assistants.");
    }
  }
}

async function preparePostProcessingForLiveStart() {
  const backend = selectedCleanupBackend();
  if (!backend || backend === "none") {
    return;
  }

  try {
    const response = await fetch("/api/postprocess/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        backend,
        model: selectedCleanupModel(),
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "Could not prepare the selected AI assistant.");
    }
    state.status = {
      ...(state.status || {}),
      postProcessing: data.postProcessing || state.status?.postProcessing || null,
    };
    if (data.catalog) {
      state.postProcessCatalog = data.catalog;
    }
    renderPostProcessControls();
    renderOllamaStatus();
  } catch (error) {
    console.warn("Could not prepare live post-processing.", error);
  }
}

async function refreshSystemAudioStatus(showErrors = false) {
  try {
    const params = new URLSearchParams();
    if (state.session?.sessionId) {
      params.set("sessionId", state.session.sessionId);
    }
    const language = els.languageInput.value.trim();
    const prompt = els.promptInput.value.trim();
    if (language) {
      params.set("language", language);
    }
    if (prompt) {
      params.set("prompt", prompt);
    }
    params.set("diarize", String(Boolean(els.diarizeToggle.checked)));
    params.set("chunkMillis", String(configuredChunkMillis()));

    const response = await fetch(`/api/system-audio?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not load Mac sound output status.");
    }
    state.systemAudio = data.systemAudio;
    renderSystemAudioPanel();
    updateCaptureUi();
    updateSessionChrome();
  } catch (error) {
    if (showErrors) {
      window.alert(error.message || "Could not load Mac sound output status.");
    }
  }
}

function syncCleanupBackendSelect() {
  const catalog = state.postProcessCatalog;
  if (!catalog) {
    return;
  }

  const selectedValue = els.cleanupBackendSelect.value;
  els.cleanupBackendSelect.replaceChildren();
  const backends = (catalog.backends || []).filter((backend) => backend.id !== "none");
  backends.forEach((backend) => {
    els.cleanupBackendSelect.append(new Option(backend.label, backend.id));
  });

  const preferredValue = backends.some((backend) => backend.id === selectedValue)
    ? selectedValue
    : backends.some((backend) => backend.id === catalog.defaultBackend && catalog.defaultBackend !== "none")
      ? catalog.defaultBackend
      : recommendedCleanupBackendId(backends);
  els.cleanupBackendSelect.value = preferredValue;
}

function syncCleanupModelInput(preserveCurrentValue) {
  const backend = selectedCleanupBackendOption();
  const suggestions = backend?.suggestedModels || [];
  els.cleanupModelSuggestions.replaceChildren();
  suggestions.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    els.cleanupModelSuggestions.append(option);
  });

  const currentValue = els.cleanupModelInput.value.trim();
  if (!preserveCurrentValue || !currentValue) {
    els.cleanupModelInput.value = backend?.defaultModel || "";
  }
  els.cleanupModelInput.placeholder = backend?.modelPlaceholder || "No model needed";
}

function selectedCleanupBackend() {
  return els.cleanupBackendSelect.value || state.postProcessCatalog?.defaultBackend || recommendedCleanupBackendId();
}

function selectedCleanupBackendOption() {
  const backends = state.postProcessCatalog?.backends || [];
  return backends.find((backend) => backend.id === selectedCleanupBackend()) || null;
}

function selectedCleanupModel() {
  const customValue = els.cleanupModelInput.value.trim();
  if (customValue) {
    return customValue;
  }
  return selectedCleanupBackendOption()?.defaultModel || defaultCleanupModelForBackend(selectedCleanupBackend());
}

function recommendedCleanupBackendId(backends = state.postProcessCatalog?.backends || []) {
  const enabledBackends = backends.filter((backend) => backend.id !== "none");
  return enabledBackends.find((backend) => backend.id === "ollama" && backend.ready)?.id
    || enabledBackends.find((backend) => backend.id === "mlx" && backend.ready)?.id
    || enabledBackends.find((backend) => backend.id === "ollama")?.id
    || enabledBackends.find((backend) => backend.id === "mlx")?.id
    || enabledBackends[0]?.id
    || "ollama";
}

function defaultCleanupModelForBackend(backendId) {
  if (backendId === "mlx") {
    return "mlx-community/Qwen2.5-3B-Instruct-4bit";
  }
  return "qwen2.5:3b-instruct";
}

function renderPostProcessControls() {
  const catalog = state.postProcessCatalog;
  const backend = selectedCleanupBackendOption();
  const backendName = backend?.label || "Local AI assistant";
  const modelName = selectedCleanupModel();

  if (!catalog) {
    els.cleanupBackendSelect.disabled = true;
    els.cleanupModelInput.disabled = true;
    els.cleanupHint.textContent = "Checking which local AI assistants are available on this Mac.";
    return;
  }

  els.cleanupBackendSelect.disabled = false;
  els.cleanupModelInput.disabled = false;

  if (backend?.ready) {
    els.cleanupHint.textContent = modelName
      ? `${backendName} is ready. New chunks will use ${modelName}.`
      : `${backendName} is ready for the next live chunks.`;
    return;
  }

  const warning = backend?.warning ? ` ${backend.warning}` : "";
  els.cleanupHint.textContent = `${backendName} is not ready yet.${warning || ` ${backend?.description || ""}`}`.trim();
}

function ollamaBackendStatus() {
  const backends = state.postProcessCatalog?.backends || [];
  return backends.find((backend) => backend.id === "ollama") || null;
}

function renderOllamaStatus() {
  const status = state.status?.postProcessing || null;
  const backend = ollamaBackendStatus();
  const ollamaSelected = selectedCleanupBackend() === "ollama";
  const statusUsesOllama = status?.backend === "ollama";
  const modelName = ollamaSelected ? selectedCleanupModel() : backend?.defaultModel || status?.model || "qwen2.5:3b-instruct";

  if (!status && !backend) {
    els.ollamaState.textContent = "Checking…";
    els.ollamaHint.textContent = "Checking whether the local AI assistant runtime is running.";
    return;
  }

  const ollamaReady = Boolean(backend?.ready || (statusUsesOllama && status?.ready));
  const warning = backend?.warning || (statusUsesOllama ? status?.warning : null);

  if (ollamaReady) {
    els.ollamaState.textContent = "Running";
    if (ollamaSelected) {
      els.ollamaHint.textContent = `Ollama is running locally. New live chunks can use ${modelName} right now.`;
      return;
    }
    els.ollamaHint.textContent = `Ollama is available locally with ${modelName}. Switch the AI assistant to Ollama any time.`;
    return;
  }

  els.ollamaState.textContent = "Not running";
  if (warning) {
    els.ollamaHint.textContent = `Ollama is not available right now. ${warning}`;
    return;
  }
  els.ollamaHint.textContent = "Ollama is not available right now. Start the local Ollama service if you want AI assistant help.";
}

function renderSystemAudioPanel() {
  const modeSelected = els.captureSource.value === "mac-system-audio";
  els.systemAudioPanel.hidden = !modeSelected;
  if (!modeSelected) {
    return;
  }

  const helper = state.systemAudio;
  const uiMessage = (state.systemAudioUiMessage || "").trim();
  if (!helper) {
    els.systemAudioPill.textContent = "Checking";
    els.systemAudioHeadline.textContent = "Checking the native helper…";
    els.systemAudioSummary.textContent =
      "LocalScribe is checking whether the native ScreenCaptureKit helper is available for current Mac sound output.";
    els.systemAudioCommand.textContent = "";
    els.systemAudioDetail.textContent = "If needed, LocalScribe can prepare the helper automatically before Mac output capture starts.";
    els.copySystemAudioCommandButton.disabled = true;
    return;
  }

  const currentSessionAttached = helper.sessionId && helper.sessionId === state.session?.sessionId;
  const helperRunning = Boolean(helper.running);
  const helperReady = Boolean(helper.available);
  const command = helperReady ? helper.launchCommand : helper.buildCommand;

  if (helperRunning && currentSessionAttached) {
    els.systemAudioPill.textContent = "Running";
    els.systemAudioHeadline.textContent = "Current Mac sound output is live";
    els.systemAudioSummary.textContent =
      "The native helper is already capturing the sound coming from this Mac and streaming it into this session.";
  } else if (helperRunning) {
    els.systemAudioPill.textContent = "Busy";
    els.systemAudioHeadline.textContent = "Native helper is attached elsewhere";
    els.systemAudioSummary.textContent =
      "The native helper is already streaming Mac output into another LocalScribe session. Stop it there before starting a new one here.";
  } else if (helperReady) {
    els.systemAudioPill.textContent = "Ready";
    els.systemAudioHeadline.textContent = "Native Mac sound capture is ready";
    els.systemAudioSummary.textContent =
      "Use Start Mac Output to capture whatever is currently playing through this Mac without depending on browser audio support.";
  } else {
    els.systemAudioPill.textContent = "Auto-prepare";
    els.systemAudioHeadline.textContent = "Mac output helper will be prepared automatically";
    els.systemAudioSummary.textContent =
      "On the first Mac output capture, LocalScribe will build the native helper in the backend and then start streaming automatically.";
  }

  els.systemAudioCommand.textContent = command || "";
  const troubleshooting = helperReady
    ? "The helper will request Screen Recording permission the first time macOS needs it."
    : "The first start can take a moment while Swift builds the helper. If that automatic build fails, use the command above for debugging and make sure the active Swift compiler matches the active macOS SDK.";
  els.systemAudioDetail.textContent = uiMessage || helper.warning || troubleshooting;
  els.copySystemAudioCommandButton.textContent = helperReady ? "Copy Launch Command" : "Copy Diagnostic Command";
  els.copySystemAudioCommandButton.disabled = !command;
}

function updateInputLevelMeter(level) {
  const normalized = Math.max(0, Math.min(1, Number(level) || 0));
  els.inputLevelFill.style.width = `${Math.round(normalized * 100)}%`;
  if (!state.liveCapture) {
    els.inputLevelLabel.textContent = INPUT_LEVEL_IDLE;
    return;
  }
  if (normalized < 0.01) {
    els.inputLevelLabel.textContent = "Very quiet";
    return;
  }
  if (normalized < 0.04) {
    els.inputLevelLabel.textContent = "Low";
    return;
  }
  if (normalized < 0.14) {
    els.inputLevelLabel.textContent = "Good";
    return;
  }
  els.inputLevelLabel.textContent = "Strong";
}

function quietInputBoost(samples) {
  let peak = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const value = Math.abs(samples[index]);
    if (value > peak) {
      peak = value;
    }
  }
  updateInputLevelMeter(peak);
  if (peak <= 0 || peak >= 0.025) {
    return samples;
  }

  const gain = Math.min(18, 0.12 / peak);
  if (gain <= 1.2) {
    return samples;
  }

  const boosted = new Float32Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    boosted[index] = Math.max(-1, Math.min(1, samples[index] * gain));
  }
  return boosted;
}

async function refreshModelCatalog(showErrors = false) {
  try {
    const response = await fetch("/api/models");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not load Whisper models.");
    }
    state.modelCatalog = data;
    syncModelSelection();
    renderModelControls();
  } catch (error) {
    if (showErrors) {
      window.alert(error.message || "Could not load Whisper models.");
    }
  }
}

function syncModelSelection() {
  const catalog = state.modelCatalog;
  if (!catalog) {
    return;
  }

  const selectedValue = els.modelSelect.value;
  els.modelSelect.replaceChildren();

  if (!catalog.supported) {
    els.modelSelect.append(new Option("Model switching unavailable", ""));
    els.modelSelect.disabled = true;
    return;
  }

  const models = catalog.models || [];
  const recommendedModel = models.find((model) => model.recommended) || null;
  models.forEach((model) => {
    const suffix = model.installed ? "Installed" : "Download required";
    const option = new Option(`${model.label} · ${suffix}`, model.id);
    els.modelSelect.append(option);
  });

  els.modelSelect.disabled = false;
  const activeModelId = catalog.activeModel || "";
  const preferredValue = models.some((model) => model.id === selectedValue)
    ? selectedValue
    : models.some((model) => model.id === activeModelId)
      ? activeModelId
      : recommendedModel?.id || models[0]?.id || "";
  els.modelSelect.value = preferredValue;
}

function selectedModel() {
  const models = state.modelCatalog?.models || [];
  return models.find((model) => model.id === els.modelSelect.value) || null;
}

function renderModelControls() {
  const catalog = state.modelCatalog;
  const model = selectedModel();
  const modelFeatures = buildModelFeatures(model);
  const modelMetrics = buildModelMetrics(model);

  if (!catalog) {
    els.modelPill.textContent = "Loading";
    els.modelSummary.textContent = "Loading local Whisper model choices.";
    els.modelDetail.textContent = "Checking what is already installed and which model is active now.";
    els.modelHeadline.textContent = "Loading Whisper model…";
    renderModelMetrics([]);
    renderFeatureStrip([]);
    renderModelInstallProgress(null);
    els.installModelButton.disabled = true;
    els.switchModelButton.disabled = true;
    return;
  }

  if (!catalog.supported) {
    els.modelPill.textContent = "Unavailable";
    els.modelSummary.textContent = catalog.reason || "Model management is not available for the current engine.";
    els.modelDetail.textContent = "Switch to WhisperKit if you want model installation and runtime model changes.";
    els.modelHeadline.textContent = "Model management unavailable";
    renderModelMetrics([]);
    renderFeatureStrip([
      {
        label: "WhisperKit required",
        tone: "warm",
      },
    ]);
    renderModelInstallProgress(null);
    els.installModelButton.disabled = true;
    els.switchModelButton.disabled = true;
    return;
  }

  const install = catalog.install || null;
  const installingModelId = catalog.installingModel || install?.model || null;
  const activeModel = catalog.models?.find((entry) => entry.active) || null;
  const installRunning = Boolean(install?.running);
  renderModelInstallProgress(install);

  if (installRunning) {
    els.modelPill.textContent = "Installing";
    els.modelSummary.textContent = `Downloading ${labelForModelId(installingModelId)} into LocalScribe-managed storage.`;
  } else if (model?.active) {
    els.modelPill.textContent = "Active";
    els.modelSummary.textContent = `${model.label} is active now. New live chunks use this model immediately.`;
  } else {
    els.modelPill.textContent = model?.installed ? "Installed" : "Ready To Install";
    els.modelSummary.textContent = model
      ? `${model.label} is ${model.installed ? "installed and ready" : "not installed yet"}.`
      : "Choose a model to continue.";
  }

  let detail = "";
  if (model) {
    els.modelHeadline.textContent = model.recommended ? `${model.label} · Recommended` : model.label;
    detail = `${model.speedHint} · ${model.qualityHint} · ${model.sizeHint}. ${model.description}`;
    if (!model.installed) {
      detail += " Install it first, then switch when you are ready.";
      if (model.recommended) {
        detail += " This is the default LocalScribe model for a fresh WhisperKit setup.";
      }
    } else if (!model.active && state.liveCapture) {
      detail += " Switching during a live session keeps recording open and applies to the next processed chunks.";
    }
  } else {
    els.modelHeadline.textContent = "Choose a Whisper model";
  }
  if (install?.warning) {
    detail = `${install.warning} ${detail}`.trim();
  }
  els.modelDetail.textContent = detail || "Installed models switch quickly. Missing models can be downloaded first.";
  renderModelMetrics(modelMetrics);
  renderFeatureStrip(modelFeatures);

  const disableAll = state.modelActionPending || installRunning || !model;
  els.installModelButton.disabled = disableAll || Boolean(model?.installed);
  els.switchModelButton.disabled = disableAll || !Boolean(model?.installed) || Boolean(model?.active);

  if (state.modelActionPending) {
    els.installModelButton.textContent = "Working…";
    els.switchModelButton.textContent = "Working…";
    return;
  }

  els.installModelButton.textContent = model?.installed
    ? "Installed"
    : model?.recommended
      ? "Install Recommended Model"
      : "Install Model";
  els.switchModelButton.textContent = model?.active ? "Using This Model" : "Use Model";

  if (activeModel && !installRunning && model && model.id !== activeModel.id) {
    els.modelSummary.textContent += ` Active now: ${activeModel.label}.`;
  }
}

function renderModelInstallProgress(install) {
  const show = Boolean(install?.running || install?.warning);
  els.modelInstallProgress.hidden = !show;
  if (!show) {
    els.modelInstallTrack.classList.remove("is-indeterminate");
    els.modelInstallBar.style.width = "0%";
    els.modelInstallStatus.textContent = "Starting model download…";
    els.modelInstallMeta.textContent = "Preparing LocalScribe-managed storage.";
    els.modelInstallLog.textContent = "";
    return;
  }

  const progressPercent = Number.isFinite(Number(install?.progressPercent))
    ? Math.max(0, Math.min(100, Math.round(Number(install.progressPercent))))
    : null;
  const progressLabel = install?.progressLabel || install?.warning || "Downloading model files…";
  const logTail = Array.isArray(install?.logTail) ? install.logTail : [];

  els.modelInstallStatus.textContent = progressLabel;
  if (install?.warning) {
    els.modelInstallMeta.textContent = "Install failed. Review the recent installer output below.";
  } else if (progressPercent !== null) {
    els.modelInstallMeta.textContent = `${progressPercent}% downloaded`;
  } else if (install?.running) {
    els.modelInstallMeta.textContent = "Download in progress. Progress will update as WhisperKit reports it.";
  } else {
    els.modelInstallMeta.textContent = "Installer finished.";
  }

  els.modelInstallTrack.classList.toggle("is-indeterminate", progressPercent === null && Boolean(install?.running));
  els.modelInstallBar.style.width = progressPercent !== null ? `${progressPercent}%` : "36%";
  els.modelInstallLog.textContent = logTail.length > 0 ? logTail.join("\n") : "Installer output will appear here.";
}

function isModelInstallRunning() {
  return Boolean(state.modelCatalog?.install?.running);
}

function buildModelMetrics(model) {
  if (!model) {
    return [];
  }
  return [
    { label: "Speed", value: model.speedHint },
    { label: "Quality", value: model.qualityHint },
    { label: "Size", value: model.sizeHint },
  ];
}

function buildModelFeatures(model) {
  if (!model) {
    return [];
  }

  const featureItems = [];
  if (model.recommended) {
    featureItems.push({ label: "Recommended default", tone: "good" });
  }
  featureItems.push({
    label: realtimeLabelForModel(model),
    tone: model.speedHint === "Slowest" ? "neutral" : "good",
  });
  featureItems.push({
    label: model.installed ? "Installed locally" : "Download required",
    tone: model.installed ? "good" : "warm",
  });
  featureItems.push({
    label: els.diarizeToggle.checked
      ? state.status?.speakerRecognition?.ready
        ? "Speaker recognition on"
        : "Speaker recognition limited"
      : "Speaker labels off",
    tone: els.diarizeToggle.checked && state.status?.speakerRecognition?.ready ? "good" : "neutral",
  });
  featureItems.push({
    label: "Context linking on",
    tone: "good",
  });
  featureItems.push({
    label: postProcessingLabel(),
    tone: selectedCleanupBackendOption()?.ready ? "good" : "neutral",
  });
  return featureItems;
}

function postProcessingLabel() {
  const backend = selectedCleanupBackendOption();
  if (backend?.ready) {
    return `AI assistant on (${backend.label})`;
  }
  return `AI assistant pending (${backend?.label || selectedCleanupBackend()})`;
}

function realtimeLabelForModel(model) {
  if (model.speedHint === "Fastest" || model.speedHint === "Fast" || model.speedHint === "Balanced") {
    return "Realtime-friendly";
  }
  if (model.speedHint === "Moderate") {
    return "Live with moderate latency";
  }
  return "Best for slower, more careful passes";
}

function renderModelMetrics(metrics) {
  els.modelMetrics.replaceChildren();
  metrics.forEach((metric) => {
    const node = document.createElement("div");
    node.className = "model-metric";
    node.innerHTML = `<span>${escapeHtml(metric.label)}</span><strong>${escapeHtml(metric.value)}</strong>`;
    els.modelMetrics.append(node);
  });
}

function renderFeatureStrip(features) {
  els.modelFeatureStrip.replaceChildren();
  features.forEach((feature) => {
    const node = document.createElement("span");
    node.className = `feature-badge${feature.tone ? ` is-${feature.tone}` : ""}`;
    node.textContent = feature.label;
    els.modelFeatureStrip.append(node);
  });
}

function labelForModelId(modelId) {
  const models = state.modelCatalog?.models || [];
  return models.find((model) => model.id === modelId)?.label || modelId || "selected model";
}

async function installSelectedModel() {
  const model = selectedModel();
  if (!model) {
    return;
  }

  state.modelActionPending = true;
  renderModelControls();
  try {
    const response = await fetch("/api/models/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modelId: model.id }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Could not install ${model.label}.`);
    }
    state.modelCatalog = data;
    syncModelSelection();
  } catch (error) {
    window.alert(error.message || `Could not install ${model.label}.`);
  } finally {
    state.modelActionPending = false;
    renderModelControls();
  }
}

async function switchSelectedModel() {
  const model = selectedModel();
  if (!model) {
    return;
  }
  if (!model.installed) {
    window.alert(`${model.label} is not installed yet. Install it first, then switch.`);
    return;
  }

  state.modelActionPending = true;
  renderModelControls();
  try {
    const response = await fetch("/api/models/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modelId: model.id }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `Could not switch to ${model.label}.`);
    }
    state.modelCatalog = data;
    syncModelSelection();
    await refreshStatus();
  } catch (error) {
    window.alert(error.message || `Could not switch to ${model.label}.`);
  } finally {
    state.modelActionPending = false;
    renderModelControls();
  }
}

async function createSession({ focusTitleInput = false } = {}) {
  await flushPendingSegmentTextSaves();
  const response = await fetch("/api/sessions", { method: "POST" });
  const data = await response.json();
  state.session = data.session;
  state.sequence = 1;
  state.mode = "Live";
  setTranscriptFromSession();
  updateSessionChrome();
  void refreshSystemAudioStatus(false);
  await refreshSessionHistory();
  renderTranscript();
  if (focusTitleInput) {
    els.currentSessionTitleInput.focus();
    els.currentSessionTitleInput.select();
  }
}

async function startMic() {
  if (!state.session || state.session.sessionType === "upload") {
    await createSession();
  }

  try {
    state.systemAudioUiMessage = "";
    await preparePostProcessingForLiveStart();
    const sourceMode = els.captureSource.value;
    if (sourceMode === "mac-system-audio") {
      state.systemAudioUiMessage =
        "Preparing native Mac sound output capture. The first start can take a moment while LocalScribe builds the helper.";
      els.livePill.textContent = "Preparing";
      els.startButton.disabled = true;
      els.stopButton.disabled = true;
      renderSystemAudioPanel();
      updateSessionChrome();
      await startSystemAudioCapture();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      window.alert("Audio capture is not supported in this browser.");
      return;
    }

    await connectSocket();
    const capture = await acquireCaptureStream(sourceMode);
    state.captureStream = capture.rawStream;
    state.mediaStream = capture.recorderStream;
    state.liveCapture = await startLiveAudioCapture(state.mediaStream);
    els.livePill.textContent = "Recording";
    els.startButton.disabled = true;
    els.stopButton.disabled = false;
    state.mode = "Live";
    updateSessionChrome();
    renderTranscript();
  } catch (error) {
    await abandonLiveCapture();
    if (els.captureSource.value === "mac-system-audio") {
      handleSystemAudioStartFailure(error.message || "Could not start current Mac sound output capture.");
      return;
    }
    window.alert(error.message || "Could not start audio capture.");
  }
}

async function startSystemAudioCapture() {
  const sessionId = state.session?.sessionId;
  if (!sessionId) {
    throw new Error("No session available.");
  }

  const response = await fetch("/api/system-audio/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sessionId,
      language: els.languageInput.value.trim() || null,
      prompt: els.promptInput.value.trim() || null,
      diarize: els.diarizeToggle.checked,
      chunkMillis: configuredChunkMillis(),
      postProcessBackend: selectedCleanupBackend(),
      postProcessModel: selectedCleanupModel(),
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Could not start current Mac sound output capture.");
  }

  state.systemAudio = data.systemAudio || state.systemAudio;
  state.session = data.session || state.session;
  state.liveCapture = {
    mode: "mac-system-audio",
    awaitingAck: false,
    stopRequested: false,
    inputStopped: false,
    pollTimer: window.setInterval(() => {
      void pollSystemAudioSession();
    }, 1000),
  };
  els.livePill.textContent = "Recording";
  els.startButton.disabled = true;
  els.stopButton.disabled = false;
  state.mode = "Live";
  setTranscriptFromSession();
  updateSessionChrome();
  renderTranscript();
  renderSystemAudioPanel();
}

function handleSystemAudioStartFailure(message) {
  state.systemAudioUiMessage =
    `${message} LocalScribe already tried to prepare the helper automatically. Review the details below for the failed build or launch step.`;
  els.livePill.textContent = "Idle";
  els.startButton.disabled = false;
  els.stopButton.disabled = true;
  updateSessionChrome();
  renderSystemAudioPanel();
  scrollToWorkflowCard(els.dialInCard);
}

async function stopMic() {
  const liveCapture = state.liveCapture;
  if (!liveCapture) {
    await finalizeStopMic();
    return;
  }

  if (liveCapture.mode === "mac-system-audio") {
    liveCapture.stopRequested = true;
    els.livePill.textContent = "Finishing";
    els.startButton.disabled = true;
    els.stopButton.disabled = true;
    updateSessionChrome();
    await stopSystemAudioCapture();
    await finalizeStopMic();
    return;
  }

  liveCapture.stopRequested = true;
  els.livePill.textContent = "Finishing";
  els.startButton.disabled = true;
  els.stopButton.disabled = true;
  updateSessionChrome();

  await stopAudioInput(liveCapture);
  if (liveCapture.awaitingAck) {
    return;
  }

  const flushed = await flushPendingAudioChunk(liveCapture, true);
  if (!flushed) {
    await finalizeStopMic();
  }
}

async function stopSystemAudioCapture() {
  const response = await fetch("/api/system-audio/stop", { method: "POST" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Could not stop current Mac sound output capture.");
  }
  state.systemAudio = data.systemAudio || state.systemAudio;
  renderSystemAudioPanel();
}

async function connectSocket() {
  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    return;
  }

  const sessionId = state.session?.sessionId;
  if (!sessionId) {
    throw new Error("No session available.");
  }

  const socket = new WebSocket(wsUrl(`/ws/live/${sessionId}`));
  state.socket = socket;

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "error") {
      void abandonLiveCapture(payload.detail || "The live transcription socket reported an error.");
      return;
    }
    if (payload.type === "chunk_processed") {
      handleLiveChunkProcessed();
    }
    if (payload.session) {
      state.session = payload.session;
      state.mode = "Live";
      setTranscriptFromSession();
      updateSessionChrome();
      renderTranscript();
    }
  });

  socket.addEventListener("close", () => {
    if (state.socket !== socket) {
      return;
    }
    void abandonLiveCapture("The live transcription connection closed. Start the microphone again.");
  });

  await new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("Socket connection timed out.")), 5000);
    socket.addEventListener(
      "open",
      () => {
        window.clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
    socket.addEventListener(
      "error",
      () => {
        window.clearTimeout(timer);
        reject(new Error("Could not connect to live transcription socket."));
      },
      { once: true },
    );
  });
}

async function copyTranscript() {
  await flushPendingSegmentTextSaves();
  const text = composeTranscriptText(state.transcript?.segments || []);
  if (!text) {
    return;
  }

  if (!navigator.clipboard?.writeText) {
    window.alert("Clipboard access is not available in this browser.");
    return;
  }

  await navigator.clipboard.writeText(text);
  els.copyTranscriptButton.textContent = "Copied";
  window.setTimeout(() => {
    els.copyTranscriptButton.textContent = "Copy Transcript";
  }, 1200);
}

async function copySystemAudioCommand() {
  const command = state.systemAudio?.available ? state.systemAudio?.launchCommand : state.systemAudio?.buildCommand;
  if (!command) {
    return;
  }
  if (!navigator.clipboard?.writeText) {
    window.alert("Clipboard access is not available in this browser.");
    return;
  }
  await navigator.clipboard.writeText(command);
  const original = els.copySystemAudioCommandButton.textContent;
  els.copySystemAudioCommandButton.textContent = "Copied";
  window.setTimeout(() => {
    els.copySystemAudioCommandButton.textContent = original;
  }, 1200);
}

async function downloadExport() {
  const sessionId = state.session?.sessionId;
  if (!sessionId) {
    window.alert("Open or create a saved session first.");
    return;
  }

  await flushPendingSegmentTextSaves();
  const format = els.exportFormatSelect.value;
  await downloadSessionExport(sessionId, format);
}

async function downloadSessionExport(sessionId, format) {
  const response = await fetch(`/api/sessions/${sessionId}/export?format=${encodeURIComponent(format)}`);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    window.alert(data.detail || "Could not export this session.");
    return;
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  const filename = filenameMatch?.[1] || `localscribe.${format}`;
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(objectUrl);
}

async function refreshSessionHistory() {
  const response = await fetch("/api/sessions");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  state.sessions = data.sessions || [];
  renderSessionHistory();
}

async function openSession(sessionId) {
  await flushPendingSegmentTextSaves();
  const response = await fetch(`/api/sessions/${sessionId}`);
  const data = await response.json();
  if (!response.ok) {
    window.alert(data.detail || "Could not load that session.");
    return;
  }
  state.session = data.session;
  state.mode = state.session.sessionType === "upload" ? "Batch" : "Live";
  setTranscriptFromSession();
  updateSessionChrome();
  void refreshSystemAudioStatus(false);
  renderTranscript();
}

async function refreshRemoteSession() {
  if (!state.session?.sessionId || state.liveCapture) {
    return;
  }

  const response = await fetch(`/api/sessions/${state.session.sessionId}`);
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  state.session = data.session;
  if (!state.mode || state.mode === "Waiting") {
    state.mode = state.session.sessionType === "upload" ? "Batch" : "Live";
  }
  setTranscriptFromSession();
  updateSessionChrome();
  void refreshSystemAudioStatus(false);
  renderTranscript();
}

async function pollSystemAudioSession() {
  const sessionId = state.session?.sessionId;
  if (!sessionId || state.liveCapture?.mode !== "mac-system-audio") {
    return;
  }

  try {
    const [sessionResponse, helperResponse] = await Promise.all([
      fetch(`/api/sessions/${sessionId}`),
      fetch(`/api/system-audio?${new URLSearchParams({
        sessionId,
        language: els.languageInput.value.trim(),
        prompt: els.promptInput.value.trim(),
        diarize: String(Boolean(els.diarizeToggle.checked)),
        chunkMillis: String(configuredChunkMillis()),
      }).toString()}`),
    ]);

    if (sessionResponse.ok) {
      const data = await sessionResponse.json();
      state.session = data.session;
      setTranscriptFromSession();
      renderTranscript();
    }

    if (helperResponse.ok) {
      const data = await helperResponse.json();
      state.systemAudio = data.systemAudio;
      renderSystemAudioPanel();
      if (!data.systemAudio?.running && !state.liveCapture?.stopRequested) {
        await finalizeStopMic();
        return;
      }
    }
  } catch (error) {
    console.warn("Could not refresh native Mac sound capture.", error);
  }

  updateSessionChrome();
}

function composeTranscriptText(segments) {
  return (segments || []).map((segment) => currentSegmentText(segment)).filter(Boolean).join("\n");
}

function currentSegmentText(segment) {
  return state.segmentDrafts[segment.segmentId] ?? segment.text ?? "";
}

function sessionTimelineSegments() {
  return [...(state.session?.segments || []), ...(state.session?.draftSegments || [])];
}

function sessionSegmentById(segmentId) {
  return sessionTimelineSegments().find((segment) => segment.segmentId === segmentId) || null;
}

function visibleLiveSegmentCount() {
  return sessionTimelineSegments().length;
}

function shouldUsePostProcessingForLiveChunk() {
  return ALWAYS_ENABLE_POST_PROCESSING && visibleLiveSegmentCount() > 0;
}

function liveStartupState() {
  const liveCapture = state.liveCapture;
  if (!liveCapture || visibleLiveSegmentCount() > 0) {
    return null;
  }

  if (liveCapture.mode === "mac-system-audio") {
    if (liveCapture.awaitingAck || Number(state.session?.chunkCount || 0) > 0) {
      return {
        status: "Transcribing first text",
        summary: "The first Mac output chunk is in the transcription pipeline now.",
        detail: "Current Mac sound output is already flowing. The first transcript line appears after the first chunk finishes local transcription.",
      };
    }
    return {
      status: "Listening for audio",
      summary: "Waiting for the first usable Mac output turn before transcription starts.",
      detail: "Current Mac sound output capture is live. The first transcript line appears as soon as LocalScribe receives a usable chunk from the current output.",
    };
  }

  if (liveCapture.awaitingAck) {
    return {
      status: "Transcribing first text",
      summary: "The first startup chunk is being transcribed locally right now.",
      detail: "The startup chunk has already been sent. The first transcript line appears after this local transcription pass completes.",
    };
  }

  const bufferedSamples = Number(liveCapture.pendingSamples || 0);
  const targetSamples = Number(liveCapture.targetSamplesPerChunk || 0);
  if (bufferedSamples > 0 && targetSamples > 0) {
    const percent = Math.max(1, Math.min(99, Math.round((bufferedSamples / targetSamples) * 100)));
    return {
      status: "Buffering first chunk",
      summary: `Listening now. ${percent}% of the startup chunk is buffered before the first transcript pass begins.`,
      detail: "Recording is live. LocalScribe is filling a shorter startup chunk first so the first transcript line appears sooner.",
    };
  }

  return {
    status: "Listening for speech",
    summary: "Recording is live and waiting for the first usable speech chunk.",
    detail: "The microphone is already live. The first transcript line appears after LocalScribe buffers and transcribes the startup chunk.",
  };
}

function updateTranscriptTextFromDrafts() {
  if (!state.transcript) {
    return;
  }
  state.transcript.text = composeTranscriptText(state.transcript.segments || []);
  updateSessionChrome();
}

function clearSegmentSaveTimers() {
  Object.values(state.segmentSaveTimers).forEach((timer) => {
    window.clearTimeout(timer);
  });
  state.segmentSaveTimers = {};
}

async function flushPendingSegmentTextSaves() {
  const pendingEntries = Object.entries(state.segmentSaveTimers);
  if (pendingEntries.length === 0) {
    return;
  }

  pendingEntries.forEach(([, timer]) => {
    window.clearTimeout(timer);
  });
  state.segmentSaveTimers = {};

  const drafts = Object.entries(state.segmentDrafts);
  for (const [segmentId, draftText] of drafts) {
    const currentSegment = sessionSegmentById(segmentId);
    if (!currentSegment || currentSegment.text === draftText.trim()) {
      delete state.segmentDrafts[segmentId];
      continue;
    }
    await saveSegmentText(segmentId, draftText);
  }
}

function queueSegmentTextSave(segmentId, text) {
  if (state.segmentSaveTimers[segmentId]) {
    window.clearTimeout(state.segmentSaveTimers[segmentId]);
  }
  state.segmentSaveTimers[segmentId] = window.setTimeout(() => {
    delete state.segmentSaveTimers[segmentId];
    void saveSegmentText(segmentId, text);
  }, 450);
}

async function saveSegmentText(segmentId, text) {
  const sessionId = state.session?.sessionId;
  const normalized = (text || "").trim();
  if (!sessionId) {
    return;
  }
  if (!normalized) {
    delete state.segmentDrafts[segmentId];
    updateTranscriptTextFromDrafts();
    renderTranscript();
    return;
  }

  const currentSegment = sessionSegmentById(segmentId);
  if (currentSegment && currentSegment.text === normalized) {
    delete state.segmentDrafts[segmentId];
    updateTranscriptTextFromDrafts();
    return;
  }

  const response = await fetch(`/api/sessions/${sessionId}/segments/${segmentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: normalized }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    window.alert(data.detail || "Could not save the edited transcript segment.");
    return;
  }

  const currentDraft = state.segmentDrafts[segmentId];
  if (currentDraft === undefined || currentDraft.trim() === normalized) {
    delete state.segmentDrafts[segmentId];
  }
  state.session = data.session;
  setTranscriptFromSession();
  updateSessionChrome();
  renderTranscript();
}

function captureFocusedSegmentEditor() {
  const active = document.activeElement;
  if (!(active instanceof HTMLTextAreaElement) || !active.classList.contains("segment-editor")) {
    return null;
  }
  const segmentNode = active.closest(".segment");
  const segmentId = segmentNode?.dataset.segmentId;
  if (!segmentId) {
    return null;
  }
  return {
    segmentId,
    selectionStart: active.selectionStart,
    selectionEnd: active.selectionEnd,
  };
}

function restoreFocusedSegmentEditor(snapshot) {
  if (!snapshot) {
    return;
  }
  const editor = document.querySelector(`#segment-${CSS.escape(snapshot.segmentId)} .segment-editor`);
  if (!(editor instanceof HTMLTextAreaElement)) {
    return;
  }
  editor.focus({ preventScroll: true });
  editor.setSelectionRange(snapshot.selectionStart, snapshot.selectionEnd);
}

function autosizeTextarea(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.max(textarea.scrollHeight, 72)}px`;
}

function setTranscriptFromSession() {
  if (!state.session) {
    state.transcript = null;
    state.draftSessionId = null;
    clearSegmentSaveTimers();
    state.segmentDrafts = {};
    return;
  }
  if (state.draftSessionId !== state.session.sessionId) {
    clearSegmentSaveTimers();
    state.segmentDrafts = {};
    state.draftSessionId = state.session.sessionId;
  }
  const segments = [...(state.session.segments || []), ...(state.session.draftSegments || [])]
    .sort((left, right) => (left.start - right.start) || (left.end - right.end) || left.segmentId.localeCompare(right.segmentId));
  state.transcript = {
    text: composeTranscriptText(segments),
    segments,
    speakers: state.session.speakers,
    durationSeconds: state.session.totalAudioSeconds,
    warnings: state.session.warnings,
  };
}

function sessionIdentityParts(session = state.session) {
  const title = (session?.title || "").trim();
  const sessionId = session?.sessionId || "";
  const shortId = sessionId ? sessionId.slice(0, 8) : "";
  return { title, sessionId, shortId };
}

function currentSessionDisplayLabel({ session = state.session, fallback = "No session", shortIdOnly = false } = {}) {
  const { title, shortId } = sessionIdentityParts(session);
  if (title) {
    return title;
  }
  if (shortId) {
    return shortIdOnly ? shortId : `Session ${shortId}`;
  }
  return fallback;
}

function currentSessionReferenceLabel(session = state.session) {
  const { title, shortId } = sessionIdentityParts(session);
  if (title) {
    return `"${title}"`;
  }
  if (shortId) {
    return `Session ${shortId}`;
  }
  return "the live session";
}

function sessionHasWarning(fragment) {
  const normalizedFragment = (fragment || "").trim().toLowerCase();
  if (!normalizedFragment) {
    return false;
  }
  return (state.session?.warnings || []).some((warning) => warning.toLowerCase().includes(normalizedFragment));
}

function hasLowInputWarning() {
  return sessionHasWarning(LOW_INPUT_WARNING);
}

function hasSpeechDetectionWarning() {
  return sessionHasWarning(NO_SPEECH_WARNING) || sessionHasWarning(LIVE_FALLBACK_WARNING);
}

function sessionNeedsSourceAttention() {
  const chunkCount = Number(state.session?.chunkCount || 0);
  const segmentCount = Number(state.transcript?.segments?.length || 0);
  if (segmentCount > 0) {
    return false;
  }
  if (chunkCount < 3) {
    return false;
  }
  return hasLowInputWarning() || hasSpeechDetectionWarning();
}

function currentSourceAttentionCopy() {
  const chunkCount = Number(state.session?.chunkCount || 0);
  if (hasLowInputWarning()) {
    return {
      status: "Input too quiet",
      summary: state.liveCapture?.awaitingAck
        ? "The current chunk is still being checked, but the selected source is too quiet for reliable transcription."
        : "Check the selected microphone or audio source. LocalScribe is not hearing enough speech yet.",
      caption: `${currentSessionReferenceLabel()} is receiving very little usable audio.`,
      lead: "The current source is too quiet for reliable speech recognition. Fix the input level before expecting transcript segments.",
      hint: "The current source is too quiet for reliable transcription. Check the selected microphone or move closer before continuing.",
      emptyTitle: "Input is too quiet",
      emptyBody:
        "LocalScribe is receiving very little signal from the selected source. Check the microphone choice, permission, distance, or source audio routing before expecting transcript text.",
      helper:
        "The selected source is extremely quiet right now. Check microphone selection, browser microphone permission, or move closer to the mic.",
    };
  }
  return {
    status: "Check input",
    summary: state.liveCapture?.awaitingAck
      ? "The latest chunk is still being checked, but this session has not produced transcribable speech yet."
      : "Audio is arriving, but it is not turning into transcript text yet. Recheck the chosen source and speak more clearly into it.",
    caption: `${currentSessionReferenceLabel()} has streamed ${chunkCount} chunk${chunkCount === 1 ? "" : "s"} without transcript text yet.`,
    lead: "Audio is arriving, but the current source still has not produced transcriptable speech.",
    hint: "LocalScribe has checked multiple live chunks, but this source is still not producing transcript text. Recheck the microphone, source routing, or speaking distance.",
    emptyTitle: "Audio is arriving, but not as transcript",
    emptyBody:
      "LocalScribe has already checked multiple live chunks from this session, but none have turned into transcript text yet. Reconfirm the microphone choice, source routing, and speaking distance before continuing.",
    helper:
      `LocalScribe has already checked ${chunkCount} live chunk${chunkCount === 1 ? "" : "s"} without transcript text yet. Reconfirm microphone selection, browser permission, or source routing.`,
  };
}

function updateCurrentSessionPanel() {
  const session = state.session;
  const sessionId = session?.sessionId;
  const liveActive = Boolean(state.liveCapture);
  const liveFinishing = Boolean(state.liveCapture?.stopRequested);
  const savedTitle = (session?.title || "").trim();
  const input = els.currentSessionTitleInput;
  const saveButton = els.currentSessionTitleSave;

  if (!sessionId) {
    input.dataset.sessionId = "";
    input.value = "";
    input.placeholder = "Create a live session first";
    input.disabled = true;
    saveButton.disabled = true;
    els.currentSessionHeading.textContent = "No live session yet";
    els.currentSessionHint.textContent =
      "Create a session first, then give it a clear title so it stays easy to reopen and export later.";
    return;
  }

  const shouldResetInput = input.dataset.sessionId !== sessionId || document.activeElement !== input;
  if (shouldResetInput) {
    input.value = savedTitle;
  }
  input.dataset.sessionId = sessionId;
  input.placeholder = "Name this live session";
  input.disabled = false;

  const draftTitle = input.value.trim();
  const headingTitle = draftTitle || savedTitle || `Session ${sessionId.slice(0, 8)}`;
  els.currentSessionHeading.textContent = headingTitle;

  if (liveFinishing) {
    els.currentSessionHint.textContent =
      "The last buffered chunk is still finishing. You can still rename this session before reopening or exporting it.";
  } else if (liveActive) {
    els.currentSessionHint.textContent =
      "Rename this session while recording. The new title updates in history and in the transcript room immediately.";
  } else {
    els.currentSessionHint.textContent =
      "This session is ready for live capture. Give it a clear title now so it is easier to find after the conversation ends.";
  }

  saveButton.disabled = draftTitle === savedTitle;
}

async function saveCurrentSessionTitle() {
  const sessionId = state.session?.sessionId;
  if (!sessionId) {
    return;
  }
  await renameSession(sessionId, els.currentSessionTitleInput.value);
}

function renderTranscript() {
  _isRenderingTranscript = true;
  const transcript = state.transcript;
  const segments = transcript?.segments || [];
  const speakers = transcript?.speakers || [];
  const warnings = transcript?.warnings || [];
  const focusedEditor = captureFocusedSegmentEditor();
  const liveActive = Boolean(state.liveCapture);
  const liveFinishing = Boolean(state.liveCapture?.stopRequested);
  const hasSession = Boolean(state.session?.sessionId);
  const lowInput = hasLowInputWarning();
  const sourceAttention = sessionNeedsSourceAttention();
  const attentionCopy = sourceAttention ? currentSourceAttentionCopy() : null;
  const startupState = liveStartupState();

  els.modeValue.textContent = state.mode;
  els.durationValue.textContent = formatDuration(transcript?.durationSeconds || 0);
  els.segmentCountValue.textContent = String(segments.length);
  els.speakerCountValue.textContent = String(speakers.length);
  els.sessionIdPill.textContent = truncateText(currentSessionDisplayLabel(), 32);
  els.timelineLead.textContent = buildTimelineLead(segments.length);
  els.rosterLead.textContent =
    speakers.length > 0
      ? `${speakers.length} detected voice label${speakers.length === 1 ? "" : "s"} available for review and rename.`
      : "Known and inferred voices appear here. Rename any detected speaker and the transcript updates immediately.";
  const speakerMarkers = buildSpeakerMarkers(segments);
  els.markerLead.textContent =
    speakerMarkers.length > 0
      ? `${speakerMarkers.length} speaker change marker${speakerMarkers.length === 1 ? "" : "s"} detected in this session.`
      : "Each detected speaker change is listed here so you can jump through the conversation.";
  els.timelineHint.textContent =
    segments.length > 0
      ? segments.some((segment) => segment.isFinal === false)
        ? "All segments can be edited inline. Click into the live caption to lock your wording — new speech will continue in the next segment."
        : "Edit any finished segment inline. Your changes are saved back to the live session while new speech continues to arrive."
      : liveFinishing
        ? "LocalScribe is finishing the last buffered chunk now. Your transcript will settle here when it completes."
        : sourceAttention && attentionCopy
          ? attentionCopy.hint
          : startupState
            ? startupState.detail
          : liveActive
            ? state.liveCapture?.mode === "mac-system-audio"
              ? "Mac sound output capture is live. New text lands here as soon as LocalScribe finishes each detected turn."
              : "Recording is already live. The first text appears after the current short chunk finishes processing."
          : hasSession
            ? "This session is ready. Start the mic when you want transcript segments to begin appearing here."
            : "Create a live session to populate the live editor.";
  updateCurrentSessionPanel();

  els.warnings.replaceChildren();
  warnings.forEach((warning) => {
    const node = document.createElement("div");
    node.className = "warning";
    node.textContent = warning;
    els.warnings.append(node);
  });

  els.speakerRoster.replaceChildren();
  if (speakers.length === 0) {
    const node = document.createElement("div");
    node.className = "speaker-chip";
    node.innerHTML = "<strong>No speakers yet</strong><span>Detected speaker labels will appear here once the conversation starts.</span>";
    els.speakerRoster.append(node);
  } else {
    speakers.forEach((speaker) => {
      const node = document.createElement("div");
      node.className = "speaker-chip";
      const similarity = speaker.similarity
        ? `Match ${Math.round(speaker.similarity * 100)}%`
        : `${speaker.samples} sample${speaker.samples === 1 ? "" : "s"}`;
      const tag = speaker.enrolled ? "Enrolled voiceprint" : "Inferred from transcript";
      node.innerHTML = `
        <div class="speaker-chip-head">
          <strong>${escapeHtml(speaker.label)}</strong>
          <span>${similarity} · ${tag}</span>
        </div>
        <div class="speaker-chip-actions">
          <input
            class="speaker-label-input"
            id="speaker-label-${speaker.speakerId}"
            name="speaker-label-${speaker.speakerId}"
            type="text"
            value="${escapeHtmlAttribute(speaker.label)}"
            aria-label="Rename speaker"
          />
          <button type="button" class="secondary speaker-save-button">Rename</button>
        </div>
      `;
      const input = node.querySelector(".speaker-label-input");
      const button = node.querySelector(".speaker-save-button");
      button.addEventListener("click", () => {
        void renameSpeaker(speaker.speakerId, input.value);
      });
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          void renameSpeaker(speaker.speakerId, input.value);
        }
      });
      els.speakerRoster.append(node);
    });
  }

  renderSpeakerMarkers(speakerMarkers);

  els.timeline.replaceChildren();
  if (segments.length === 0) {
    const node = document.createElement("div");
    node.className = "empty-state";
    let emptyTitle = "No transcript yet";
    let emptyBody =
      "Use the live capture controls to start streaming audio into the local transcription pipeline. When segments arrive, you can edit them here live.";
    if (liveFinishing) {
      emptyTitle = "Finishing the last live chunk";
      emptyBody =
        "The microphone has stopped, but the final buffered audio is still being transcribed locally. The first segment will appear here as soon as that pass completes.";
    } else if (sourceAttention && attentionCopy) {
      emptyTitle = attentionCopy.emptyTitle;
      emptyBody = attentionCopy.emptyBody;
    } else if (startupState) {
      emptyTitle = startupState.status;
      emptyBody = startupState.detail;
    } else if (liveActive) {
      emptyTitle = "Listening for the first transcript";
      emptyBody = state.liveCapture?.mode === "mac-system-audio"
        ? "Mac sound output capture is already live. The first text will appear once LocalScribe hears a usable turn from the current Mac output."
        : "Recording is live right now. The first live caption appears once LocalScribe hears enough of the current turn to place a sentence or speaker boundary.";
    } else if (hasSession) {
      emptyTitle = "Session ready for live capture";
      emptyBody =
        "This session is armed and can be named now. Start the mic when you want the transcript editor to begin filling with live segments.";
    }
    node.innerHTML = `<strong>${escapeHtml(emptyTitle)}</strong><p>${escapeHtml(emptyBody)}</p>`;
    els.timeline.append(node);
    renderSessionHistory();
    _isRenderingTranscript = false;
    return;
  }

  segments.forEach((segment) => {
    const fragment = els.timelineItemTemplate.content.cloneNode(true);
    const article = fragment.querySelector(".segment");
    const editor = fragment.querySelector(".segment-editor");
    const stateNode = fragment.querySelector(".segment-state");
    article.dataset.segmentId = segment.segmentId;
    article.id = `segment-${segment.segmentId}`;
    article.classList.toggle("is-draft", segment.isFinal === false);
    article.querySelector(".segment-speaker").textContent = segment.speakerName || "Unassigned";
    stateNode.textContent = segment.isFinal === false ? "Live caption" : segment.manuallyEdited ? "Edited" : "Editable";
    article.querySelector(".segment-time").textContent = `${formatClock(segment.start)} - ${formatClock(segment.end)}`;
    editor.id = `segment-editor-${segment.segmentId}`;
    editor.name = `segment-editor-${segment.segmentId}`;
    editor.value = currentSegmentText(segment);
    editor.readOnly = false;
    editor.removeAttribute("aria-readonly");
    editor.title = segment.isFinal === false
      ? "Editing this live caption locks the current wording and pushes later speech into the next segment."
      : "Edits are saved back to this live session.";
    editor.addEventListener("input", () => {
      state.segmentDrafts[segment.segmentId] = editor.value;
      autosizeTextarea(editor);
      queueSegmentTextSave(segment.segmentId, editor.value);
      updateTranscriptTextFromDrafts();
    });
    editor.addEventListener("blur", () => {
      if (!_isRenderingTranscript) {
        void saveSegmentText(segment.segmentId, editor.value);
      }
    });
    editor.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        void saveSegmentText(segment.segmentId, editor.value);
      }
    });
    autosizeTextarea(editor);
    els.timeline.append(article);
  });

  restoreFocusedSegmentEditor(focusedEditor);
  renderSessionHistory();
  _isRenderingTranscript = false;
}

function renderSessionHistory() {
  const sessions = (state.sessions || []).filter((session) => session.sessionType !== "upload");
  els.sessionHistory.replaceChildren();
  els.clearHistoryButton.disabled = sessions.length === 0;

  if (sessions.length === 0) {
    const node = document.createElement("div");
    node.className = "empty-state empty-state-compact";
    node.innerHTML = "<strong>No live sessions yet</strong><p>Recorded live sessions with transcript content will appear here once capture begins.</p>";
    els.sessionHistory.append(node);
    return;
  }

  sessions.forEach((session) => {
    const article = document.createElement("article");
    article.className = "session-card";
    if (state.session?.sessionId === session.sessionId) {
      article.classList.add("is-active");
    }

    const typeLabel = "Live";
    article.innerHTML = `
      <div class="session-card-copy">
        <input
          class="session-title-input"
          id="session-title-${session.sessionId}"
          name="session-title-${session.sessionId}"
          type="text"
          value="${escapeHtmlAttribute(session.title || "")}"
          placeholder="Name this live session"
          aria-label="Session title"
        />
        <span>${typeLabel} · ${formatDuration(session.totalAudioSeconds || 0)} · ${session.segmentCount || 0} segments</span>
      </div>
      <div class="session-card-actions">
        <button type="button" class="ghost session-save-title">Save Name</button>
        <button type="button" class="secondary session-open">Open</button>
        <button type="button" class="ghost session-export">SRT</button>
      </div>
    `;

    const titleInput = article.querySelector(".session-title-input");
    const saveButton = article.querySelector(".session-save-title");
    saveButton.addEventListener("click", () => {
      void renameSession(session.sessionId, titleInput.value);
    });
    titleInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void renameSession(session.sessionId, titleInput.value);
      }
    });
    titleInput.addEventListener("blur", () => {
      void renameSession(session.sessionId, titleInput.value);
    });
    article.querySelector(".session-open").addEventListener("click", () => {
      void openSession(session.sessionId);
    });
    article.querySelector(".session-export").addEventListener("click", () => {
      void quickExport(session.sessionId, "srt");
    });
    els.sessionHistory.append(article);
  });
}

async function quickExport(sessionId, format) {
  await flushPendingSegmentTextSaves();
  els.exportFormatSelect.value = format;
  await downloadSessionExport(sessionId, format);
}

async function renameSession(sessionId, title) {
  const normalized = (title || "").trim();
  const currentSession = state.sessions.find((session) => session.sessionId === sessionId);
  const currentTitle = (currentSession?.title || (state.session?.sessionId === sessionId ? state.session.title : "") || "").trim();
  if (currentTitle === normalized) {
    updateCurrentSessionPanel();
    return;
  }

  const response = await fetch(`/api/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: normalized || null }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    window.alert(data.detail || "Could not rename the session.");
    return;
  }

  if (state.session?.sessionId === sessionId) {
    state.session = data.session;
    setTranscriptFromSession();
    updateSessionChrome();
  }
  await refreshSessionHistory();
  renderTranscript();
}

async function renameSpeaker(speakerId, label) {
  const sessionId = state.session?.sessionId;
  const normalized = (label || "").trim();
  if (!sessionId) {
    window.alert("Open a session first.");
    return;
  }
  if (!normalized) {
    window.alert("Speaker name cannot be empty.");
    return;
  }

  const response = await fetch(`/api/sessions/${sessionId}/speakers/${speakerId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: normalized }),
  });
  const data = await response.json();
  if (!response.ok) {
    window.alert(data.detail || "Could not rename the speaker.");
    return;
  }

  state.session = data.session;
  setTranscriptFromSession();
  updateSessionChrome();
  await refreshSessionHistory();
  renderTranscript();
}

async function clearLiveHistory() {
  if (state.liveCapture) {
    if (!window.confirm("Clear saved live history and keep the live session that is recording right now?")) {
      return;
    }
  } else if (!window.confirm("Delete all saved live sessions from LocalScribe history?")) {
    return;
  }

  const params = new URLSearchParams({ sessionType: "live" });
  if (state.liveCapture && state.session?.sessionId) {
    params.set("excludeSessionId", state.session.sessionId);
  }
  const response = await fetch(`/api/sessions?${params.toString()}`, { method: "DELETE" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    window.alert(data.detail || "Could not clear live session history.");
    return;
  }

  if (!state.liveCapture && state.session?.sessionType === "live") {
    state.session = null;
    setTranscriptFromSession();
    state.mode = "Waiting";
    updateSessionChrome();
  }

  await refreshSessionHistory();
  renderTranscript();
}

function buildSpeakerMarkers(segments) {
  const markers = [];
  let previousSpeakerId = null;
  segments.forEach((segment) => {
    const currentSpeakerId = segment.speakerId || segment.speakerName || "__unknown__";
    if (currentSpeakerId === previousSpeakerId) {
      return;
    }
    markers.push({
      segmentId: segment.segmentId,
      speakerName: segment.speakerName || "Unassigned",
      start: segment.start,
      text: currentSegmentText(segment),
    });
    previousSpeakerId = currentSpeakerId;
  });
  return markers;
}

function renderSpeakerMarkers(markers) {
  els.speakerMarkers.replaceChildren();
  if (markers.length === 0) {
    const node = document.createElement("div");
    node.className = "empty-state empty-state-compact";
    node.innerHTML = "<strong>No speaker changes yet</strong><p>Once multiple voices are detected, their changes will be listed here.</p>";
    els.speakerMarkers.append(node);
    return;
  }

  markers.forEach((marker, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "speaker-marker";
    button.innerHTML = `
      <span class="speaker-marker-index">${String(index + 1).padStart(2, "0")}</span>
      <span class="speaker-marker-copy">
        <strong>${escapeHtml(marker.speakerName)}</strong>
        <span>${formatClock(marker.start)} · ${escapeHtml(truncateText(marker.text, 72))}</span>
      </span>
    `;
    button.addEventListener("click", () => {
      jumpToSegment(marker.segmentId);
    });
    els.speakerMarkers.append(button);
  });
}

function jumpToSegment(segmentId) {
  const node = document.querySelector(`#segment-${CSS.escape(segmentId)}`);
  if (!node) {
    return;
  }
  node.scrollIntoView({ behavior: "smooth", block: "center" });
  node.classList.add("segment-highlight");
  window.setTimeout(() => {
    node.classList.remove("segment-highlight");
  }, 1400);
}

function updateSessionChrome() {
  const sessionId = state.session?.sessionId;
  const liveActive = Boolean(state.liveCapture);
  const liveFinishing = Boolean(state.liveCapture?.stopRequested);
  const sessionReference = currentSessionReferenceLabel();
  const sourceAttention = sessionNeedsSourceAttention();
  const attentionCopy = sourceAttention ? currentSourceAttentionCopy() : null;
  const startupState = liveStartupState();

  if (liveFinishing) {
    els.sessionStatusText.textContent = "Finishing live";
    els.sessionCaption.textContent = sessionId
      ? `${sessionReference} is sending the final buffered audio chunk.`
      : "Waiting for the final live audio chunk to finish transcribing.";
    els.liveSummary.textContent = "Wrapping up the last buffered audio chunk before capture closes.";
  } else if (liveActive && sourceAttention && attentionCopy) {
    els.sessionStatusText.textContent = attentionCopy.status;
    els.sessionCaption.textContent = sessionId ? attentionCopy.caption : attentionCopy.caption.replace(`${sessionReference} `, "");
    els.liveSummary.textContent = attentionCopy.summary;
  } else if (liveActive && startupState) {
    els.sessionStatusText.textContent = startupState.status;
    els.sessionCaption.textContent = sessionId
      ? `${sessionReference} is live. ${startupState.detail}`
      : startupState.detail;
    els.liveSummary.textContent = startupState.summary;
  } else if (liveActive) {
    const macOutputMode = state.liveCapture?.mode === "mac-system-audio";
    els.sessionStatusText.textContent = macOutputMode ? "Capturing Mac output" : "Recording live";
    els.sessionCaption.textContent = sessionId
      ? macOutputMode
        ? `${sessionReference} is receiving audio from the current Mac sound output.`
        : `${sessionReference} is streaming live audio.`
      : macOutputMode
        ? "A live session is capturing the current Mac sound output."
        : "A live session is actively recording.";
    els.liveSummary.textContent = macOutputMode
      ? "Current Mac sound output is flowing through the native helper. The transcript refreshes as each live turn lands."
      : state.liveCapture?.awaitingAck
        ? "Writing the latest live chunk now. Audio keeps buffering locally until it catches up."
        : "Microphone is live and streaming short chunks.";
  } else if (sessionId) {
    els.sessionStatusText.textContent = "Session ready";
    els.sessionCaption.textContent = `${sessionReference} is armed for live capture.`;
    els.liveSummary.textContent = "Start the mic from here or keep reviewing the current transcript.";
  } else {
    els.sessionStatusText.textContent = "Idle";
    els.sessionCaption.textContent = "Create a live session to begin.";
    els.liveSummary.textContent = "No session armed yet.";
  }

  els.helperNote.textContent = liveActive
    ? sourceAttention && attentionCopy
      ? `${attentionCopy.helper}${cleanupSessionNote()}`
      : startupState
        ? `${startupState.summary}${cleanupSessionNote()}`
      : `Audio is flowing. Live segment length is ${formatChunkMillis(configuredChunkMillis())} and changes apply without restarting.${cleanupSessionNote()}`
    : captureHelperText();
  els.downloadExportButton.disabled = !sessionId;
  els.copyTranscriptButton.disabled = !composeTranscriptText(state.transcript?.segments || []);
  updateCurrentSessionPanel();
  renderStarterLaunchState();
}

function updateCaptureUi() {
  const sourceMode = els.captureSource.value;
  const microphoneMode = sourceMode === "microphone";
  const entryPreset = currentEntryPreset();
  els.audioInputSelect.disabled = !microphoneMode;
  els.refreshInputsButton.disabled = !microphoneMode;
  els.startButton.textContent = entryPreset.actionLabel;
  els.helperNote.textContent = captureHelperText();
  renderSystemAudioPanel();
}

function renderChunkMillisControls() {
  const chunkMillis = configuredChunkMillis();
  els.chunkMillisValue.textContent = formatChunkMillis(chunkMillis);
  els.chunkMillisLiveHint.textContent = state.liveCapture ? "Updating live" : "Applies live";
}

async function handleChunkMillisChange({ immediate = false } = {}) {
  const chunkMillis = readChunkMillisInput();
  if (chunkMillis === null) {
    els.chunkMillis.value = String(configuredChunkMillis());
    renderChunkMillisControls();
    return;
  }

  els.chunkMillis.value = String(chunkMillis);
  if (state.liveCapture) {
    applyChunkMillisToLiveCapture(state.liveCapture, chunkMillis);
  }
  renderChunkMillisControls();
  updateSessionChrome();
  renderStarterPanel();
  void refreshSystemAudioStatus(false);

  queueChunkMillisPersist(chunkMillis, { immediate });
}

function queueChunkMillisPersist(chunkMillis, { immediate = false } = {}) {
  if (state.chunkMillisPersistTimer) {
    window.clearTimeout(state.chunkMillisPersistTimer);
    state.chunkMillisPersistTimer = 0;
  }

  const persist = async () => {
    try {
      await persistChunkMillisSetting(chunkMillis);
    } catch (error) {
      if (immediate) {
        window.alert(error.message || "Could not update the live segment length.");
      }
    }
  };

  if (immediate) {
    void persist();
    return;
  }

  state.chunkMillisPersistTimer = window.setTimeout(() => {
    state.chunkMillisPersistTimer = 0;
    void persist();
  }, 220);
}

function currentChunkMillisBounds() {
  const settings = state.status?.settings || {};
  const min = Number(settings.minChunkMillis);
  const max = Number(settings.maxChunkMillis);
  return {
    min: Number.isFinite(min) ? min : 800,
    max: Number.isFinite(max) ? max : 10000,
  };
}

function normalizeChunkMillis(value) {
  const { min, max } = currentChunkMillisBounds();
  const normalized = Math.round(value);
  return Math.max(min, Math.min(max, normalized));
}

function configuredChunkMillis() {
  const rawValue = Number(els.chunkMillis.value);
  if (Number.isFinite(rawValue)) {
    return normalizeChunkMillis(rawValue);
  }

  const serverValue = Number(state.status?.settings?.chunkMillis);
  if (Number.isFinite(serverValue)) {
    return normalizeChunkMillis(serverValue);
  }

  return 2200;
}

function readChunkMillisInput() {
  const rawValue = Number(els.chunkMillis.value);
  if (!Number.isFinite(rawValue)) {
    return null;
  }
  return normalizeChunkMillis(rawValue);
}

async function persistChunkMillisSetting(chunkMillis) {
  const requestToken = state.chunkMillisRequestToken + 1;
  state.chunkMillisRequestToken = requestToken;

  const response = await fetch("/api/settings/live", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chunkMillis }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Could not update the live segment length.");
  }
  if (requestToken !== state.chunkMillisRequestToken) {
    return;
  }

  state.status = {
    ...(state.status || {}),
    settings: data.settings,
  };
  els.chunkMillis.min = String(currentChunkMillisBounds().min);
  els.chunkMillis.max = String(currentChunkMillisBounds().max);
  els.chunkMillis.value = String(data.settings.chunkMillis);
  if (state.liveCapture) {
    applyChunkMillisToLiveCapture(state.liveCapture, data.settings.chunkMillis);
  }
  renderChunkMillisControls();
  updateSessionChrome();
  renderStarterPanel();
}

async function refreshAudioInputs(requestPermission) {
  if (!navigator.mediaDevices?.enumerateDevices) {
    return;
  }

  try {
    if (requestPermission) {
      const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      permissionStream.getTracks().forEach((track) => track.stop());
    }

    const previousValue = els.audioInputSelect.value;
    const devices = await navigator.mediaDevices.enumerateDevices();
    const inputs = devices.filter((device) => device.kind === "audioinput");

    els.audioInputSelect.replaceChildren();
    els.audioInputSelect.append(new Option("Default microphone", ""));
    inputs.forEach((device, index) => {
      const label = device.label || `Microphone ${index + 1}`;
      els.audioInputSelect.append(new Option(label, device.deviceId));
    });

    if ([...els.audioInputSelect.options].some((option) => option.value === previousValue)) {
      els.audioInputSelect.value = previousValue;
    }
  } catch (error) {
    console.warn("Could not refresh audio inputs.", error);
    els.audioInputSelect.replaceChildren();
    els.audioInputSelect.append(new Option("Default microphone", ""));
    if (requestPermission) {
      window.alert("Could not refresh microphone devices. You can still use the default microphone and start live capture.");
    }
  }
}

async function acquireCaptureStream(sourceMode) {
  if (sourceMode === "browser-audio") {
    if (!navigator.mediaDevices?.getDisplayMedia) {
      throw new Error(
        "Browser or screen audio capture is not available here. Use Safari or Edge for live microphone capture. For direct Mac output capture, switch to Current Mac sound output.",
      );
    }
    const rawStream = await navigator.mediaDevices.getDisplayMedia({
      audio: true,
      video: true,
    });
    const audioTracks = rawStream.getAudioTracks();
    if (audioTracks.length === 0) {
      rawStream.getTracks().forEach((track) => track.stop());
      throw new Error(
        "The selected screen share did not expose an audio track. In Edge or another Chromium browser, choose a tab or window with shared audio enabled. On Safari, use microphone mode or Current Mac sound output.",
      );
    }
    const recorderStream = new MediaStream(audioTracks);
    return { rawStream, recorderStream };
  }

  const deviceId = els.audioInputSelect.value;
  const audioConstraints = {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  if (deviceId) {
    audioConstraints.deviceId = { exact: deviceId };
  }
  const rawStream = await navigator.mediaDevices.getUserMedia({
    audio: audioConstraints,
    video: false,
  });
  await refreshAudioInputs(false);
  return { rawStream, recorderStream: rawStream };
}

function captureHelperText() {
  if (els.captureSource.value === "mac-system-audio") {
    const helper = state.systemAudio;
    if (helper?.running && helper.sessionId === state.session?.sessionId) {
      return "LocalScribe is using the native Mac sound helper for this session. Audio from the current Mac output is flowing directly into the transcript room.";
    }
    if (helper?.available) {
      return "Use Start Mac Output to capture whatever is playing through this Mac. LocalScribe will use the native ScreenCaptureKit helper instead of browser audio capture.";
    }
    return "LocalScribe can capture current Mac sound output, but the native helper needs to be built once first. The exact build command is shown below.";
  }
  if (els.captureSource.value === "browser-audio") {
    return "Browser or screen audio capture depends on browser support. Edge and other Chromium browsers are the best fit for tab audio. For direct Mac output capture, switch to Current Mac sound output.";
  }
  return `Choose a microphone input and let LocalScribe shape live turns around ${formatChunkMillis(configuredChunkMillis())} of rolling audio for the ${currentScenarioPreset().title.toLowerCase()} preset.${cleanupSessionNote()}`;
}

function cleanupSessionNote() {
  const backend = selectedCleanupBackendOption();
  const model = selectedCleanupModel();
  if (backend?.ready) {
    return model
      ? ` The AI assistant will use ${backend.label} with ${model} for the next turns.`
      : ` The AI assistant will use ${backend.label} for the next turns.`;
  }
  return ` The AI assistant layer is turned on, but ${backend?.label || "the selected engine"} is not ready yet.`;
}

function buildTimelineLead(segmentCount) {
  if (segmentCount > 0) {
    return "Live captions keep reshaping into finished turns as speakers pause, finish sentences, or interrupt one another.";
  }
  if (sessionNeedsSourceAttention()) {
    return currentSourceAttentionCopy().lead;
  }
  if (state.liveCapture?.stopRequested) {
    return "LocalScribe is finishing the last buffered live segment before this session closes.";
  }
  if (state.liveCapture) {
    return state.liveCapture.mode === "mac-system-audio"
      ? "Current Mac sound output is live. LocalScribe will place text here as soon as it hears a usable sentence or turn boundary."
      : "Recording is live. The first caption appears once LocalScribe hears a usable sentence or turn boundary.";
  }
  if (state.session?.sessionId) {
    return "This live session is ready. Start the microphone when you want the editor to begin filling.";
  }
  return "Start a live session to populate the live segment editor.";
}

async function startLiveAudioCapture(stream) {
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) {
    throw new Error("Web Audio is not available in this browser.");
  }

  const audioContext = new AudioContextCtor();
  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }

  const sourceNode = audioContext.createMediaStreamSource(stream);
  const channelCount = Math.min(sourceNode.channelCount || 1, 2);
  const processorNode = await createLiveCaptureProcessor(audioContext, channelCount);
  const muteGain = audioContext.createGain();
  muteGain.gain.value = 0;

  const liveCapture = {
    audioContext,
    sourceNode,
    processorNode,
    muteGain,
    pendingBuffers: [],
    pendingSamples: 0,
    desiredChunkMillis: configuredChunkMillis(),
    bootstrapMode: true,
    targetSamplesPerChunk: calculateTargetSamples(
      audioContext.sampleRate,
      Math.min(configuredChunkMillis(), LIVE_BOOTSTRAP_CHUNK_MILLIS),
    ),
    flushing: false,
    awaitingAck: false,
    stopRequested: false,
    inputStopped: false,
  };

  attachLiveCaptureProcessor(processorNode, liveCapture);

  sourceNode.connect(processorNode);
  processorNode.connect(muteGain);
  muteGain.connect(audioContext.destination);
  return liveCapture;
}

async function createLiveCaptureProcessor(audioContext, channelCount) {
  if (audioContext.audioWorklet && window.AudioWorkletNode) {
    await ensureCaptureWorklet(audioContext);
    return new AudioWorkletNode(audioContext, CAPTURE_WORKLET_NAME, {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      channelCount,
      channelCountMode: "explicit",
      channelInterpretation: "speakers",
    });
  }

  return audioContext.createScriptProcessor(4096, channelCount, 1);
}

async function ensureCaptureWorklet(audioContext) {
  if (_captureWorkletModuleUrl === null) {
    const source = `
      class LocalScribeCaptureProcessor extends AudioWorkletProcessor {
        process(inputs, outputs) {
          const input = inputs[0];
          const output = outputs[0];
          if (!input || input.length === 0) {
            return true;
          }

          const frameCount = input[0]?.length || 0;
          if (frameCount === 0) {
            return true;
          }

          const mono = new Float32Array(frameCount);
          let activeChannels = 0;
          for (let channelIndex = 0; channelIndex < input.length; channelIndex += 1) {
            const channel = input[channelIndex];
            if (!channel || channel.length === 0) {
              continue;
            }
            activeChannels += 1;
            for (let index = 0; index < frameCount; index += 1) {
              mono[index] += channel[index];
            }
          }

          if (activeChannels > 1) {
            for (let index = 0; index < frameCount; index += 1) {
              mono[index] /= activeChannels;
            }
          }

          if (output) {
            for (let channelIndex = 0; channelIndex < output.length; channelIndex += 1) {
              const outputChannel = output[channelIndex];
              const sourceChannel = input[Math.min(channelIndex, input.length - 1)] || input[0];
              outputChannel.set(sourceChannel || mono);
            }
          }

          this.port.postMessage(mono, [mono.buffer]);
          return true;
        }
      }

      registerProcessor("${CAPTURE_WORKLET_NAME}", LocalScribeCaptureProcessor);
    `;
    const blob = new Blob([source], { type: "application/javascript" });
    _captureWorkletModuleUrl = URL.createObjectURL(blob);
  }

  await audioContext.audioWorklet.addModule(_captureWorkletModuleUrl);
}

function attachLiveCaptureProcessor(processorNode, liveCapture) {
  if ("port" in processorNode && processorNode.port) {
    processorNode.port.onmessage = (event) => {
      if (!(event.data instanceof Float32Array)) {
        return;
      }
      handleLiveCaptureSamples(liveCapture, quietInputBoost(event.data));
    };
    return;
  }

  processorNode.onaudioprocess = (event) => {
    handleLiveCaptureSamples(liveCapture, quietInputBoost(mixToMono(event.inputBuffer)));
  };
}

function handleLiveCaptureSamples(liveCapture, monoSamples) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    return;
  }

  liveCapture.pendingBuffers.push(monoSamples);
  liveCapture.pendingSamples += monoSamples.length;
  if (liveCapture.pendingSamples >= liveCapture.targetSamplesPerChunk && !liveCapture.flushing) {
    void flushPendingAudioChunk(liveCapture, false);
  }
}

function calculateTargetSamples(sampleRate, chunkMillis) {
  return Math.max(4096, Math.round(sampleRate * chunkMillis / 1000));
}

function applyChunkMillisToLiveCapture(liveCapture, chunkMillis) {
  liveCapture.desiredChunkMillis = chunkMillis;
  const effectiveChunkMillis = liveCapture.bootstrapMode
    ? Math.min(chunkMillis, LIVE_BOOTSTRAP_CHUNK_MILLIS)
    : chunkMillis;
  liveCapture.targetSamplesPerChunk = calculateTargetSamples(liveCapture.audioContext.sampleRate, effectiveChunkMillis);
  if (
    !liveCapture.awaitingAck
    && liveCapture.pendingSamples >= liveCapture.targetSamplesPerChunk
    && !liveCapture.flushing
  ) {
    void flushPendingAudioChunk(liveCapture, false);
  }
}

function wsUrl(path) {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}${path}`;
}

async function stopAudioInput(liveCapture) {
  if (!liveCapture || liveCapture.inputStopped) {
    return;
  }

  liveCapture.inputStopped = true;
  if ("port" in liveCapture.processorNode && liveCapture.processorNode.port) {
    liveCapture.processorNode.port.onmessage = null;
  }
  if ("onaudioprocess" in liveCapture.processorNode) {
    liveCapture.processorNode.onaudioprocess = null;
  }
  liveCapture.sourceNode.disconnect();
  liveCapture.processorNode.disconnect();
  liveCapture.muteGain.disconnect();
  await liveCapture.audioContext.close();

  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
  }
  if (state.captureStream) {
    state.captureStream.getTracks().forEach((track) => track.stop());
    state.captureStream = null;
  }
}

async function finalizeStopMic() {
  const liveCapture = state.liveCapture;
  if (liveCapture?.pollTimer) {
    window.clearInterval(liveCapture.pollTimer);
  }
  state.liveCapture = null;
  if (state.socket) {
    const socket = state.socket;
    state.socket = null;
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "stop" }));
    }
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    }
  }
  els.livePill.textContent = "Idle";
  els.startButton.disabled = false;
  els.stopButton.disabled = true;
  updateInputLevelMeter(0);
  updateSessionChrome();
  renderSystemAudioPanel();
  await refreshSessionHistory();
}

async function abandonLiveCapture(message) {
  const socket = state.socket;
  const liveCapture = state.liveCapture;
  if (liveCapture?.pollTimer) {
    window.clearInterval(liveCapture.pollTimer);
  }
  if (liveCapture) {
    if (liveCapture.mode === "mac-system-audio") {
      try {
        await stopSystemAudioCapture();
      } catch (error) {
        console.warn("Could not stop native Mac sound capture.", error);
      }
    } else {
      await stopAudioInput(liveCapture);
    }
  }
  state.liveCapture = null;
  state.mediaStream = null;
  state.captureStream = null;
  state.socket = null;
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    socket.close();
  }
  els.livePill.textContent = "Idle";
  els.startButton.disabled = false;
  els.stopButton.disabled = true;
  updateInputLevelMeter(0);
  updateSessionChrome();
  renderSystemAudioPanel();
  if (message) {
    window.alert(message);
  }
}

async function flushPendingAudioChunk(liveCapture, force) {
  if (liveCapture.flushing) {
    return false;
  }
  if (liveCapture.awaitingAck) {
    return false;
  }
  if (!liveCapture.pendingSamples) {
    return false;
  }
  if (!force && liveCapture.pendingSamples < liveCapture.targetSamplesPerChunk) {
    return false;
  }
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    liveCapture.pendingBuffers = [];
    liveCapture.pendingSamples = 0;
    return false;
  }

  liveCapture.flushing = true;
  try {
    const merged = mergeFloat32Chunks(liveCapture.pendingBuffers, liveCapture.pendingSamples);
    liveCapture.pendingBuffers = [];
    liveCapture.pendingSamples = 0;
    const wavBuffer = encodeWav(merged, liveCapture.audioContext.sampleRate);
    const payload = arrayBufferToBase64(wavBuffer);
    liveCapture.awaitingAck = true;
    try {
      state.socket.send(
        JSON.stringify({
          type: "audio_chunk",
          sequence: state.sequence++,
          mimeType: "audio/wav",
          payload,
          language: els.languageInput.value.trim() || null,
          prompt: els.promptInput.value.trim() || null,
          diarize: els.diarizeToggle.checked,
          linkContext: ALWAYS_ENABLE_CONTEXT_LINKING,
          postProcess: shouldUsePostProcessingForLiveChunk(),
          postProcessBackend: selectedCleanupBackend(),
          postProcessModel: selectedCleanupModel(),
        }),
      );
    } catch (error) {
      liveCapture.awaitingAck = false;
      throw error;
    }
    updateSessionChrome();
    return true;
  } finally {
    liveCapture.flushing = false;
  }
}

function handleLiveChunkProcessed() {
  const liveCapture = state.liveCapture;
  if (!liveCapture) {
    return;
  }

  liveCapture.awaitingAck = false;
  if (liveCapture.bootstrapMode && visibleLiveSegmentCount() > 0) {
    liveCapture.bootstrapMode = false;
    applyChunkMillisToLiveCapture(liveCapture, liveCapture.desiredChunkMillis || configuredChunkMillis());
  }
  if (liveCapture.stopRequested) {
    if (liveCapture.pendingSamples > 0) {
      void flushPendingAudioChunk(liveCapture, true);
      return;
    }
    void finalizeStopMic();
    return;
  }

  if (liveCapture.pendingSamples >= liveCapture.targetSamplesPerChunk) {
    void flushPendingAudioChunk(liveCapture, false);
  }
  updateSessionChrome();
}

function mixToMono(inputBuffer) {
  const channelCount = inputBuffer.numberOfChannels || 1;
  const mono = new Float32Array(inputBuffer.length);
  for (let channel = 0; channel < channelCount; channel += 1) {
    const data = inputBuffer.getChannelData(channel);
    for (let index = 0; index < data.length; index += 1) {
      mono[index] += data[index] / channelCount;
    }
  }
  return mono;
}

function mergeFloat32Chunks(chunks, totalLength) {
  const merged = new Float32Array(totalLength);
  let offset = 0;
  chunks.forEach((chunk) => {
    merged.set(chunk, offset);
    offset += chunk.length;
  });
  return merged;
}

function encodeWav(samples, sampleRate) {
  const bytesPerSample = 2;
  const dataLength = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (let index = 0; index < samples.length; index += 1) {
    const value = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, value < 0 ? value * 0x8000 : value * 0x7fff, true);
    offset += bytesPerSample;
  }
  return buffer;
}

function writeAscii(view, offset, text) {
  for (let index = 0; index < text.length; index += 1) {
    view.setUint8(offset + index, text.charCodeAt(index));
  }
}

function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return window.btoa(binary);
}

function formatDuration(value) {
  const seconds = Math.max(0, Math.round(value));
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

function formatChunkMillis(value) {
  const chunkMillis = Math.max(0, Math.round(value));
  if (chunkMillis % 1000 === 0) {
    return `${chunkMillis / 1000}s`;
  }
  return `${(chunkMillis / 1000).toFixed(1)}s`;
}

function formatClock(value) {
  const seconds = Math.max(0, Math.floor(value));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeHtmlAttribute(value) {
  return escapeHtml(value);
}

function truncateText(value, maxLength) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1).trimEnd()}…`;
}

boot().catch((error) => {
  console.error(error);
  window.alert(error.message || "App failed to load.");
});
