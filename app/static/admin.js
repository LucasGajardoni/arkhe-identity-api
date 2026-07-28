"use strict";

const state = {
  token: null,
  selectedPerson: null,
  currentStep: 1,
  capturedImage: null,
  uploadedFile: null,
  cameraStream: null,
  people: [],
  documentSaved: false,
  faceSaved: false,
};

const byId = (id) => document.getElementById(id);
const elements = {
  authStatus: byId("authStatus"),
  workspace: byId("workspace"),
  peoplePanel: byId("peoplePanel"),
  loginUser: byId("loginUser"),
  loginPass: byId("loginPass"),
  loginMessage: byId("loginMessage"),
  personForm: byId("personForm"),
  consent: byId("consent"),
  personMessage: byId("personMessage"),
  docForm: byId("docForm"),
  docType: byId("docType"),
  docNumberLabel: byId("docNumberLabel"),
  docMessage: byId("docMessage"),
  faceMessage: byId("faceMessage"),
  faceUpload: byId("faceUpload"),
  video: byId("video"),
  canvas: byId("canvas"),
  imagePreview: byId("imagePreview"),
  emptyPreview: byId("emptyPreview"),
  cameraArea: byId("cameraArea"),
  uploadArea: byId("uploadArea"),
  cameraMode: byId("cameraMode"),
  uploadMode: byId("uploadMode"),
  peopleBody: byId("peopleBody"),
  peopleSearch: byId("peopleSearch"),
  peopleMessage: byId("peopleMessage"),
  selectedPersonCard: byId("selectedPersonCard"),
  technicalOutput: byId("technicalOutput"),
};

const setMessage = (element, message, kind = "") => {
  element.textContent = message;
  element.className = `message ${kind}`.trim();
};

const showTechnical = (data) => {
  elements.technicalOutput.textContent = JSON.stringify(data, null, 2);
};

const asJson = (form, visibleOnly = false) => {
  const payload = {};
  for (const field of form.elements) {
    if (!field.name || field.disabled || (visibleOnly && field.closest("[hidden]"))) continue;
    if (field.type === "checkbox") payload[field.name] = field.checked;
    else payload[field.name] = field.value === "" ? null : field.value;
  }
  return payload;
};

const errorMessage = (data, fallback) => {
  if (typeof data?.detail === "string") return data.detail;
  if (typeof data?.message === "string") return data.message;
  if (Array.isArray(data?.detail)) return data.detail.map((item) => item.msg).join(" ");
  return fallback;
};

const apiFetch = async (url, options = {}) => {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  const response = await fetch(url, { ...options, headers });
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  showTechnical(data);
  if (response.status === 401 || response.status === 403) {
    state.token = null;
    elements.workspace.hidden = true;
    elements.peoplePanel.hidden = true;
    elements.authStatus.textContent = "Acesso expirado";
    setMessage(elements.loginMessage, "Seu acesso expirou. Faça login novamente.", "error");
  }
  return { response, data };
};

const stopCamera = () => {
  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach((track) => track.stop());
    state.cameraStream = null;
  }
  elements.video.srcObject = null;
};

const updateSelectedPerson = () => {
  const person = state.selectedPerson;
  elements.selectedPersonCard.hidden = !person;
  if (!person) return;
  byId("selectedName").textContent = person.nome || "Pessoa sem nome";
  byId("selectedDetails").textContent = `${person.cpf_mascarado || "CPF indisponível"} · ${person.status || "ativo"}`;
  byId("selectedId").textContent = `UUID: ${person.id}`;
};

const renderSummary = () => {
  const person = state.selectedPerson || {};
  byId("summaryName").textContent = person.nome || "—";
  byId("summaryCpf").textContent = person.cpf_mascarado || "—";
  byId("summaryStatus").textContent = person.status || "Ativo";
  byId("summaryDocument").textContent = state.documentSaved ? "Associado com sucesso" : "Não adicionado";
  byId("summaryFace").textContent = state.faceSaved ? "Cadastrada com sucesso" : "Não cadastrada";
  byId("summaryId").textContent = person.id || "—";
};

const goToStep = (step) => {
  if (step > 1 && !state.selectedPerson) {
    setMessage(elements.personMessage, "Selecione ou cadastre uma pessoa antes de continuar.", "error");
    step = 1;
  }
  if (state.currentStep === 3 && step !== 3) stopCamera();
  state.currentStep = step;
  document.querySelectorAll("[data-step-panel]").forEach((panel) => {
    const active = Number(panel.dataset.stepPanel) === step;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  document.querySelectorAll(".step").forEach((button) => {
    const buttonStep = Number(button.dataset.step);
    button.disabled = buttonStep > 1 && !state.selectedPerson;
    button.classList.toggle("active", buttonStep === step);
    button.classList.toggle("complete", buttonStep < step);
  });
  if (step === 4) renderSummary();
  window.scrollTo({ top: 0, behavior: "smooth" });
};

const resetImage = () => {
  stopCamera();
  state.capturedImage = null;
  state.uploadedFile = null;
  elements.faceUpload.value = "";
  elements.canvas.hidden = true;
  elements.imagePreview.hidden = true;
  elements.imagePreview.removeAttribute("src");
  elements.emptyPreview.hidden = false;
};

const resetFlow = () => {
  state.selectedPerson = null;
  state.documentSaved = false;
  state.faceSaved = false;
  elements.personForm.reset();
  elements.docForm.reset();
  elements.consent.checked = false;
  resetImage();
  updateSelectedPerson();
  updateDocumentFields();
  [elements.personMessage, elements.docMessage, elements.faceMessage].forEach((item) => setMessage(item, ""));
  goToStep(1);
};

const selectPerson = (person, step = 2) => {
  state.selectedPerson = person;
  state.documentSaved = false;
  state.faceSaved = Boolean(person.possui_biometria);
  resetImage();
  updateSelectedPerson();
  goToStep(step);
};

const documentFields = {
  RG: ["numero", "orgao_expedidor", "uf_expedidor", "data_emissao", "principal"],
  CIN: ["numero", "orgao_expedidor", "uf_expedidor", "data_emissao", "data_validade", "principal"],
  CNH: ["numero", "orgao_expedidor", "uf_expedidor", "data_emissao", "data_validade", "principal"],
  PASSAPORTE: ["numero", "orgao_expedidor", "pais_emissor", "data_emissao", "data_validade", "principal"],
  CRNM: ["numero", "orgao_expedidor", "pais_emissor", "data_emissao", "data_validade", "principal"],
  OUTRO: ["numero", "orgao_expedidor", "uf_expedidor", "pais_emissor", "data_emissao", "data_validade", "principal"],
};

function updateDocumentFields() {
  const type = elements.docType.value;
  const visible = new Set(documentFields[type]);
  document.querySelectorAll("[data-doc-field]").forEach((wrapper) => {
    const show = visible.has(wrapper.dataset.docField);
    wrapper.hidden = !show;
    if (!show) {
      wrapper.querySelectorAll("input, select").forEach((field) => {
        if (field.type === "checkbox") field.checked = false;
        else field.value = "";
      });
    }
  });
  const principal = elements.docForm.elements.principal;
  if (principal && visible.has("principal") && !principal.checked) principal.checked = true;
  const country = elements.docForm.elements.pais_emissor;
  if (visible.has("pais_emissor") && !country.value) country.value = "BR";
  elements.docNumberLabel.textContent =
    type === "CNH" ? "Número de registro" : type === "CIN" ? "Número (CPF)" : "Número";
}

const renderPeople = () => {
  const query = elements.peopleSearch.value.trim().toLocaleLowerCase("pt-BR");
  const filtered = state.people.filter((person) =>
    [person.nome, person.cpf_mascarado, person.id].some((value) =>
      String(value || "").toLocaleLowerCase("pt-BR").includes(query)
    )
  );
  elements.peopleBody.replaceChildren();
  filtered.forEach((person) => {
    const row = document.createElement("tr");
    if (state.selectedPerson?.id === person.id) row.classList.add("selected-row");
    const values = [
      person.cpf_mascarado,
      person.nome,
      person.status,
      person.possui_biometria ? "Cadastrada" : "Pendente",
      person.id,
    ];
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value || "—";
      row.appendChild(cell);
    });
    const actionCell = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "table-action";
    button.textContent = state.selectedPerson?.id === person.id ? "Selecionada" : "Selecionar";
    button.addEventListener("click", () => {
      selectPerson(person);
      renderPeople();
    });
    actionCell.appendChild(button);
    row.appendChild(actionCell);
    row.addEventListener("dblclick", () => {
      selectPerson(person);
      renderPeople();
    });
    elements.peopleBody.appendChild(row);
  });
  setMessage(
    elements.peopleMessage,
    filtered.length ? `${filtered.length} pessoa(s) exibida(s).` : "Nenhuma pessoa encontrada.",
    ""
  );
};

const loadPeople = async () => {
  const { response, data } = await apiFetch("/admin/pessoas");
  if (!response.ok) {
    setMessage(elements.peopleMessage, errorMessage(data, "Não foi possível carregar as pessoas."), "error");
    return;
  }
  state.people = Array.isArray(data) ? data : [];
  renderPeople();
};

byId("loginBtn").addEventListener("click", async () => {
  setMessage(elements.loginMessage, "Entrando...", "loading");
  const { response, data } = await apiFetch("/admin/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: elements.loginUser.value, password: elements.loginPass.value }),
  });
  if (!response.ok || !data.access_token) {
    setMessage(elements.loginMessage, errorMessage(data, "Não foi possível entrar. Verifique suas credenciais."), "error");
    return;
  }
  state.token = data.access_token;
  elements.authStatus.textContent = "Autenticado";
  elements.authStatus.classList.add("success");
  elements.workspace.hidden = false;
  elements.peoplePanel.hidden = false;
  setMessage(elements.loginMessage, "Login realizado com sucesso.", "success");
  await loadPeople();
});

elements.loginPass.addEventListener("keydown", (event) => {
  if (event.key === "Enter") byId("loginBtn").click();
});

byId("savePerson").addEventListener("click", async () => {
  if (!elements.personForm.reportValidity()) return;
  if (!elements.consent.checked) {
    setMessage(elements.personMessage, "Aceite o termo de consentimento para continuar.", "error");
    return;
  }
  const payload = asJson(elements.personForm);
  payload.consentimento = {
    consentimento_aceito: true,
    versao_termo: "arkhe-consent-v1",
    finalidade: "Prova de conceito academica privada Banco Arkhe",
  };
  setMessage(elements.personMessage, "Cadastrando pessoa...", "loading");
  const { response, data } = await apiFetch("/admin/pessoas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    setMessage(elements.personMessage, errorMessage(data, "Não foi possível cadastrar a pessoa."), "error");
    return;
  }
  selectPerson({ ...data, status: "ativo", possui_biometria: false }, 2);
  setMessage(elements.docMessage, "Pessoa cadastrada com sucesso. Adicione o documento.", "success");
  await loadPeople();
});

byId("saveDoc").addEventListener("click", async () => {
  if (!state.selectedPerson) {
    setMessage(elements.docMessage, "Selecione ou cadastre uma pessoa antes de continuar.", "error");
    return;
  }
  if (!elements.docForm.reportValidity()) return;
  const payload = asJson(elements.docForm, true);
  setMessage(elements.docMessage, "Associando documento...", "loading");
  const { response, data } = await apiFetch(
    `/admin/pessoas/${encodeURIComponent(state.selectedPerson.id)}/documentos`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    setMessage(elements.docMessage, errorMessage(data, "Não foi possível associar o documento."), "error");
    return;
  }
  state.documentSaved = true;
  goToStep(3);
  setMessage(elements.faceMessage, "Documento associado com sucesso. Cadastre a referência facial.", "success");
});

const setFaceMode = (mode) => {
  const camera = mode === "camera";
  elements.cameraArea.hidden = !camera;
  elements.uploadArea.hidden = camera;
  elements.cameraMode.classList.toggle("active", camera);
  elements.uploadMode.classList.toggle("active", !camera);
  if (!camera) stopCamera();
};

elements.cameraMode.addEventListener("click", () => setFaceMode("camera"));
elements.uploadMode.addEventListener("click", () => setFaceMode("upload"));

byId("startCam").addEventListener("click", async () => {
  stopCamera();
  if (!navigator.mediaDevices?.getUserMedia) {
    setMessage(elements.faceMessage, "Não foi possível acessar a câmera. Use o envio de imagem.", "error");
    return;
  }
  try {
    state.cameraStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    elements.video.srcObject = state.cameraStream;
    await elements.video.play();
    setMessage(elements.faceMessage, "Câmera aberta. Posicione o rosto e capture a foto.", "success");
  } catch {
    setMessage(elements.faceMessage, "Não foi possível acessar a câmera. Verifique a permissão ou envie uma imagem.", "error");
  }
});

byId("capture").addEventListener("click", () => {
  if (!state.cameraStream || elements.video.readyState < 2) {
    setMessage(elements.faceMessage, "Abra a câmera antes de capturar a foto.", "error");
    return;
  }
  const context = elements.canvas.getContext("2d");
  context.drawImage(elements.video, 0, 0, elements.canvas.width, elements.canvas.height);
  state.capturedImage = elements.canvas.toDataURL("image/jpeg", 0.9);
  state.uploadedFile = null;
  elements.faceUpload.value = "";
  elements.canvas.hidden = false;
  elements.imagePreview.hidden = true;
  elements.emptyPreview.hidden = true;
  stopCamera();
  setMessage(elements.faceMessage, "Foto capturada. Confira a prévia antes de enviar.", "success");
});

elements.faceUpload.addEventListener("change", () => {
  const file = elements.faceUpload.files[0] || null;
  state.uploadedFile = file;
  state.capturedImage = null;
  elements.canvas.hidden = true;
  if (!file) {
    elements.imagePreview.hidden = true;
    elements.emptyPreview.hidden = false;
    return;
  }
  elements.imagePreview.src = URL.createObjectURL(file);
  elements.imagePreview.onload = () => URL.revokeObjectURL(elements.imagePreview.src);
  elements.imagePreview.hidden = false;
  elements.emptyPreview.hidden = true;
  setMessage(elements.faceMessage, "Imagem selecionada. Confira a prévia antes de enviar.", "success");
});

byId("saveFace").addEventListener("click", async () => {
  if (!state.selectedPerson) {
    setMessage(elements.faceMessage, "Selecione ou cadastre uma pessoa antes de continuar.", "error");
    return;
  }
  if (!state.uploadedFile && !state.capturedImage) {
    setMessage(elements.faceMessage, "Escolha uma imagem ou capture uma foto.", "error");
    return;
  }
  const form = new FormData();
  if (state.uploadedFile) form.append("imagem", state.uploadedFile);
  else form.append("imagem_base64", state.capturedImage);
  setMessage(elements.faceMessage, "Enviando referência facial...", "loading");
  const { response, data } = await apiFetch(
    `/admin/pessoas/${encodeURIComponent(state.selectedPerson.id)}/referencia-facial`,
    { method: "POST", body: form }
  );
  if (!response.ok) {
    setMessage(elements.faceMessage, errorMessage(data, "Não foi possível cadastrar a referência facial."), "error");
    return;
  }
  state.faceSaved = true;
  state.selectedPerson.possui_biometria = true;
  stopCamera();
  goToStep(4);
  await loadPeople();
});

elements.docType.addEventListener("change", updateDocumentFields);
elements.peopleSearch.addEventListener("input", renderPeople);
byId("refreshPeople").addEventListener("click", loadPeople);
byId("newRegistration").addEventListener("click", resetFlow);
byId("finishRegistration").addEventListener("click", resetFlow);
byId("cancelSelection").addEventListener("click", () => {
  resetFlow();
  renderPeople();
});

document.querySelectorAll("[data-go-step]").forEach((button) => {
  button.addEventListener("click", () => goToStep(Number(button.dataset.goStep)));
});
document.querySelectorAll(".step").forEach((button) => {
  button.addEventListener("click", () => goToStep(Number(button.dataset.step)));
});

document.querySelectorAll("[data-mask='cpf']").forEach((input) => {
  input.addEventListener("input", () => {
    const digits = input.value.replace(/\D/g, "").slice(0, 11);
    input.value = digits
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  });
});

window.addEventListener("beforeunload", stopCamera);
updateDocumentFields();
goToStep(1);
