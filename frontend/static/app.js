const state = {
  aspectRatio: "1:1",
  payload: null,
  payloadJson: "",
};

const form = document.querySelector("#payload-form");
const promptField = document.querySelector("#prompt");
const widthField = document.querySelector("#width");
const heightField = document.querySelector("#height");
const numInferenceStepsField = document.querySelector("#num-inference-steps");
const guidanceScaleField = document.querySelector("#guidance-scale");
const seedField = document.querySelector("#seed");
const stepsValue = document.querySelector("#steps-value");
const guidanceValue = document.querySelector("#guidance-value");
const resolutionValue = document.querySelector("#resolution-value");
const charCount = document.querySelector("#char-count");
const feedback = document.querySelector("#feedback");
const payloadPanel = document.querySelector("#payload-panel");
const payloadOutput = document.querySelector("#payload-output");
const payloadSummary = document.querySelector("#payload-summary");
const generateButton = document.querySelector("#generate-button");
const submitButton = document.querySelector("#submit-button");
const copyButton = document.querySelector("#copy-button");
const downloadButton = document.querySelector("#download-button");
const endpointPanel = document.querySelector("#endpoint-panel");
const endpointUrlField = document.querySelector("#endpoint-url");
const authTokenField = document.querySelector("#auth-token");
const submitModeTitle = document.querySelector("#submit-mode-title");
const submitModeCopy = document.querySelector("#submit-mode-copy");
const helperCopy = document.querySelector("#helper-copy");
const responsePanel = document.querySelector("#response-panel");
const responseSummary = document.querySelector("#response-summary");
const responseStatus = document.querySelector("#response-status");
const responseMedia = document.querySelector("#response-media");
const responseOutput = document.querySelector("#response-output");
const generatedImage = document.querySelector("#generated-image");
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

function updateAspectButtons() {
  aspectButtons.forEach((button) => {
    const isActive = button.dataset.aspectRatio === state.aspectRatio;
    button.classList.toggle("aspect-button-active", isActive);
    button.setAttribute("aria-checked", String(isActive));
  });
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
    result.content_type,
    result.endpoint_url || "local API",
  ];

  responseSummary.innerHTML = "";
  chips.forEach((text) => {
    const chip = document.createElement("span");
    chip.className = "payload-summary-chip";
    chip.textContent = text;
    responseSummary.appendChild(chip);
  });

  responseStatus.hidden = true;
  responseStatus.textContent = "";
  responseMedia.hidden = true;
  responseOutput.hidden = false;
  responseOutput.textContent = result.response_json
    ? JSON.stringify(result.response_json, null, 2)
    : (result.response_text || "");

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

  guidanceScaleField.min = String(config.guidance_scale.min);
  guidanceScaleField.max = String(config.guidance_scale.max);
  guidanceScaleField.step = String(config.guidance_scale.step);
  guidanceScaleField.value = String(config.guidance_scale.default);
  guidanceValue.textContent = String(config.guidance_scale.default);

  updateResolutionDisplay();
}

async function buildPayload({
  scroll = true,
  showPreview = true,
  successMessage = "Payload ready.",
} = {}) {
  if (!promptField.value.trim()) {
    setFeedback("Prompt is required.", "error");
    promptField.focus();
    return null;
  }

  const dimensions = aspectDimensions[state.aspectRatio];
  const width = dimensions.width;
  const height = dimensions.height;
  const numInferenceSteps = Number.parseInt(numInferenceStepsField.value, 10);
  const guidanceScale = Number.parseFloat(guidanceScaleField.value);
  const seed = Number.parseInt(seedField.value, 10) || 0;

  const response = await fetch("/api/payload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      prompt: promptField.value,
      width,
      height,
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
  payloadPanel.hidden = !showPreview;
  if (scroll && showPreview) {
    payloadPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (successMessage) {
    setFeedback(successMessage, "success");
  }
  return data.payload;
}

aspectButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.aspectRatio = button.dataset.aspectRatio;
    updateAspectButtons();
    updateResolutionDisplay();
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
    await buildPayload();
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    generateButton.disabled = false;
    generateButton.textContent = "Generate Image";
  }
});

submitButton.addEventListener("click", async () => {
  setFeedback("");

  const endpointUrl = endpointUrlField.value.trim();

  if (!endpointUrl) {
    setFeedback("Endpoint URL is required before submit.", "error");
    endpointUrlField.focus();
    return;
  }

  submitButton.disabled = true;
  submitButton.textContent = "Submitting...";

  try {
    const payload = await buildPayload({
      scroll: false,
      showPreview: true,
      successMessage: "Payload refreshed for submit.",
    });
    if (!payload) {
      return;
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

    renderResponse(result);
    responsePanel.scrollIntoView({ behavior: "smooth", block: "start" });

    setFeedback(
      result.ok
        ? `Submitted successfully. Endpoint returned HTTP ${result.status_code}.`
        : `Submitted. Endpoint returned HTTP ${result.status_code}.`,
      result.ok ? "success" : "error"
    );
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    submitButton.disabled = false;
  }
});

updatePromptCounter();
updateAspectButtons();
initializeConfig().catch((error) => {
  setFeedback(error.message, "error");
});
