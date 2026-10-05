let token = "";

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(data.detail || data.mensagem || "Falha na requisicao.");
  }

  return data;
}

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  const result = await api("/admin/auth/login", { method: "POST", body: JSON.stringify(data) });
  token = result.access_token;
  await refresh();
});

document.querySelector("#client-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  const result = await api("/admin/client-applications", { method: "POST", body: JSON.stringify({ ...data, allowed_origins: [] }) });
  document.querySelector("#client-secret").textContent = JSON.stringify(result, null, 2);
  form.reset();
  await refresh();
});

async function resetarBiometria(identityId, nome) {
  const confirmado = window.confirm(`Resetar a biometria de ${nome || "esta pessoa"}? No proximo login sera necessario cadastrar o rosto novamente.`);

  if (!confirmado) return;

  try {
    await api(`/admin/identities/${identityId}/biometric-template`, { method: "DELETE" });
    window.alert("Biometria resetada com sucesso.");
    await refresh();
  } catch (erro) {
    window.alert(erro.message || "Nao foi possivel resetar a biometria.");
  }
}

async function refresh() {
  const [clients, identities] = await Promise.all([api("/admin/client-applications"), api("/admin/identities")]);

  document.querySelector("#clients").innerHTML = clients
    .map((client) => `<div class="item"><b>${client.name}</b><br>${client.slug}</div>`)
    .join("");

  document.querySelector("#identities").innerHTML = identities
    .map((identity) => {
      const nome = identity.display_name || "";
      const statusBiometria = identity.has_biometric_template ? "Biometria cadastrada" : "Sem biometria";
      const botao = identity.has_biometric_template
        ? `<button class="danger" type="button" data-reset-biometria="${identity.id}" data-nome="${nome.replaceAll('"', '&quot;')}">Resetar biometria</button>`
        : "";

      return `
        <div class="item identity-item">
          <div>
            <b>${identity.cpf_masked}</b><br>
            ${nome}<br>
            <span>${statusBiometria}</span>
          </div>
          ${botao}
        </div>
      `;
    })
    .join("");

  document.querySelectorAll("[data-reset-biometria]").forEach((botao) => {
    botao.addEventListener("click", () => resetarBiometria(botao.dataset.resetBiometria, botao.dataset.nome));
  });
}
