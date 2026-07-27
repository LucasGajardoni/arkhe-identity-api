let selfie = "";

document.querySelectorAll("[data-mask='cpf']").forEach((input) => {
  input.addEventListener("input", () => {
    const d = input.value.replace(/\D/g, "").slice(0, 11);
    input.value = d.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  });
});

clientCam.onclick = async () => {
  clientVideo.srcObject = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
};

clientCapture.onclick = () => {
  clientCanvas.getContext("2d").drawImage(clientVideo, 0, 0, clientCanvas.width, clientCanvas.height);
  selfie = clientCanvas.toDataURL("image/jpeg", 0.9);
};

validateBtn.onclick = async () => {
  const form = Object.fromEntries(new FormData(validateForm).entries());
  const payload = {
    privacidade: { rfb: { id_template: "arkhe-template-v1" }, senatran: { token: "interno-opcional" } },
    cpf: form.cpf,
    validacao: {
      nome: form.nome,
      data_nascimento: form.data_nascimento,
      sexo: form.sexo,
      nacionalidade: Number(form.nacionalidade),
      nome_mae: form.nome_mae,
      nome_pai: form.nome_pai,
      rfb: { situacao_cpf: "regular" },
      documento: { tipo: 1, numero: form.documento, orgao_expedidor: form.orgao_expedidor, uf_expedidor: form.uf_expedidor },
    },
    biometria_facial: { imagem: selfie, vivacidade: false },
    tag: "cadastro-banco-arkhe",
  };
  const res = await fetch("/v5/pessoa-fisica/validacao", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Arkhe-Api-Key": form.api_key },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  cards.innerHTML = [
    ["Provedor", data.provedor || "indisponivel", true],
    ["Cadastro", data.regra_local?.cadastro_confirmado ?? "indisponivel", data.regra_local?.cadastro_confirmado],
    ["Face", data.regra_local?.face_confirmada ?? "indisponivel", data.regra_local?.face_confirmada],
  ].map(([k, v, ok]) => `<div class="card"><strong>${k}</strong><p class="${ok ? "ok" : "bad"}">${v}</p></div>`).join("");
  jsonOut.textContent = JSON.stringify(data, null, 2).replace(/data:image\/[^"]+/g, "[BASE64_REDACTED]");
};
