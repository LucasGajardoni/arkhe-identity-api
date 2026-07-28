# Arkhe Identity API

Serviço independente de verificação de identidade baseado em uma base privada
previamente formada e consentida. Pode ser consumido por qualquer aplicação que
precise confirmar `CPF + documento oficial + selfie`.

A API não é um cadastro bancário, CRM ou cadastro de clientes. Telefone, e-mail,
endereço, conta, saldo e outros dados de relacionamento pertencem ao sistema
consumidor.

> A comparação ocorre somente com a base privada cadastrada neste serviço.

O projeto não consulta Receita Federal, Senatran, Renach ou outra base
governamental, não implementa prova de vida e não é uma integração oficial com
Datavalid.

## Arquitetura

- FastAPI + Uvicorn;
- SQLAlchemy 2 + Alembic;
- PostgreSQL em desenvolvimento e produção;
- SQLite em testes automatizados;
- AES-GCM para dados recuperáveis;
- HMAC-SHA-256 para pesquisa de CPF e documento;
- OpenCV YuNet + SFace para detecção e embeddings faciais locais;
- painel administrativo em `/admin`;
- API genérica recomendada em `/v1/identity/validate`;
- camada V5 temporária de compatibilidade em `/v5/pessoa-fisica/validacao`.

A política central de validação fica no `IdentityValidationService`. A API
genérica usa diretamente essa política. A rota V5 converte sua entrada para o
contrato central e adapta o resultado ao formato antigo.

## Dados armazenados

O serviço mantém apenas dados necessários à identidade:

- CPF criptografado e hash pesquisável;
- dados civis essenciais;
- documentos oficiais;
- referência facial em forma de embedding criptografado;
- consentimentos;
- tentativas de validação.

As colunas antigas `email` e `telefone` permanecem fisicamente no banco somente
para compatibilidade. Elas estão obsoletas, não são aceitas pelos schemas
administrativos e não participam de nenhuma decisão. Uma remoção futura deve ser
feita por migration específica e não destrutiva.

## Formação da base privada

1. O administrador entra em `/admin`.
2. Cadastra CPF válido e dados civis essenciais.
3. Registra o consentimento.
4. Adiciona um ou mais documentos oficiais.
5. Cadastra a referência facial por câmera ou upload.
6. O `person_id` associa os registros somente dentro do serviço.

O UUID interno nunca é exigido de sistemas consumidores.

## Validação por sistemas externos

1. O consumidor envia CPF, documento apresentado e selfie Base64.
2. A API valida os dígitos do CPF e procura o hash privado.
3. Confirma pessoa ativa e consentimento vigente.
4. Localiza documento do mesmo tipo e compara os campos aplicáveis.
5. Reprova documentos vencidos.
6. Compara a selfie com a referência facial ativa.
7. Retorna resultado estruturado e registra a tentativa.

A decisão final é:

```text
pessoa encontrada e ativa
E consentimento vigente
E documento confirmado
E biometria confirmada
```

## Instalação local no Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\scripts\download_face_models.ps1
.\.venv\Scripts\python scripts\generate_secrets.py
Copy-Item .env.example .env
```

Copie os segredos gerados para `.env`. Os placeholders dos arquivos de exemplo
não podem ser usados em produção.

Para iniciar:

```powershell
.\.venv\Scripts\uvicorn app.main:app --reload
```

Ou com Docker:

```powershell
docker compose up --build
```

Endpoints locais:

- API: `http://localhost:8000`;
- Swagger: `http://localhost:8000/docs`;
- Admin: `http://localhost:8000/admin`.

## API genérica recomendada

```http
POST /v1/identity/validate
Content-Type: application/json
X-Arkhe-Api-Key: <api-key>
```

Tipos aceitos: `RG`, `CIN`, `CNH`, `PASSAPORTE`, `CRNM` e `OUTRO`.

Regras principais:

| Tipo | Campos obrigatórios além de tipo e número |
|---|---|
| RG | órgão expedidor e UF |
| CIN | órgão expedidor e UF; número igual ao CPF da pessoa |
| CNH | órgão expedidor e UF |
| PASSAPORTE | país emissor |
| CRNM | país emissor ou órgão expedidor |
| OUTRO | nenhum |

RG não exige validade. Datas são opcionais, mas uma validade cadastrada e
vencida reprova o documento.

### Requisição

```json
{
  "cpf": "52998224725",
  "documento": {
    "tipo": "RG",
    "numero": "123456789",
    "orgao_expedidor": "SSP",
    "uf_expedidor": "SP",
    "pais_emissor": "BR",
    "data_emissao": "2025-01-10"
  },
  "selfie": {
    "imagem_base64": "<BASE64>"
  }
}
```

O endpoint não aceita `person_id`, UUID, telefone, e-mail, endereço,
`client_id`, `customer_id` ou dados bancários.

### Aprovação

```json
{
  "request_id": "3bc63ac8-a063-4608-a490-78bd187e78d1",
  "valido": true,
  "codigo": "IDENTIDADE_CONFIRMADA",
  "motivos": [],
  "verificacoes": {
    "cpf": {"valido": true, "pessoa_encontrada": true},
    "documento": {
      "valido": true,
      "tipo": "RG",
      "campos": {
        "tipo": true,
        "numero": true,
        "orgao_expedidor": true,
        "uf_expedidor": true
      }
    },
    "biometria": {
      "valido": true,
      "similaridade": 0.94,
      "limiar": 0.85
    }
  }
}
```

`similaridade` varia de 0 a 1 e é comparada ao limiar configurado. Esse valor
não representa prova de vida.

### Reprovação

```json
{
  "request_id": "c2a76f67-377f-4d25-b19d-6e981e416336",
  "valido": false,
  "codigo": "DOCUMENTO_DIVERGENTE",
  "motivos": ["NUMERO_DOCUMENTO_DIVERGENTE"],
  "verificacoes": {
    "cpf": {"valido": true, "pessoa_encontrada": true},
    "documento": {
      "valido": false,
      "tipo": "RG",
      "campos": {"tipo": true, "numero": false}
    },
    "biometria": {
      "valido": true,
      "similaridade": 0.92,
      "limiar": 0.85
    }
  }
}
```

### Códigos de resultado

- `IDENTIDADE_CONFIRMADA`;
- `CPF_INVALIDO`;
- `PESSOA_NAO_ENCONTRADA`;
- `PESSOA_INATIVA`;
- `CONSENTIMENTO_AUSENTE`;
- `DOCUMENTO_NAO_ENCONTRADO`;
- `DOCUMENTO_DIVERGENTE`;
- `DOCUMENTO_VENCIDO`;
- `SELFIE_INVALIDA`;
- `FACE_NAO_DETECTADA`;
- `MULTIPLAS_FACES_DETECTADAS`;
- `REFERENCIA_FACIAL_AUSENTE`;
- `BIOMETRIA_NAO_CONFIRMADA`;
- `ERRO_INTERNO`.

Validações processadas retornam HTTP 200, inclusive pessoa não encontrada para
reduzir enumeração de CPFs. CPF ou imagem malformados retornam HTTP 400 com o
mesmo corpo estruturado. API key inválida retorna 401 e payload estruturalmente
inválido retorna 422.

### cURL

```bash
curl -X POST http://localhost:8000/v1/identity/validate \
  -H "Content-Type: application/json" \
  -H "X-Arkhe-Api-Key: local-dev-api-key" \
  --data @identity-request.json
```

### JavaScript

```javascript
const response = await fetch("http://localhost:8000/v1/identity/validate", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Arkhe-Api-Key": "local-dev-api-key"
  },
  body: JSON.stringify(payload)
});
const result = await response.json();
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/identity/validate",
    headers={"X-Arkhe-Api-Key": "local-dev-api-key"},
    json=payload,
    timeout=20,
)
result = response.json()
```

## Compatibilidade V5

```http
POST /v5/pessoa-fisica/validacao
X-Arkhe-Api-Key: <api-key>
```

Essa rota permanece temporariamente para consumidores existentes. Ela é uma
camada de compatibilidade inspirada no formato Datavalid, não uma integração
oficial. Novos consumidores devem usar `/v1/identity/validate`.

A V5 conserva seus schemas externos, incluindo campos civis antigos, mas sua
decisão combinada passa pela mesma confirmação obrigatória de documento e
biometria da política central. `vivacidade=true` continua retornando 422 porque
prova de vida não está implementada.

## Segurança e auditoria

- CPF e documento não são armazenados em texto puro;
- Base64, imagem, embedding, CPF completo e API key não são registrados;
- a resposta nunca contém `person_id`;
- toda tentativa processada registra request ID, pessoa interna quando
  encontrada, código, campos avaliados, duração, similaridade e ausências;
- login, API genérica e V5 possuem rate limit configurável;
- a aplicação recusa defaults de desenvolvimento quando
  `ENVIRONMENT=production`.

Variáveis relevantes:

```env
ADMIN_LOGIN_RATE_LIMIT=20/minute
IDENTITY_VALIDATION_RATE_LIMIT=120/minute
V5_VALIDATION_RATE_LIMIT=120/minute
```

Produção exige valores seguros para `DATA_ENCRYPTION_KEY`,
`LOOKUP_HMAC_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH` e `API_KEY_HASH`.
`API_KEY_PLAINTEXT_FOR_LOCAL_ONLY` deve ficar vazio.

`ADMIN_PASSWORD_HASH` e `API_KEY_HASH` recebem hashes bcrypt, nunca os
segredos em texto puro. Gere cada hash interativamente, sem colocar o valor na
linha de comando ou no histórico:

```powershell
.\.venv\Scripts\python.exe -c "from getpass import getpass; from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash(getpass('Segredo: ')))"
```

Copie o resultado diretamente para o gerenciador de variáveis do ambiente e
não o grave em `.env`, logs ou documentação.

Em uma base já existente, preserve obrigatoriamente `DATA_ENCRYPTION_KEY` e
`LOOKUP_HMAC_KEY`. Trocar a primeira impede descriptografar CPF, documentos e
embeddings; trocar a segunda impede localizar pessoas pelo CPF.

## Testes

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\mypy app
```

Os testes usam backend facial falso e não dependem dos modelos OpenCV reais.

## Migrations

Esta etapa não cria migration. Para um banco novo ou existente:

```powershell
.\.venv\Scripts\alembic upgrade head
```

Não remova manualmente as colunas legadas de e-mail e telefone.

## Deploy no EasyPanel

1. Faça backup do PostgreSQL.
2. Confirme que `DATABASE_URL` aponta para o PostgreSQL persistente existente
   pela rede interna do projeto.
3. Preserve os valores atuais de `DATA_ENCRYPTION_KEY` e `LOOKUP_HMAC_KEY`.
4. Configure as demais variáveis de `easypanel.env.example`.
5. Mantenha `ENVIRONMENT=production`, `DEBUG=false`,
   `FACE_BACKEND=opencv` e `API_KEY_PLAINTEXT_FOR_LOCAL_ONLY=` vazio.
6. Mantenha `ENABLE_API_DOCS=true` somente se Swagger/ReDoc precisarem ficar
   públicos neste primeiro deploy. Depois, podem ser removidos com
   `ENABLE_API_DOCS=false`, sem alteração de código.
7. Configure `FORWARDED_ALLOW_IPS` apenas com o IP ou CIDR do proxy interno
   confiável. Não use `*` sem garantir isolamento de rede.
8. Publique a nova imagem.
9. O `scripts/start.sh` executará `alembic upgrade head` antes do Uvicorn e
   encerrará o container se a migration falhar.
10. Use `/ready` como readiness check e `/health` como liveness check.
11. Verifique `/docs` quando habilitado e `/admin`.
12. Teste uma identidade fictícia/consentida na rota genérica.
13. Execute um teste de regressão no consumidor V5 existente.
14. Confirme logs e registros de auditoria sem conteúdo sensível.

O HTTPS é terminado pelo proxy do EasyPanel; isso permite o acesso à câmera do
painel administrativo. Integrações backend-to-backend não dependem de CORS.
Para navegadores, configure origens explícitas em `CORS_ORIGINS`; produção
recusa `*` porque a aplicação habilita credenciais.

O rate limit usa o endereço remoto observado pela aplicação. Após o deploy,
confirme que o proxy encaminha `X-Forwarded-For` e que Uvicorn confia somente
no proxy interno configurado em `FORWARDED_ALLOW_IPS`.

Antes de uso real, calibre `FACIAL_SIMILARITY_THRESHOLD` com pares genuínos e
impostores consentidos. O algoritmo local não realiza prova de vida e não deve
ser usado sozinho em cenários de alto risco.
