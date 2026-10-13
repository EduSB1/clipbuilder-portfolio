FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1

WORKDIR /app

# ── Dependências de sistema ───────────────────────────────────────────────
# ffmpeg        — geração de clipes e merge de streams do yt-dlp
# libreoffice   — conversão DOCX→PDF
# libpq-dev     — driver PostgreSQL (psycopg2)
# curl          — health check
# gosu          — troca de usuário no entrypoint (sem `su`, preserva sinais)
# nodejs + npm  — exigidos pelo bgutil-ytdlp-pot-provider (PO Token)
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     ffmpeg \
     fonts-dejavu-core \
     gosu \
     libreoffice \
     libpq-dev \
     curl \
     nodejs \
     npm \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# ── Dependências Python ───────────────────────────────────────────────────
# Copiadas antes do código-fonte para que o cache da layer só seja invalidado
# quando requirements.txt mudar.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── yt-dlp + plugins anti-bot do YouTube ──────────────────────────────────
# Instalados SEM pin de versão, de propósito: o YouTube muda as proteções
# constantemente e uma versão fixa para de funcionar em dias.  O contrapeso é
# que dois builds do mesmo commit podem gerar imagens diferentes — se precisar
# reproduzir um build antigo, fixe as versões via `--build-arg YTDLP_PIN=...`.
#   - yt-dlp:                    downloader
#   - yt-dlp-get-pot:            framework de geração de PO Token
#   - bgutil-ytdlp-pot-provider: backend do PO Token (requer Node.js)
#
# O remédio mais confiável contra bloqueio de IP de datacenter continua sendo
# CLIPBUILDER_YTDLP_PROXY apontando para um proxy residencial.
ARG YTDLP_PIN=""
RUN pip install --no-cache-dir --upgrade \
      "yt-dlp${YTDLP_PIN}" yt-dlp-get-pot bgutil-ytdlp-pot-provider

# ── Usuário sem privilégios ───────────────────────────────────────────────
# A API executa ffmpeg, LibreOffice e yt-dlp sobre conteúdo enviado por
# usuários; rodar isso como root é risco desnecessário.
RUN useradd --create-home --shell /usr/sbin/nologin clipbuilder \
  && mkdir -p /app/data /app/logs \
  && chown -R clipbuilder:clipbuilder /app

# gosu preserva o ambiente, então HOME precisa apontar para um diretório que o
# usuário sem privilégios possa escrever — LibreOffice e npm gravam ali.
ENV HOME=/home/clipbuilder

COPY --chown=clipbuilder:clipbuilder entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY --chown=clipbuilder:clipbuilder . ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD curl -fsS -o /dev/null http://127.0.0.1:8000/health || exit 1

# O entrypoint roda como root só para ajustar a posse dos volumes e então
# baixa o privilégio para `clipbuilder`.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Um único worker: o estado das sessões de vídeo vive em memória no processo
# (`_videos` em main.py).  Antes de aumentar para --workers N, esse estado
# precisa ir para o Postgres ou Redis.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
