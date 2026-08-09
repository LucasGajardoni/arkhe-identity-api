# Arkhe Identity API

API independente de identidade facial para cadastro e verificacao biometrica multi-tenant.

O projeto funciona como um servico de Face ID: uma aplicacao cliente cria uma sessao de cadastro ou verificacao no backend, entrega ao navegador apenas um `session_token` temporario, captura a imagem pelo scanner web e recebe o resultado sem expor `client_secret`, selfie, CPF completo ou embedding.

## Arquitetura

- FastAPI + Uvicorn
- SQLAlchemy 2 + Alembic
- PostgreSQL em producao
- SQLite apenas em testes automatizados
- AES-GCM para dados recuperaveis
- HMAC-SHA-256 para indices pesquisaveis de CPF e tokens
- OpenCV YuNet + SFace para deteccao e embeddings faciais locais
- Admin em `/admin`
- Scanner web generico em `/admin/scanner`

## Entidades principais

- `ClientApplication`: sistema cliente autorizado a criar sessoes.
- `Identity`: identidade cadastrada por cliente, com CPF normalizado, criptografado e mascarado nas respostas.
- `BiometricTemplate`: embedding facial criptografado e versionado.
- `EnrollmentSession`: sessao temporaria de cadastro facial.
- `VerificationSession`: sessao temporaria de verificacao facial.
- `VerificationAttempt`: tentativa individual com score e decisao.
- `AuditEvent`: trilha operacional sem payload sensivel.

## Variaveis

Use `.env.example` no ambiente local e `easypanel.env.example` no EasyPanel. Gere valores reais com:

```powershell
.\.venv\Scripts\python scripts\generate_secrets.py
```

Nunca use placeholders em producao.

## Rodar local

```powershell
cd C:\Users\Usuário\Documents\BANCO\arkhe-identity-api
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\scripts\download_face_models.ps1
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

URLs:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Admin: `http://localhost:8000/admin`
- Health: `http://localhost:8000/health`

## Fluxo de uso

1. O admin cria uma aplicacao cliente em `POST /admin/client-applications`.
2. O backend do cliente guarda `slug` e `client_secret`.
3. O backend do cliente cria uma sessao em `POST /v1/enrollments`.
4. O navegador usa apenas o `session_token` para enviar capturas.
5. Quando `ready=true`, o backend conclui com `POST /v1/enrollments/{session_id}/complete`.
6. Para autenticar depois, o backend cria `POST /v1/verifications` e envia a selfie em `/attempts`.

## SDK Web

O scanner reutilizavel fica em:

```html
<script src="https://SUA-API/static/sdk/face-identity.js"></script>
```

A pagina `/admin/scanner` e apenas uma demo/playground. Ela usa o SDK e nao duplica a logica de camera.

Arquitetura do SDK:

- `CameraController`: encapsula `getUserMedia`, preview, captura JPEG e encerramento da camera.
- `FaceIdentityTransport`: envia captures para a API com `Authorization: Bearer <sessionToken>`.
- `ScannerUI`: cria a interface visual padrao de scanner.
- `FaceIdentity.enroll()` e `FaceIdentity.verify()`: orquestram camera, transporte, UI, callbacks e erros.

Exemplo de cadastro em outro projeto:

```html
<div id="face-scan"></div>
<script src="https://SUA-API/static/sdk/face-identity.js"></script>
<script>
  FaceIdentity.enroll({
    sessionId: "uuid-da-sessao",
    sessionToken: "token-temporario",
    mount: document.querySelector("#face-scan"),
    autoComplete: true,
    onProgress(result) {
      console.log(result.coverage, result.next_hint, result.ready);
    },
    onSuccess(identity) {
      console.log(identity.identity_id, identity.cpf_masked);
    },
    onError(error) {
      console.error(error.code, error.message);
    }
  });
</script>
```

Exemplo de verificacao:

```js
FaceIdentity.verify({
  sessionId: "uuid-da-sessao",
  sessionToken: "token-temporario",
  mount: document.querySelector("#face-scan"),
  onProgress(result) {
    console.log(result.matched, result.similarity, result.threshold);
  },
  onSuccess(result) {
    console.log(result.status);
  },
  onError(error) {
    console.error(error);
  }
});
```

## Criar aplicacao cliente

```http
POST /admin/client-applications
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "name": "Portal do Cliente",
  "slug": "portal-cliente",
  "client_secret": "segredo-longo-gerado-pelo-backend-cliente",
  "allowed_origins": ["https://app.exemplo.local"]
}
```

A API nao devolve `client_secret`. Ela armazena apenas o hash do segredo recebido.

## Criar sessao de cadastro

```http
POST /v1/enrollments
X-Client-Id: portal-cliente
X-Client-Secret: <client-secret>
Content-Type: application/json

{
  "cpf": "52998224725",
  "external_user_id": "user-123",
  "display_name": "Pessoa Teste",
  "consent": {
    "accepted": true,
    "version": "terms-v1",
    "purpose": "Autenticacao facial"
  }
}
```

Resposta:

```json
{
  "session_id": "uuid",
  "session_token": "token-temporario",
  "expires_at": "2026-08-09T18:00:00Z",
  "scanner_url": "http://localhost:8000/admin/scanner?mode=enroll&session_id=uuid#token=token-temporario"
}
```

## Enviar captura

```http
POST /v1/enrollments/{session_id}/captures
Authorization: Bearer <session-token>
Content-Type: application/json

{
  "image_base64": "BASE64_DA_SELFIE"
}
```

Resposta:

```json
{
  "session_id": "uuid",
  "status": "ready",
  "coverage": {
    "frontal": 1.0,
    "left": 0.91,
    "right": 0.72,
    "up": 0.78,
    "down": 0.74
  },
  "quality_score": 0.72,
  "coverage_score": 0.68,
  "liveness_score": 0.83,
  "next_hint": "hold_still",
  "ready": true
}
```

## Enrollment adaptativo

O enrollment nao percorre uma lista fixa de poses. A cada captura valida, o backend atualiza `coverage` por regiao:

- `frontal`
- `left`
- `right`
- `up`
- `down`

O estado anterior e comparado com a estimativa da captura atual. Cada regiao guarda a melhor cobertura aceita ate o momento. O `coverage_score` e a media dessas regioes.

`next_hint` e sempre escolhido pela regiao mais deficiente:

- menor `left` -> `turn_left`
- menor `right` -> `turn_right`
- menor `up` -> `turn_up`
- menor `down` -> `turn_down`
- menor `frontal` -> `center_face`
- cobertura suficiente -> `complete`

`ready=true` depende dos criterios biometricos, nao de contador:

- cobertura minima por regiao: `0.65`
- media minima de coverage: `0.72`
- qualidade minima da melhor captura: `0.15`
- existencia de embedding valido

Observacao tecnica: a versao atual usa um estimador local limitado de pose/coverage a partir do frame. A arquitetura esta separada em `app/services/coverage.py` para trocar por um modelo real de landmarks/head pose sem mudar o contrato da API.

## Liveness

A implementacao atual de liveness e `PassiveLivenessService` (`passive-quality-v1`). Ela e deterministica e baseada em qualidade/face unica. Serve como ponto plugavel de arquitetura, mas nao e um modelo real de anti-spoofing e nao deve ser apresentada como protecao equivalente a Face ID da Apple.

Para producao, substitua esse servico por um provider real de anti-spoofing/liveness.

## Concluir cadastro

```http
POST /v1/enrollments/{session_id}/complete
Authorization: Bearer <session-token>
```

A resposta inclui `identity_id`, `biometric_template_id` e `cpf_masked`.

## Verificar identidade

```http
POST /v1/verifications
X-Client-Id: portal-cliente
X-Client-Secret: <client-secret>
Content-Type: application/json

{
  "identity_id": "uuid",
  "purpose": "login"
}
```

Depois envie a selfie:

```http
POST /v1/verifications/{session_id}/attempts
Authorization: Bearer <session-token>
Content-Type: application/json

{
  "image_base64": "BASE64_DA_SELFIE"
}
```

## Deploy EasyPanel

- Use o reposititorio GitHub como source.
- O EasyPanel usa o `Dockerfile` existente.
- Conecte um PostgreSQL.
- Configure as variaveis de `easypanel.env.example`.
- Sem comprar dominio, use o dominio gerado pelo EasyPanel, por exemplo `https://apps-arkhe-identity-api.<seu-host>.easypanel.host`.
- Health check recomendado: `GET /health`.
- Porta interna: `8000`.

## Seguranca

- `client_secret` e credenciais admin nunca devem ir para o navegador.
- CPF completo nao aparece em respostas; use `cpf_masked`.
- Selfies e embeddings nao aparecem em logs nem respostas.
- Tokens de sessao sao temporarios, hasheados no banco e separados por finalidade.
- O limiar facial padrao deve ser calibrado com dados consentidos antes de uso real.

## Verificacao local

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy app
.\.venv\Scripts\python -m pytest
```
