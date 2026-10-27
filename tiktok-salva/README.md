# TikSalva 🎬

PWA para Android e desktop para baixar **vídeos públicos do TikTok** em MP4, pelo link de compartilhamento. O TikSalva não solicita senha nem login.

## Funcionalidades

- Link completo ou curto (tiktok.com, vm.tiktok.com, vt.tiktok.com).
- Download MP4 de vídeo público, sem baixar arquivos de legenda (.srt/.vtt).
- Instalação na tela inicial do Android via Chrome.
- Interface responsiva e PWA básico com cache somente da interface.
- Limites de 120 MB, duas extrações simultâneas e 10 tentativas por IP a cada 15 minutos.
- Arquivo temporário apagado após envio.

**Limitação:** legendas/textos inseridos na imagem do vídeo permanecem. Não há garantia de retirar a marca-d'água do TikTok. Vídeos privados ou com restrições podem falhar. Use apenas conteúdos que você tem direito de salvar e reutilizar.

## Rodar localmente

Da raiz do repositório:

\`\`\`sh
pip install -r tiktok-salva/requirements.txt
cd tiktok-salva
uvicorn app:app --reload
\`\`\`

Abra http://127.0.0.1:8000.

## Implantar no Render (serviço separado)

Crie um **Web Service** com o mesmo repositório, usando a branch \`tiktok-salva\`, Python e o plano Free:

- Build: \`pip install -r tiktok-salva/requirements.txt\`
- Start: \`cd tiktok-salva && uvicorn app:app --host 0.0.0.0 --port $PORT\`
- Health: \`/api/health\`

O serviço web requer Python com yt-dlp. Não funciona apenas com GitHub Pages, porque o navegador não pode extrair sozinho os MP4s de todos os links públicos.

O Render Free pode hibernar e pode aplicar limites de banda. O TikTok também pode bloquear servidores ou mudar suas páginas.

## Recuperacao de falhas na extracao

O servico usa yt-dlp e repete a tentativa com um user-agent alternativo. Caso autorizado na interface (checkbox ligado por padrao com aviso), transmite **somente o link publico** para a API externa TikWM e recebe um MP4 quando disponivel. TikTok e TikWM podem bloquear esse acesso, logo nao ha garantia de sucesso. Nunca pede login/senha/cookies do usuario. Os downloads temporarios sao limitados em tamanho.
