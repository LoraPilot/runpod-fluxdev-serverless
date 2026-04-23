const state = {
  aspectRatio: "1:1",
  payload: null,
  payloadJson: "",
  activeResponseTab: "image",
};

const form = document.querySelector("#payload-form");
const promptField = document.querySelector("#prompt");
const numInferenceStepsField = document.querySelector("#num-inference-steps");
const guidanceScaleField = document.querySelector("#guidance-scale");
const seedField = document.querySelector("#seed");
const stepsValue = document.querySelector("#steps-value");
const guidanceValue = document.querySelector("#guidance-value");
const resolutionValue = document.querySelector("#resolution-value");
const stepsMinLabel = document.querySelector("#steps-min-label");
const stepsDefaultLabel = document.querySelector("#steps-default-label");
const stepsMaxLabel = document.querySelector("#steps-max-label");
const guidanceMinLabel = document.querySelector("#guidance-min-label");
const guidanceDefaultLabel = document.querySelector("#guidance-default-label");
const guidanceMaxLabel = document.querySelector("#guidance-max-label");
const charCount = document.querySelector("#char-count");
const feedback = document.querySelector("#feedback");
const payloadPanel = document.querySelector("#payload-panel");
const payloadOutput = document.querySelector("#payload-output");
const payloadSummary = document.querySelector("#payload-summary");
const generateButton = document.querySelector("#generate-button");
const copyButton = document.querySelector("#copy-button");
const downloadButton = document.querySelector("#download-button");
const endpointUrlField = document.querySelector("#endpoint-url");
const authTokenField = document.querySelector("#auth-token");
const responsePanel = document.querySelector("#response-panel");
const responseSummary = document.querySelector("#response-summary");
const responseStatus = document.querySelector("#response-status");
const responseMedia = document.querySelector("#response-media");
const responseOutput = document.querySelector("#response-output");
const generatedImage = document.querySelector("#generated-image");
const responseMediaTitle = document.querySelector("#response-media-title");
const openImageLink = document.querySelector("#open-image-link");
const saveImageLink = document.querySelector("#save-image-link");
const responseTabButtons = document.querySelectorAll("[data-response-tab]");
const responseImageView = document.querySelector("#response-image-view");
const responseJsonView = document.querySelector("#response-json-view");
const aspectButtons = document.querySelectorAll("[data-aspect-ratio]");

const aspectDimensions = {
  "1:1": { width: 1024, height: 1024 },
  "16:9": { width: 1344, height: 768 },
  "9:16": { width: 768, height: 1344 },
  "4:3": { width: 1152, height: 896 },
  "3:4": { width: 896, height: 1152 },
};

function setFeedback(message, type = "") {
  feedback.textContent = message;
  feedback.className = type ? `feedback ${type}` : "feedback";
}

function updatePromptCounter() {
  charCount.textContent = String(promptField.value.length);
}

function updateResolutionDisplay() {
  const dimensions = aspectDimensions[state.aspectRatio];
  resolutionValue.textContent = `${dimensions.width} × ${dimensions.height}`;
}

function positionRangeMarker(label, minValue, maxValue, markerValue) {
  const ratio = (markerValue - minValue) / (maxValue - minValue);
  label.style.left = `${Math.max(0, Math.min(100, ratio * 100))}%`;
}

function updateRangeMarkerPositions(config) {
  positionRangeMarker(
    stepsDefaultLabel,
    config.num_inference_steps.min,
    config.num_inference_steps.max,
    config.num_inference_steps.default
  );
  positionRangeMarker(
    guidanceDefaultLabel,
    config.guidance_scale.min,
    config.guidance_scale.max,
    config.guidance_scale.default
  );
}

function updateAspectButtons() {
  aspectButtons.forEach((button) => {
    const isActive = button.dataset.aspectRatio === state.aspectRatio;
    button.classList.toggle("aspect-button-active", isActive);
    button.setAttribute("aria-checked", String(isActive));
  });
}

function setActiveResponseTab(tabName) {
  state.activeResponseTab = tabName;

  responseTabButtons.forEach((button) => {
    const isActive = button.dataset.responseTab === tabName;
    button.classList.toggle("response-tab-active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });

  responseImageView.hidden = tabName !== "image";
  responseJsonView.hidden = tabName !== "json";
}

function renderSummary(summary) {
  const chips = [
    `${summary.width} × ${summary.height}`,
    `${summary.aspect_ratio}`,
    `${summary.num_inference_steps} steps`,
    `guidance: ${summary.guidance_scale}`,
    summary.seed ? `seed: ${summary.seed}` : "seed: random",
  ];

  payloadSummary.innerHTML = "";
  chips.forEach((text) => {
    const chip = document.createElement("span");
    chip.className = "payload-summary-chip";
    chip.textContent = text;
    payloadSummary.appendChild(chip);
  });
}

async function copyPayload() {
  if (!state.payloadJson) {
    return;
  }

  await navigator.clipboard.writeText(state.payloadJson);
  setFeedback("Payload copied.", "success");
}

function downloadPayload() {
  if (!state.payloadJson) {
    return;
  }

  const blob = new Blob([state.payloadJson], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "flux-payload.json";
  link.click();
  URL.revokeObjectURL(url);
}

function renderResponse(result) {
  const chips = [
    result.ok ? `HTTP ${result.status_code} ok` : `HTTP ${result.status_code}`,
    result.job_status || result.content_type,
    result.endpoint_url || "local API",
  ];

  responseSummary.innerHTML = "";
  chips.forEach((text) => {
    const chip = document.createElement("span");
    chip.className = "payload-summary-chip";
    chip.textContent = text;
    responseSummary.appendChild(chip);
  });

  responseOutput.textContent = result.response_json
    ? JSON.stringify(result.response_json, null, 2)
    : (result.response_text || "");

  const imageDataUrl = result.image_data_url;
  const metadata = result.metadata || {};
  if (imageDataUrl) {
    generatedImage.src = imageDataUrl;
    generatedImage.alt = metadata.seed
      ? `Generated image with seed ${metadata.seed}`
      : "Generated image";
    responseMediaTitle.textContent = metadata.seed
      ? `Generated image · seed ${metadata.seed}`
      : "Generated image";
    openImageLink.href = imageDataUrl;
    saveImageLink.href = imageDataUrl;
    saveImageLink.download = metadata.seed
      ? `flux-generated-${metadata.seed}.png`
      : "flux-generated.png";
    responseMedia.hidden = false;
    responseStatus.hidden = true;
    responseStatus.textContent = "";
    setActiveResponseTab("image");
  } else {
    generatedImage.removeAttribute("src");
    openImageLink.href = "#";
    saveImageLink.href = "#";
    responseMedia.hidden = true;
    responseStatus.hidden = false;
    responseStatus.textContent =
      result.error_message ||
      (result.job_status
        ? `Endpoint returned ${result.job_status}. Open the JSON tab for the raw response.`
        : "No image was returned. Open the JSON tab for the raw response.");
    setActiveResponseTab("json");
  }

  responsePanel.hidden = false;
}

async function initializeConfig() {
  const response = await fetch("/api/config");
  if (!response.ok) {
    throw new Error("Failed to load app configuration.");
  }

  const config = await response.json();
  numInferenceStepsField.min = String(config.num_inference_steps.min);
  numInferenceStepsField.max = String(config.num_inference_steps.max);
  numInferenceStepsField.value = String(config.num_inference_steps.default);
  stepsValue.textContent = String(config.num_inference_steps.default);
  stepsMinLabel.textContent = String(config.num_inference_steps.min);
  stepsDefaultLabel.textContent = String(config.num_inference_steps.default);
  stepsMaxLabel.textContent = String(config.num_inference_steps.max);

  guidanceScaleField.min = String(config.guidance_scale.min);
  guidanceScaleField.max = String(config.guidance_scale.max);
  guidanceScaleField.step = String(config.guidance_scale.step);
  guidanceScaleField.value = String(config.guidance_scale.default);
  guidanceValue.textContent = String(config.guidance_scale.default);
  guidanceMinLabel.textContent = String(config.guidance_scale.min);
  guidanceDefaultLabel.textContent = String(config.guidance_scale.default);
  guidanceMaxLabel.textContent = String(config.guidance_scale.max);

  updateResolutionDisplay();
  updateRangeMarkerPositions(config);
}

async function buildPayload() {
  if (!promptField.value.trim()) {
    setFeedback("Prompt is required.", "error");
    promptField.focus();
    return null;
  }

  const numInferenceSteps = Number.parseInt(numInferenceStepsField.value, 10);
  const guidanceScale = Number.parseFloat(guidanceScaleField.value);
  const rawSeed = seedField.value.trim();
  const parsedSeed = rawSeed ? Number.parseInt(rawSeed, 10) : 0;
  const seed = Number.isInteger(parsedSeed) && parsedSeed > 0 ? parsedSeed : 0;

  const response = await fetch("/api/payload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      prompt: promptField.value,
      aspect_ratio: state.aspectRatio,
      num_inference_steps: numInferenceSteps,
      guidance_scale: guidanceScale,
      seed,
    }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Failed to generate payload.");
  }

  state.payload = data.payload;
  state.payloadJson = JSON.stringify(data.payload, null, 2);
  payloadOutput.textContent = state.payloadJson;
  renderSummary(data.summary);
  payloadPanel.hidden = false;

  return data.payload;
}

async function submitPayload(payload) {
  const endpointUrl = endpointUrlField.value.trim();

  if (!endpointUrl) {
    setFeedback("Endpoint URL is required.", "error");
    endpointUrlField.focus();
    return null;
  }

  const response = await fetch("/api/submit", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      endpoint_url: endpointUrl,
      auth_token: authTokenField.value,
      payload,
    }),
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || "Submit failed.");
  }

  return result;
}

aspectButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.aspectRatio = button.dataset.aspectRatio;
    updateAspectButtons();
    updateResolutionDisplay();
  });
});

responseTabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setActiveResponseTab(button.dataset.responseTab);
  });
});

promptField.addEventListener("input", updatePromptCounter);
numInferenceStepsField.addEventListener("input", () => {
  stepsValue.textContent = numInferenceStepsField.value;
});
guidanceScaleField.addEventListener("input", () => {
  guidanceValue.textContent = guidanceScaleField.value;
});
copyButton.addEventListener("click", copyPayload);
downloadButton.addEventListener("click", downloadPayload);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  setFeedback("");
  generateButton.disabled = true;
  generateButton.textContent = "Generating...";

  try {
    const payload = await buildPayload();
    if (!payload) {
      return;
    }

    const result = await submitPayload(payload);
    renderResponse(result);
    responsePanel.scrollIntoView({ behavior: "smooth", block: "start" });

    setFeedback(
      result.ok
        ? "Image generated successfully."
        : (result.error_message || `Endpoint returned ${result.job_status || result.status_code}.`),
      result.ok ? "success" : "error"
    );
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    generateButton.disabled = false;
    generateButton.textContent = "Generate Image";
  }
});

updatePromptCounter();
updateAspectButtons();
setActiveResponseTab("image");
initializeConfig().catch((error) => {
  setFeedback(error.message, "error");
});
