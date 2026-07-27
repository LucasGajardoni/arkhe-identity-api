# Arkhe Identity API

Provedor interno, privado e academico de validacao de identidade para o TCC do Banco Arkhe.

Frase correta para apresentar o resultado:

> Os dados e a biometria foram comparados com a base privada previamente cadastrada no ambiente Banco Arkhe.

Este projeto nao consulta Receita Federal, Senatran, Renach ou qualquer base governamental. Ele nao prova existencia oficial de uma pessoa, nao implementa prova de vida e nao substitui o Datavalid oficial.

## Arquitetura

- FastAPI + Uvicorn
- SQLAlchemy 2 + Alembic
- PostgreSQL em desenvolvimento/producao
- SQLite somente em testes automatizados
- AES-GCM para dados recuperaveis
- HMAC-SHA-256 para indices pesquisaveis de CPF/documento
- OpenCV YuNet + SFace para deteccao e embeddings faciais locais
- Admin HTML/CSS/JS simples em `/admin`
- Cliente de teste Banco Arkhe em `/admin/cliente-teste`
- Provider intercambiavel via `IDENTITY_PROVIDER`

## Biblioteca Facial

A implementacao real usa OpenCV contrib:

- detector: YuNet `face_detection_yunet_2023mar.onnx`
- reconhecedor: SFace `face_recognition_sface_2021dec.onnx`
- metrica: cosseno sobre embedding normalizado, convertido para similaridade 0..1
- licenca: OpenCV e opencv_zoo usam Apache License 2.0

Motivo da escolha: possui wheels pre-compilados para Windows/Linux, roda em Docker, gera embeddings localmente e nao envia imagens a servicos externos. A alternativa `insightface==0.7.3` foi testada no Windows/Python 3.12 e falhou por exigir Microsoft C++ Build Tools para compilar extensao nativa.

Limites: o limiar facial padrao e experimental. Use `scripts/calibrate_threshold.py` com pares genuinos/impostores consentidos antes de usar qualquer valor como regra final.

## Instalar no Windows

```powershell
cd C:\Users\Usuário\Documents\BANCO\arkhe-identity-api
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\scripts\download_face_models.ps1
.\.venv\Scripts\python scripts\generate_secrets.py
Copy-Item .env.example .env
```

Copie os valores gerados para `.env`. Nao use os placeholders do exemplo em producao.

## Rodar com Docker

```powershell
docker compose up --build
```

Endpoints:

- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Admin: `http://localhost:8000/admin`
- Cliente teste: `http://localhost:8000/admin/cliente-teste`

## Migrations

```powershell
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\alembic revision --autogenerate -m "descricao"
```

## Fluxo Administrativo

1. Entrar em `/admin`.
2. Autenticar com `ADMIN_USERNAME` e `ADMIN_PASSWORD_HASH`.
3. Aceitar consentimento explicitamente.
4. Cadastrar pessoa.
5. Adicionar documento.
6. Cadastrar referencia facial por camera ou upload.
7. A imagem original e descartada por padrao; somente o embedding criptografado fica persistido.

Funcionalidades incluidas: listar cadastros, visualizar dados mascarados, bloquear cadastro, revogar referencia facial, revogar consentimento, exportar JSON e excluir definitivamente a pessoa com seus dados relacionados.

## Contrato Compatível V5

Endpoint:

```http
POST /v5/pessoa-fisica/validacao
X-Arkhe-Api-Key: <api-key>
```

Entrada resumida:

```json
{
  "privacidade": {
    "rfb": { "id_template": "arkhe-template-v1" },
    "senatran": { "token": "token-interno-opcional", "cnpj_anuente": "cnpj-opcional" }
  },
  "cpf": "00000000000",
  "validacao": {
    "nome": "Nome completo",
    "data_nascimento": "2000-01-01",
    "sexo": "M",
    "nacionalidade": 1,
    "rfb": { "situacao_cpf": "regular" },
    "documento": { "tipo": 1, "numero": "000000000", "orgao_expedidor": "SSP", "uf_expedidor": "SP" }
  },
  "biometria_facial": { "imagem": "<BASE64>", "vivacidade": false },
  "tag": "cadastro-banco-arkhe"
}
```

`privacidade` existe apenas por compatibilidade estrutural. Nao representa autorizacao real da RFB ou Senatran. Ative `REQUIRE_PRIVACY_OBJECT=true` somente se quiser exigir a presenca do objeto no ambiente local.

Saida resumida:

```json
{
  "request_id": "uuid",
  "provedor": "ARKHE_PRIVATE_REGISTRY",
  "ambiente": "TCC",
  "rfb_existe": true,
  "cnh_existe": true,
  "rfb": { "nome": true, "nome_similaridade": 1.0, "data_nascimento": true },
  "biometria_facial": {
    "disponivel": true,
    "similaridade": 0.94,
    "probabilidade": "ALTISSIMA",
    "vivacidade": null,
    "codigo_retorno": "ARKHE_FACE_OK"
  },
  "regra_local": {
    "cadastro_confirmado": true,
    "face_confirmada": true,
    "validacao_combinada": true,
    "limiar_facial": 0.85
  },
  "avisos": [
    "Comparacao realizada exclusivamente com a base privada Banco Arkhe.",
    "Nenhuma base governamental foi consultada.",
    "Vivacidade nao foi verificada."
  ]
}
```

Se `vivacidade=true`, a API retorna 422 com `ARKHE_LIVENESS_NOT_SUPPORTED`.

## Exemplos

curl:

```bash
curl -X POST http://localhost:8000/v5/pessoa-fisica/validacao \
  -H "Content-Type: application/json" \
  -H "X-Arkhe-Api-Key: local-dev-api-key" \
  -d @examples/request.json
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/v5/pessoa-fisica/validacao `
  -Headers @{ "X-Arkhe-Api-Key" = "local-dev-api-key" } `
  -ContentType "application/json" `
  -Body (Get-Content .\examples\request.json -Raw)
```

JavaScript:

```js
await fetch("/v5/pessoa-fisica/validacao", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Arkhe-Api-Key": "local-dev-api-key" },
  body: JSON.stringify(payload)
});
```

Python:

```python
import requests

requests.post(
    "http://localhost:8000/v5/pessoa-fisica/validacao",
    headers={"X-Arkhe-Api-Key": "local-dev-api-key"},
    json=payload,
    timeout=20,
)
```

## Seguranca e LGPD

- Nao armazene CPF ou documento em texto puro.
- Nao registre selfie, Base64, embedding, CPF completo ou payload sensivel nos logs.
- Use chaves separadas: `DATA_ENCRYPTION_KEY`, `LOOKUP_HMAC_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `API_KEY_HASH`.
- A caixa de consentimento nunca vem marcada.
- Sem consentimento, nao cadastre biometria.
- Revogacao e exclusao definitiva estao expostas no admin/API.
- Use apenas pessoas ficticias ou participantes que aceitaram expressamente.

## Calibracao

CSV de entrada:

```csv
left_path,right_path,label
foto_a1.jpg,foto_a2.jpg,genuine
foto_a1.jpg,foto_b1.jpg,impostor
```

Comando:

```powershell
.\.venv\Scripts\python scripts\calibrate_threshold.py --pairs pares.csv --out calibration_report.csv
```

O relatorio usa identificadores anonimizados e calcula FAR/FRR por limiar.

## Troca futura para Datavalid

O frontend do banco deve chamar sempre a mesma interface. No futuro, altere:

```env
IDENTITY_PROVIDER=private_registry
```

para:

```env
IDENTITY_PROVIDER=datavalid
```

`DatavalidProvider` esta propositalmente vazio, com TODOs. Ele nao chama o Datavalid agora e nao contem credenciais reais.

## Deploy EasyPanel

- Defina `DATABASE_URL` apontando para PostgreSQL externo.
- Defina `PORT`.
- Rode `alembic upgrade head` no start.
- Use usuario nao root do Dockerfile.
- Envie logs para stdout.
- Nao habilite `DEBUG` em producao.
- Garanta storage externo se decidir manter imagens, embora `STORE_REFERENCE_IMAGES=false` seja o padrao.

## Verificacao Local Realizada

Neste ambiente:

- `ruff check .`: passou
- `mypy app`: passou
- `pytest`: 13 testes passaram

Docker nao estava acessivel no Windows local: o client nao encontrou `docker_engine`. Por isso, PostgreSQL via Docker e migrations contra Postgres nao foram executados nesta maquina.
