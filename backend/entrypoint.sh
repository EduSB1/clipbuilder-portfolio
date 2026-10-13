#!/bin/sh
# Ajusta a posse dos volumes montados e baixa o privilégio antes de iniciar a API.
#
# Necessário porque volumes nomeados criados por versões anteriores da imagem
# pertencem a root:root — sem este chown o processo não-root não conseguiria
# gravar em /app/data (vídeos) nem em /app/logs.
set -e

for dir in /app/data /app/logs; do
    mkdir -p "$dir"
    chown -R clipbuilder:clipbuilder "$dir" 2>/dev/null || true
done

exec gosu clipbuilder "$@"
