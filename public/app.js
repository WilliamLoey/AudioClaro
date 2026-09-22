"use strict";

const form = document.querySelector("#validation-form");
const steps = [...document.querySelectorAll(".form-step")];
const previousButton = document.querySelector("#previous");
const nextButton = document.querySelector("#next");
const saveButton = document.querySelector("#save");
const progressBar = document.querySelector("#progress-bar");
const progressValue = document.querySelector("#progress-value");
const stepName = document.querySelector("#step-name");
const formError = document.querySelector("#form-error");
const saveStatus = document.querySelector("#save-status");
const resultRows = document.querySelector("#result-rows");
const adminTokenInput = document.querySelector("#admin-token");
const adminStatus = document.querySelector("#admin-status");
const adminTable = document.querySelector("#admin-table");
const exportButton = document.querySelector("#export-csv");
const connectionStatus = document.querySelector("#connection-status");
const connectionBadge = document.querySelector(".api-status");
let currentStep = 1;

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
}

async function apiFetch(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    throw new Error(body?.error || "Não foi possível concluir a operação.");
  }
  return { response, body };
}

function updateStep() {
  steps.forEach((step, index) => {
    const active = index + 1 === currentStep;
    step.hidden = !active;
    step.classList.toggle("active", active);
  });
  const percent = Math.round((currentStep / steps.length) * 100);
  progressBar.style.width = `${percent}%`;
  progressValue.textContent = `${percent}%`;
  stepName.textContent = `Etapa ${currentStep} de ${steps.length}`;
  previousButton.hidden = currentStep === 1;
  nextButton.hidden = currentStep === steps.length;
  saveButton.hidden = currentStep !== steps.length;
  formError.hidden = true;
}

function validateCurrentStep() {
  const fields = [...steps[currentStep - 1].querySelectorAll("input, select, textarea")];
  const invalid = fields.find((field) => !field.checkValidity());
  if (!invalid) return true;
  formError.textContent = "Preencha os campos obrigatórios desta etapa antes de continuar.";
  formError.hidden = false;
  invalid.reportValidity();
  invalid.focus();
  return false;
}

function formPayload() {
  const data = Object.fromEntries(new FormData(form));
  data.consent = data.consent === "true";
  return data;
}

async function submitValidation(payload) {
  const { body } = await apiFetch("/api/responses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  await loadStats();
  return body;
}

nextButton.addEventListener("click", () => {
  if (!validateCurrentStep()) return;
  currentStep += 1;
  updateStep();
  form.scrollIntoView({ behavior: "smooth", block: "start" });
});

previousButton.addEventListener("click", () => {
  currentStep -= 1;
  updateStep();
  form.scrollIntoView({ behavior: "smooth", block: "start" });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateCurrentStep()) return;
  saveButton.disabled = true;
  saveButton.textContent = "Salvando...";
  saveStatus.textContent = "";
  try {
    await submitValidation(formPayload());
    form.reset();
    currentStep = 1;
    updateStep();
    saveStatus.textContent = "Validação salva com sucesso no banco de dados.";
    document.querySelector("#resultados").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    formError.textContent = error.message;
    formError.hidden = false;
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "Salvar validação";
  }
});

async function loadStats() {
  try {
    const { body } = await apiFetch("/api/stats");
    document.querySelector("#metric-total").textContent = body.total;
    document.querySelector("#metric-problem").textContent = `${body.problem_percent}%`;
    document.querySelector("#metric-preference").textContent = `${body.preference_percent}%`;
    document.querySelector("#metric-action").textContent = `${body.action_percent}%`;
    connectionStatus.textContent = "Banco conectado";
    connectionBadge.classList.add("connected");
    connectionBadge.classList.remove("error");
    return body;
  } catch (error) {
    connectionStatus.textContent = "Banco indisponível";
    connectionBadge.classList.add("error");
    connectionBadge.classList.remove("connected");
    throw error;
  }
}

function adminHeaders() {
  return { "X-Admin-Token": adminTokenInput.value.trim() };
}

function renderResponses(items) {
  if (!items.length) {
    resultRows.innerHTML = '<tr class="empty-row"><td colspan="7">Nenhuma validação salva.</td></tr>';
    return;
  }
  resultRows.innerHTML = items.map((record) => `
    <tr>
      <td>${escapeHtml(record.participant_code)}</td>
      <td>${escapeHtml(record.activity)}</td>
      <td>${escapeHtml(record.audios_per_day)}</td>
      <td>${escapeHtml(record.preference)}</td>
      <td>${escapeHtml(record.second_action)}</td>
      <td>${escapeHtml(record.confidence)}</td>
      <td><button class="icon-button" type="button" data-delete="${escapeHtml(record.id)}" aria-label="Excluir resposta de ${escapeHtml(record.participant_code)}">Excluir</button></td>
    </tr>`).join("");
}

async function loadAdminResponses() {
  adminStatus.textContent = "Carregando respostas...";
  try {
    const { body } = await apiFetch("/api/responses", { headers: adminHeaders() });
    renderResponses(body.items);
    adminTable.hidden = false;
    exportButton.disabled = false;
    adminStatus.textContent = `${body.total} resposta(s) disponível(is).`;
    sessionStorage.setItem("audioclaro_admin_token", adminTokenInput.value.trim());
  } catch (error) {
    adminTable.hidden = true;
    exportButton.disabled = true;
    adminStatus.textContent = error.message;
  }
}

document.querySelector("#load-admin").addEventListener("click", loadAdminResponses);

resultRows.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete]");
  if (!button) return;
  if (!window.confirm("Excluir esta resposta permanentemente?")) return;
  button.disabled = true;
  try {
    await apiFetch(`/api/responses/${encodeURIComponent(button.dataset.delete)}`, {
      method: "DELETE",
      headers: adminHeaders()
    });
    await Promise.all([loadAdminResponses(), loadStats()]);
  } catch (error) {
    adminStatus.textContent = error.message;
    button.disabled = false;
  }
});

exportButton.addEventListener("click", async () => {
  exportButton.disabled = true;
  try {
    const response = await fetch("/api/export.csv", { headers: adminHeaders() });
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.error || "Não foi possível exportar o CSV.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `audioclaro-validacoes-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    adminStatus.textContent = "CSV exportado com sucesso.";
  } catch (error) {
    adminStatus.textContent = error.message;
  } finally {
    exportButton.disabled = false;
  }
});

function registerWebMcpTools() {
  const context = document.modelContext;
  if (!context?.registerTool) return;

  Promise.resolve(context.registerTool({
    name: "get_audioclaro_public_stats",
    title: "Consultar indicadores do AudioClaro",
    description: "Retorna somente os indicadores agregados e públicos da validação do AudioClaro.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, untrustedContentHint: false },
    async execute() {
      return await loadStats();
    }
  })).catch(() => {});

  Promise.resolve(context.registerTool({
    name: "submit_audioclaro_validation",
    title: "Registrar validação do AudioClaro",
    description: "Registra uma entrevista de validação depois que a pessoa confirmou o consentimento e que nenhum dado sensível foi incluído.",
    inputSchema: {
      type: "object",
      properties: {
        participant_code: { type: "string", maxLength: 12 },
        activity: { type: "string", maxLength: 80 },
        audios_per_day: { type: "string", enum: ["0 a 2", "3 a 5", "6 a 10", "Mais de 10"] },
        recent_episode: { type: "string", maxLength: 900 },
        impact: { type: "string", maxLength: 900 },
        preference: { type: "string", enum: ["sim", "nao", "depende"] },
        feedback: { type: "string", maxLength: 900 },
        second_action: { type: "string", enum: ["sim", "nao"] },
        confidence: { type: "string", enum: ["sim", "nao", "depende"] },
        concern: { type: "string", maxLength: 900 },
        notes: { type: "string", maxLength: 900 },
        consent: { type: "boolean", const: true }
      },
      required: ["participant_code", "activity", "audios_per_day", "recent_episode", "impact", "preference", "feedback", "second_action", "confidence", "concern", "consent"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, untrustedContentHint: true },
    async execute(input) {
      const result = await submitValidation({ ...input, notes: input.notes || "", website: "" });
      return { id: result.id, status: result.status };
    }
  })).catch(() => {});
}

adminTokenInput.value = sessionStorage.getItem("audioclaro_admin_token") || "";
updateStep();
loadStats().catch(() => {});
registerWebMcpTools();

