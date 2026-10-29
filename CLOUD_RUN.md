# Implantação do ReelSalva no Google Cloud Run

O site anterior está no Render e foi suspenso por faturamento. A migração não altera o serviço do Render nem os bots existentes.

## Pré-requisitos

- Projeto Google Cloud com **faturamento ativo** (mesmo quando o uso estimado fica na franquia gratuita).
- CLI `gcloud` autenticada com uma conta autorizada a implantar Cloud Run, habilitar APIs e usar o Cloud Build e Artifact Registry.
- **Senha pessoal forte** para restringir o acesso ao PWA. Não a publique no GitHub.
- APIs Cloud Run, Cloud Build e Artifact Registry habilitadas.

## Deploy seguro e econômico

Após configurar o projeto desejado e habilitar as APIs, execute na raiz deste repositório:

```sh
gcloud config set project SEU_PROJECT_ID

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud run deploy reelsalva-pwa \
  --source . \
  --region us-central1 \
  --platform managed \
  --cpu 1 \
  --memory 1Gi \
  --timeout 180 \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 1 \
  --cpu-throttling \
  --allow-unauthenticated \
  --set-env-vars REELSALVA_ACCESS_CODE=ESCOLHA_UMA_SENHA_FORTE
```

O sinalizador `--allow-unauthenticated` é necessário para que o PWA abra num navegador sem login do Google Cloud. **O aplicativo exige autenticação HTTP Basic** quando `REELSALVA_ACCESS_CODE` está definido. No Chrome, informe **usuário `julio`** e a senha escolhida. Caso a senha não tenha sido configurada no Cloud Run, o app retorna erro 503 em vez de ficar aberto.

Evite salvar senhas em scripts versionados, histórico compartilhado do terminal ou prints. Para infraestrutura permanente, prefira o Secret Manager. A API de health permanece pública.

## Prevenção de custos

- `min-instances=0`: escala a zero entre acessos.
- `max-instances=1`: limita a uma instância em execução.
- `concurrency=1`: apenas um download por vez.
- `timeout=180`: limita duração por requisição.
- Configure orçamento e alertas no Cloud Billing (alertas comuns **não bloqueiam** cobranças; quando disponível, considere **orçamento com gasto máximo**).
- Transferências de vídeos para celulares, Cloud Build e armazenamento de imagens no Artifact Registry podem gerar cobranças mesmo em uso pessoal.
- Não confunda o tráfego pequeno com isenção de custos garantida.

## Validação

1. Abra a URL `https://...run.app/api/health`. Deve aparecer `{"ok":true,...}`.
2. Abra a raiz do app, autentique-se e instale pelo menu do Chrome.
3. Teste a transferência de um Reel público autorizado.
4. Se falhar, confira logs no Console do Cloud Run. O Instagram pode bloquear IPs de servidores.

Não crie múltiplas implantações de teste no mesmo projeto sem limpar artefatos antigos do Artifact Registry.
