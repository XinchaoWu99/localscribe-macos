const state = {
  status: null,
  session: null,
  sessions: [],
  transcript: null,
  modelCatalog: null,
  postProcessCatalog: null,
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
  draftSessionId: null,
  segmentDrafts: {},
  segmentSaveTimers: {},
};

let _isRenderingTranscript = false;

const ALWAYS_ENABLE_CONTEXT_LINKING = true;
const ALWAYS_ENABLE_POST_PROCESSING = true;

const ENTRY_PRESETS = {
  microphone: {
    label: "Live microphone",
    summary: "Best for room conversations, calls, interviews, and meetings happening right now.",
    actionLabel: "Start Live Microphone",
    target: "live",
  },
  "browser-audio": {
    label: "Browser or system audio",
    summary: "Best for playback, livestreams, conference tabs, and other audio coming from the Mac.",
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
  starterPrimaryButton: document.querySelector("#starterPrimaryButton"),
  starterSecondaryButton: document.querySelector("#starterSecondaryButton"),
  starterModePill: document.querySelector("#starterModePill"),
  starterScenarioTitle: document.querySelector("#starterScenarioTitle"),
  starterScenarioSummary: document.querySelector("#starterScenarioSummary"),
  starterSegmentHint: document.querySelector("#starterSegmentHint"),
  starterSpeakerHint: document.querySelector("#starterSpeakerHint"),
  starterFocusHint: document.querySelector("#starterFocusHint"),
  starterPromptPreview: document.querySelector("#starterPromptPreview"),
  starterLaunchState: document.querySelector("#starterLaunchState"),
  starterActionHint: document.querySelector("#starterActionHint"),
  entryModeButtons: [...document.querySelectorAll("[data-entry-mode]")],
  scenarioButtons: [...document.querySelectorAll("[data-scenario]")],
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
  createSessionButton: document.querySelector("#createSessionButton"),
  startButton: document.querySelector("#startButton"),
  stopButton: document.querySelector("#stopButton"),
  livePill: document.querySelector("#livePill"),
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
  transcriptStage: document.querySelector(".transcript-stage"),
};

async function boot() {
  bindEvents();
  await refreshStatus();
  await refreshPostProcessCatalog();
  await refreshModelCatalog();
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
        applyScenarioPreset(scenarioId);
      }
    });
  });
  els.starterPrimaryButton.addEventListener("click", () => {
    void handleStarterPrimaryAction();
  });
  els.starterSecondaryButton.addEventListener("click", () => {
    handleStarterSecondaryAction();
  });
  els.createSessionButton.addEventListener("click", createSession);
  els.startButton.addEventListener("click", startMic);
  els.stopButton.addEventListener("click", stopMic);
  els.downloadExportButton.addEventListener("click", downloadExport);
  els.copyTranscriptButton.addEventListener("click", copyTranscript);
  els.clearHistoryButton.addEventListener("click", () => {
    void clearLiveHistory();
  });
  els.captureSource.addEventListener("change", () => {
    state.entryMode = els.captureSource.value;
    renderStarterPanel();
    updateCaptureUi();
  });
  els.chunkMillis.addEventListener("input", () => {
    void handleChunkMillisChange({ immediate: false });
  });
  els.chunkMillis.addEventListener("change", () => {
    void handleChunkMillisChange({ immediate: true });
  });
  els.modelSelect.addEventListener("change", renderModelControls);
  els.diarizeToggle.addEventListener("change", renderModelControls);
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
  applyScenarioPreset(state.scenarioId, { persist: false, scroll: false });
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
    scrollToWorkflowCard(els.liveWorkflowCard);
  }
}

function applyScenarioPreset(scenarioId, { persist = true, scroll = false } = {}) {
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

  if (persist) {
    void persistChunkMillisSetting(normalizeChunkMillis(preset.chunkMillis)).catch(() => {});
  }
  if (scroll) {
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
  els.starterPromptPreview.textContent = scenarioPreset.prompt;
  els.starterPrimaryButton.textContent = entryPreset.actionLabel;
  renderStarterLaunchState();
  els.liveWorkflowCard.classList.add("is-guided");
}

async function handleStarterPrimaryAction() {
  if (state.liveCapture) {
    scrollToWorkflowCard(els.transcriptStage);
    return;
  }
  await startMic();
  if (state.liveCapture) {
    scrollToWorkflowCard(els.transcriptStage);
  }
}

function handleStarterSecondaryAction() {
  if (state.liveCapture) {
    scrollToWorkflowCard(els.transcriptStage);
    return;
  }
  focusDialInControls();
}

function renderStarterLaunchState() {
  const entryPreset = currentEntryPreset();
  const sessionId = state.session?.sessionId;
  const liveActive = Boolean(state.liveCapture);
  const liveFinishing = Boolean(state.liveCapture?.stopRequested);
  const captureLabel = entryPreset.label.toLowerCase();

  if (liveFinishing) {
    els.starterLaunchState.textContent = "Finishing";
    els.starterActionHint.textContent =
      "The last buffered live segment is still being processed. The transcript will settle in place when it completes.";
    els.starterPrimaryButton.disabled = true;
    els.starterSecondaryButton.textContent = "View Transcript Room";
    return;
  }

  if (liveActive) {
    els.starterLaunchState.textContent = "Recording live";
    els.starterActionHint.textContent = `LocalScribe is already transcribing from ${captureLabel}. Stay here or jump straight to the transcript room.`;
    els.starterPrimaryButton.disabled = true;
    els.starterSecondaryButton.textContent = "View Transcript Room";
    return;
  }

  els.starterPrimaryButton.disabled = false;
  els.starterSecondaryButton.textContent = "Refine Live Setup";

  if (sessionId) {
    els.starterLaunchState.textContent = "Session ready";
    els.starterActionHint.textContent = `Session ${sessionId.slice(0, 8)} is armed. Start from here and LocalScribe will immediately open ${captureLabel}.`;
    return;
  }

  els.starterLaunchState.textContent = "Ready to start";
  els.starterActionHint.textContent = `Start from here and LocalScribe will create a live session, request permission, and begin transcription from ${captureLabel}.`;
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
  const engine = state.status.engine;
  const speaker = state.status.speakerRecognition;
  els.engineName.textContent = engine.engine;
  els.engineHint.textContent = engine.warnings?.[0] || "Local engine ready.";
  els.speakerState.textContent = speaker.ready ? "Ready" : "Limited";
  els.speakerHint.textContent = speaker.warning || "Speaker embedding pipeline ready.";
  els.chunkMillis.min = String(currentChunkMillisBounds().min);
  els.chunkMillis.max = String(currentChunkMillisBounds().max);
  els.chunkMillis.value = String(state.status.settings.chunkMillis);
  renderChunkMillisControls();
  renderPostProcessControls();
  renderModelControls();
  renderStarterPanel();
  updateSessionChrome();
  updateCaptureUi();
}

async function refreshPostProcessCatalog(showErrors = false) {
  try {
    const response = await fetch("/api/postprocess/catalog");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not load local cleanup engines.");
    }
    state.postProcessCatalog = data;
    syncCleanupBackendSelect();
    syncCleanupModelInput(true);
    renderPostProcessControls();
    renderModelControls();
  } catch (error) {
    if (showErrors) {
      window.alert(error.message || "Could not load local cleanup engines.");
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
  const backendName = backend?.label || "Local cleanup";
  const modelName = selectedCleanupModel();

  if (!catalog) {
    els.cleanupBackendSelect.disabled = true;
    els.cleanupModelInput.disabled = true;
    els.cleanupHint.textContent = "Checking which local cleanup engines are available on this Mac.";
    return;
  }

  els.cleanupBackendSelect.disabled = false;
  els.cleanupModelInput.disabled = false;

  if (backend?.ready) {
    els.cleanupHint.textContent = modelName
      ? `${backendName} is ready. New chunks will use ${modelName} for cleanup.`
      : `${backendName} is ready for the next live chunks.`;
    return;
  }

  const warning = backend?.warning ? ` ${backend.warning}` : "";
  els.cleanupHint.textContent = `${backendName} is not ready yet.${warning || ` ${backend?.description || ""}`}`.trim();
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
  const show = Boolean(install?.running || install?.warning || (install?.logTail && install.logTail.length));
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
    return `Local cleanup on (${backend.label})`;
  }
  return `Local cleanup pending (${backend?.label || selectedCleanupBackend()})`;
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

async function createSession() {
  await flushPendingSegmentTextSaves();
  const response = await fetch("/api/sessions", { method: "POST" });
  const data = await response.json();
  state.session = data.session;
  state.sequence = 1;
  state.mode = "Live";
  setTranscriptFromSession();
  updateSessionChrome();
  await refreshSessionHistory();
  renderTranscript();
}

async function startMic() {
  if (!navigator.mediaDevices?.getUserMedia) {
    window.alert("Audio capture is not supported in this browser.");
    return;
  }

  if (!state.session || state.session.sessionType === "upload") {
    await createSession();
  }

  try {
    await connectSocket();
    const sourceMode = els.captureSource.value;
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
    window.alert(error.message || "Could not start audio capture.");
  }
}

async function stopMic() {
  const liveCapture = state.liveCapture;
  if (!liveCapture) {
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
  renderTranscript();
}

function composeTranscriptText(segments) {
  return (segments || []).map((segment) => currentSegmentText(segment)).filter(Boolean).join("\n");
}

function currentSegmentText(segment) {
  return state.segmentDrafts[segment.segmentId] ?? segment.text ?? "";
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
    const currentSegment = (state.session?.segments || []).find((segment) => segment.segmentId === segmentId);
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

  const currentSegment = (state.session?.segments || []).find((segment) => segment.segmentId === segmentId);
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
  const segments = state.session.segments || [];
  state.transcript = {
    text: composeTranscriptText(segments),
    segments,
    speakers: state.session.speakers,
    durationSeconds: state.session.totalAudioSeconds,
    warnings: state.session.warnings,
  };
}

function renderTranscript() {
  _isRenderingTranscript = true;
  const transcript = state.transcript;
  const segments = transcript?.segments || [];
  const speakers = transcript?.speakers || [];
  const warnings = transcript?.warnings || [];
  const focusedEditor = captureFocusedSegmentEditor();

  els.modeValue.textContent = state.mode;
  els.durationValue.textContent = formatDuration(transcript?.durationSeconds || 0);
  els.segmentCountValue.textContent = String(segments.length);
  els.speakerCountValue.textContent = String(speakers.length);
  els.sessionIdPill.textContent = state.session?.sessionId ? state.session.sessionId.slice(0, 8) : "No session";
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
      ? "Edit any segment inline. Your changes are saved back to the live session while new chunks continue to arrive."
      : "Start a live session to populate the live editor.";

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
          <input class="speaker-label-input" type="text" value="${escapeHtmlAttribute(speaker.label)}" aria-label="Rename speaker" />
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
    node.innerHTML =
      "<strong>No transcript yet</strong><p>Use the live capture controls to start streaming audio into the local transcription pipeline. When segments arrive, you can edit them here live.</p>";
    els.timeline.append(node);
    renderSessionHistory();
    _isRenderingTranscript = false;
    return;
  }

  segments.forEach((segment) => {
    const fragment = els.timelineItemTemplate.content.cloneNode(true);
    const article = fragment.querySelector(".segment");
    const editor = fragment.querySelector(".segment-editor");
    article.dataset.segmentId = segment.segmentId;
    article.id = `segment-${segment.segmentId}`;
    article.querySelector(".segment-speaker").textContent = segment.speakerName || "Unassigned";
    article.querySelector(".segment-time").textContent = `${formatClock(segment.start)} - ${formatClock(segment.end)}`;
    editor.value = currentSegmentText(segment);
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
  if ((currentSession?.title || "") === normalized) {
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
  const segmentCount = state.transcript?.segments?.length || 0;

  if (liveFinishing) {
    els.sessionStatusText.textContent = "Finishing live";
    els.sessionCaption.textContent = sessionId
      ? `Session ${sessionId.slice(0, 8)} is sending the final buffered audio chunk.`
      : "Waiting for the final live audio chunk to finish transcribing.";
    els.liveSummary.textContent = "Live capture is draining the last buffered audio before closing.";
  } else if (liveActive) {
    els.sessionStatusText.textContent = "Recording live";
    els.sessionCaption.textContent = sessionId
      ? `Session ${sessionId.slice(0, 8)} is streaming microphone audio.`
      : "A live session is actively recording.";
    els.liveSummary.textContent = state.liveCapture?.awaitingAck
      ? "The backend is processing the latest chunk. Audio keeps buffering locally until it catches up."
      : "Microphone is live and streaming short chunks.";
  } else if (sessionId) {
    els.sessionStatusText.textContent = "Session ready";
    els.sessionCaption.textContent = `Session ${sessionId.slice(0, 8)} is armed for live capture.`;
    els.liveSummary.textContent = "You can start the mic or continue reviewing the latest transcript.";
  } else {
    els.sessionStatusText.textContent = "Idle";
    els.sessionCaption.textContent = "Create a live session to begin.";
    els.liveSummary.textContent = "No session armed yet.";
  }

  els.helperNote.textContent = liveActive
    ? `Audio is flowing. Live segment length is ${formatChunkMillis(configuredChunkMillis())} and changes apply without restarting.${cleanupSessionNote()}`
    : captureHelperText();
  els.downloadExportButton.disabled = !sessionId;
  els.copyTranscriptButton.disabled = !composeTranscriptText(state.transcript?.segments || []);
  renderStarterLaunchState();
}

function updateCaptureUi() {
  const sourceMode = els.captureSource.value;
  const microphoneMode = sourceMode === "microphone";
  els.audioInputSelect.disabled = !microphoneMode;
  els.refreshInputsButton.disabled = !microphoneMode;
  els.helperNote.textContent = captureHelperText();
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
        "Browser or screen audio capture is not available here. Safari is reliable for microphone capture; tab or system audio works better in Chromium-based browsers.",
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
        "The selected screen share did not expose an audio track. In Safari, use microphone mode. In Chromium browsers, choose a tab or window with shared audio enabled.",
      );
    }
    const recorderStream = new MediaStream(audioTracks);
    return { rawStream, recorderStream };
  }

  const deviceId = els.audioInputSelect.value;
  const rawStream = await navigator.mediaDevices.getUserMedia({
    audio: deviceId ? { deviceId: { exact: deviceId } } : true,
    video: false,
  });
  await refreshAudioInputs(false);
  return { rawStream, recorderStream: rawStream };
}

function captureHelperText() {
  if (els.captureSource.value === "browser-audio") {
    return "Browser or screen audio capture depends on browser support. Safari is best for microphone mode; Chromium browsers are better for tab audio.";
  }
  return `Choose a microphone input and stream ${formatChunkMillis(configuredChunkMillis())} chunks for live transcription with the ${currentScenarioPreset().title.toLowerCase()} preset.${cleanupSessionNote()}`;
}

function cleanupSessionNote() {
  const backend = selectedCleanupBackendOption();
  const model = selectedCleanupModel();
  if (backend?.ready) {
    return model
      ? ` Local cleanup will use ${backend.label} with ${model} for the next chunks.`
      : ` Local cleanup will use ${backend.label} for the next chunks.`;
  }
  return ` Local cleanup is turned on, but ${backend?.label || "the selected engine"} is not ready yet.`;
}

function buildTimelineLead(segmentCount) {
  if (segmentCount > 0) {
    return "Live conversation segments are arriving in sequence, and you can correct each one inline while the session continues.";
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
  const processorNode = audioContext.createScriptProcessor(4096, Math.min(sourceNode.channelCount || 1, 2), 1);
  const muteGain = audioContext.createGain();
  muteGain.gain.value = 0;

  const liveCapture = {
    audioContext,
    sourceNode,
    processorNode,
    muteGain,
    pendingBuffers: [],
    pendingSamples: 0,
    targetSamplesPerChunk: calculateTargetSamples(audioContext.sampleRate, configuredChunkMillis()),
    flushing: false,
    awaitingAck: false,
    stopRequested: false,
    inputStopped: false,
  };

  processorNode.onaudioprocess = (event) => {
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const monoSamples = mixToMono(event.inputBuffer);
    liveCapture.pendingBuffers.push(monoSamples);
    liveCapture.pendingSamples += monoSamples.length;
    if (liveCapture.pendingSamples >= liveCapture.targetSamplesPerChunk && !liveCapture.flushing) {
      void flushPendingAudioChunk(liveCapture, false);
    }
  };

  sourceNode.connect(processorNode);
  processorNode.connect(muteGain);
  muteGain.connect(audioContext.destination);
  return liveCapture;
}

function calculateTargetSamples(sampleRate, chunkMillis) {
  return Math.max(4096, Math.round(sampleRate * chunkMillis / 1000));
}

function applyChunkMillisToLiveCapture(liveCapture, chunkMillis) {
  liveCapture.targetSamplesPerChunk = calculateTargetSamples(liveCapture.audioContext.sampleRate, chunkMillis);
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
  liveCapture.processorNode.onaudioprocess = null;
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
  updateSessionChrome();
  await refreshSessionHistory();
}

async function abandonLiveCapture(message) {
  const socket = state.socket;
  const liveCapture = state.liveCapture;
  if (liveCapture) {
    await stopAudioInput(liveCapture);
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
  updateSessionChrome();
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
          postProcess: ALWAYS_ENABLE_POST_PROCESSING,
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
