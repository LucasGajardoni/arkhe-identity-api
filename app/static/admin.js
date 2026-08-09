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
  if (!res.ok) throw new Error(await res.text());
  return res.json();
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

async function refresh() {
  const [clients, identities] = await Promise.all([api("/admin/client-applications"), api("/admin/identities")]);
  document.querySelector("#clients").innerHTML = clients.map((client) => `<div class="item"><b>${client.name}</b><br>${client.slug}</div>`).join("");
  document.querySelector("#identities").innerHTML = identities
    .map((identity) => `<div class="item"><b>${identity.cpf_masked}</b><br>${identity.display_name || ""}<br>${identity.status}</div>`)
    .join("");
}
