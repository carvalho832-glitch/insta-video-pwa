# ReelSalva 📲

PWA simples para baixar **Reels e publicações públicas do Instagram**, desde que sejam seus ou você tenha autorização para salvá-los.

## Como usar
1. Copie o link de compartilhamento do vídeo no Instagram.
2. Abra o PWA, cole o link e toque em **Baixar vídeo MP4**.
3. No Android, use Chrome > ⋮ > Adicionar à tela inicial para instalar.
4. Depois de instalado, também pode aparecer na lista de destinos do botão Compartilhar do Instagram.

## Executar localmente
Python 3.11+:

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Abra http://localhost:8000.

## Publicar no Google Cloud Run

O projeto agora inclui `Dockerfile`, proteção por senha e instruções em [CLOUD_RUN.md](CLOUD_RUN.md). É necessário ter um projeto com faturamento habilitado, mesmo que o uso fique no nível gratuito. A migração para o Cloud Run ainda depende dessa configuração.

## Publicar em Render
Conecte este repositório a um Web Service Python gratuito. Build: `pip install -r requirements.txt`. Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`. O arquivo `render.yaml` também contém essas definições.

## Limitações
Somente vídeos públicos, sem login ou cookies. O Instagram pode bloquear vídeos ou IPs de datacenters, e nem todos os Reels funcionarão. O serviço limita download a 250 MB, 8 tentativas a cada 15 minutos por IP e 2 downloads simultâneos. Para uso de grande escala, implante autenticação, rate limiting distribuído e proteção de rede.

Não afiliado ao Instagram/Meta. Respeite direitos autorais e termos aplicáveis.
