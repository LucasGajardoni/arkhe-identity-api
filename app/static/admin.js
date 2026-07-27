let token = "";
let capturedData = "";

const asJson = (form) => {
  const data = Object.fromEntries(new FormData(form).entries());
  for (const key of Object.keys(data)) {
    if (data[key] === "") data[key] = null;
  }
  return data;
};
const authHeaders = () => ({ Authorization: `Bearer ${token}`, "Content-Type": "application/json" });

document.querySelectorAll("[data-mask='cpf']").forEach((input) => {
  input.addEventListener("input", () => {
    const d = input.value.replace(/\D/g, "").slice(0, 11);
    input.value = d.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  });
});

document.querySelectorAll("[data-mask='phone']").forEach((input) => {
  input.addEventListener("input", () => {
    const d = input.value.replace(/\D/g, "").slice(0, 11);
    input.value = d.replace(/^(\d{2})(\d)/, "($1) $2").replace(/(\d{5})(\d)/, "$1-$2");
  });
});

loginBtn.onclick = async () => {
  const res = await fetch("/admin/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: loginUser.value, password: loginPass.value }),
  });
  const data = await res.json();
  token = data.access_token || "";
  personOut.value = token ? "Autenticado." : JSON.stringify(data);
};

savePerson.onclick = async () => {
  const payload = asJson(personForm);
  payload.consentimento = {
    consentimento_aceito: consent.checked,
    versao_termo: "arkhe-consent-v1",
    finalidade: "Prova de conceito academica privada Banco Arkhe",
  };
  const res = await fetch("/admin/pessoas", { method: "POST", headers: authHeaders(), body: JSON.stringify(payload) });
  personOut.value = JSON.stringify(await res.json(), null, 2);
};

saveDoc.onclick = async () => {
  const payload = asJson(docForm);
  const id = payload.person_id;
  delete payload.person_id;
  const res = await fetch(`/admin/pessoas/${id}/documentos`, { method: "POST", headers: authHeaders(), body: JSON.stringify(payload) });
  personOut.value = JSON.stringify(await res.json(), null, 2);
};

startCam.onclick = async () => {
  video.srcObject = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
};

capture.onclick = () => {
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  capturedData = canvas.toDataURL("image/jpeg", 0.9);
};

saveFace.onclick = async () => {
  const form = new FormData();
  if (faceUpload.files[0]) form.append("imagem", faceUpload.files[0]);
  else form.append("imagem_base64", capturedData);
  const res = await fetch(`/admin/pessoas/${facePersonId.value}/referencia-facial`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  faceOut.value = JSON.stringify(await res.json(), null, 2);
};

refreshPeople.onclick = async () => {
  const res = await fetch("/admin/pessoas", { headers: { Authorization: `Bearer ${token}` } });
  const people = await res.json();
  peopleBody.innerHTML = people.map((p) => `<tr><td>${p.cpf_mascarado}</td><td>${p.nome}</td><td>${p.status}</td><td>${p.possui_biometria}</td><td>${p.id}</td></tr>`).join("");
};
