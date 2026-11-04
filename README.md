# ReelSalva 📲

PWA simples para baixar **Reels e vídeos públicos do Instagram, Facebook, Shopee Vídeo e Pinterest**, desde que sejam seus ou você tenha autorização para salvá-los.

## Qualidade dos downloads

- **Máxima qualidade disponível (padrão)**: Instagram, Facebook e Pinterest selecionam a melhor combinação de vídeo e áudio publicada, sem o antigo limite de 720p.
- **Full HD até 1080p** e **HD até 720p**: procuram a melhor fonte dentro do limite escolhido, sem ampliar artificialmente.
- FFmpeg combina os fluxos de áudio e vídeo e tenta entregar MP4 sem recodificar os pixels.
- **Shopee Vídeo:** links públicos frequentemente oferecem um único MP4; a qualidade é a da fonte e o seletor não cria resolução adicional.
- Máximo de 250 MB por vídeo. Arquivos grandes podem demorar mais. Somente conteúdo público autorizado.

## Como usar
1. Copie o link de compartilhamento do vídeo no Instagram, Facebook, Shopee Vídeo ou Pinterest.
2. Abra o PWA, cole o link e toque em **Baixar vídeo MP4**.
3. No Android, use Chrome > ⋮ > Adicionar à tela inicial para instalar.
4. Depois de instalado, também pode aparecer na lista de destinos do botão Compartilhar do Instagram, Facebook, Shopee Vídeo ou Pinterest.

## Executar localmente
Python 3.11+:

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Abra http://localhost:8000.

## Publicar no Google Cloud Run

O projeto agora inclui `Dockerfile`, proteção por senha e instruções em [CLOUD_RUN.md](CLOUD_RUN.md). É necessário ter um projeto com faturamento habilitado, mesmo que o uso fique no nível gratuito. O aplicativo está publicado no Cloud Run, com proteção de acesso pessoal e configuração para economizar recursos.

## Publicar em Render
Conecte este repositório a um Web Service Python gratuito. Build: `pip install -r requirements.txt`. Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`. O arquivo `render.yaml` também contém essas definições.

## Suporte ao Shopee Vídeo

- Aceita links curtos de compartilhamento como `https://br.shp.ee/xxxxx` e páginas `https://sv.shopee.com.br/share-video/...`.
- O servidor segue somente redirecionamentos oficiais da Shopee e lê o arquivo `watermarkVideoUrl` dos dados públicos da página. O MP4 preserva qualquer marca d'água original.
- Não exige login, não acessa vídeos privados e recusa redirecionamentos/CDNs fora dos domínios permitidos.
- Nem todos os links da Shopee são vídeos públicos: links para anúncio de produto, live restrita e conteúdo removido podem falhar.

## Pinterest

- Cole um link de Pin de vídeo (ex.: `https://www.pinterest.com/pin/123456789/`) ou um link curto oficial `https://pin.it/...`.
- O app detecta o Pinterest automaticamente e possui botão dedicado.
- Extrator yt-dlp, sem login, cookies nem contorno de restrições; apenas vídeos públicos obtidos legitimamente.
- Pins de imagens, conteúdos privados e vídeos sem download permitido podem falhar.
- O Pinterest também disponibiliza downloads nativos para certos vídeos em tela cheia quando o criador permite. Prefira essa opção quando disponível.

## Limitações
Somente vídeos públicos, sem login ou cookies. Instagram e Facebook podem exigir login ou bloquear downloads em IPs de datacenters. Nem todos os vídeos públicos funcionarão. O serviço limita download a 250 MB, 8 tentativas a cada 15 minutos por IP e 2 downloads simultâneos. Para uso de grande escala, implante autenticação, rate limiting distribuído e proteção de rede.

Não afiliado ao Instagram/Meta. Respeite direitos autorais e termos aplicáveis.
