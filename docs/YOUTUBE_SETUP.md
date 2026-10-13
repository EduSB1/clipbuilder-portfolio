# YouTube Downloads no VPS — Guia de Configuração

O YouTube bloqueia downloads de IPs de datacenter/VPS. Este guia explica como configurar o ClipBuilder para que os downloads **nunca mais sejam bloqueados**.

---

## TL;DR (Solução Rápida)

```bash
# 1. No seu navegador (Chrome/Firefox), instale a extensão "Get cookies.txt LOCALLY"
# 2. Acesse youtube.com logado na sua conta Google
# 3. Exporte os cookies (clique na extensão → Export)
# 4. Copie o arquivo para o servidor:
scp ~/Downloads/cookies.txt root@seu-servidor:/home/ClipBuilder/cookies.txt

# 5. No servidor, execute:
./setup_youtube_cookies.sh /home/ClipBuilder/cookies.txt

# Pronto! Downloads funcionam por 6-12 meses.
```

---

## Métodos Disponíveis (por ordem de confiabilidade)

| # | Método | Confiabilidade | Manutenção | Recomendado? |
|---|--------|---------------|------------|--------------|
| 1 | **Cookies File** | ⭐⭐⭐⭐⭐ | Renovar a cada 6-12 meses | ✅ **SIM** |
| 2 | Proxy Residencial | ⭐⭐⭐⭐ | Custo mensal | Complemento |
| 3 | PO Token (bgutil) | ⭐⭐⭐ | Automático | Já incluso como fallback |
| 4 | Bare (sem nada) | ⭐ | — | Só funciona fora de VPS |

---

## Método 1: Cookies File (Recomendado) ✅

### O que é?

O yt-dlp aceita um arquivo `cookies.txt` no formato Netscape que contém os cookies de uma sessão autenticada no YouTube. Com cookies reais de um navegador logado, o YouTube trata a requisição como vinda de um usuário real — não importa se o IP é de datacenter.

### Passo a Passo

#### 1. Instale a extensão no navegador

Escolha UMA das opções:

- **Chrome**: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- **Firefox**: [cookies.txt](https://addons.mozilla.org/addon/cookies-txt/)
- **Edge**: [Get cookies.txt LOCALLY](https://microsoftedge.microsoft.com/addons/detail/get-cookiestxt-locally/hellagfjdiaicmfbfphiiemdalcablne)

> ⚠️ **IMPORTANTE**: Use apenas extensões de confiança. Extensões de cookies têm acesso a dados sensíveis. As listadas acima são as mais recomendadas pela comunidade do yt-dlp.

#### 2. Faça login no YouTube

1. Abra [https://www.youtube.com](https://www.youtube.com)
2. Faça login com qualquer conta Google (pode ser uma conta dedicada)
3. Assista qualquer vídeo para garantir que a sessão está ativa

#### 3. Exporte os cookies

1. Ainda na página do YouTube, clique no ícone da extensão
2. Clique em "Export" ou "Download"
3. Salve como `cookies.txt`

> 💡 **Dica**: Exporte os cookies enquanto está no youtube.com — a extensão só captura cookies do domínio atual.

#### 4. Copie o arquivo para o servidor

Do seu computador local:

```bash
scp ~/Downloads/cookies.txt root@seu-servidor:/home/ClipBuilder/cookies.txt
```

Ou se preferir, use SFTP, rsync, ou qualquer método de transferência.

#### 5. Instale os cookies

No servidor:

```bash
cd /home/ClipBuilder
./setup_youtube_cookies.sh cookies.txt
```

O script vai:
- Validar o formato do arquivo
- Copiar para dentro do volume Docker
- Testar se os cookies funcionam com um vídeo real

#### 6. Verificar

```bash
./setup_youtube_cookies.sh --test
```

Deve mostrar:
```
  ✓ Cookies are working!
    Test video: Me at the zoo
```

### Usando o Setup Interativo

Se preferir ser guiado passo a passo:

```bash
./setup_youtube_cookies.sh
```

O script interativo mostra todas as instruções e pergunta o caminho do arquivo.

### Quando Renovar

Os cookies do YouTube tipicamente duram **6 a 12 meses**. Sinais de que precisam ser renovados:

- Downloads começam a falhar com "Sign in to confirm you're not a bot"
- O teste `./setup_youtube_cookies.sh --test` começa a falhar

Para renovar, repita os passos 2-5 acima (exporte novos cookies e reinstale).

> ⚠️ **Atenção**: Se você fizer **logout** da conta Google no navegador, os cookies são invalidados imediatamente. Evite fazer logout da conta usada para exportar cookies.

### FAQ sobre Cookies

**P: Posso usar uma conta Google descartável?**
R: Sim! É até recomendado. Crie uma conta Google nova só para isso.

**P: Os cookies dão acesso à minha conta Google?**
R: Os cookies dão acesso à sessão do YouTube apenas. Mesmo assim, trate o arquivo como uma senha — não compartilhe e não commite no git.

**P: E se eu fizer `docker volume prune`?**
R: Vai perder os cookies instalados. Execute `./setup_youtube_cookies.sh` novamente.

**P: Funciona com YouTube Premium?**
R: Sim. Na verdade, cookies de conta Premium podem ter menos chance de serem bloqueados.

**P: Preciso manter o navegador aberto?**
R: Não. Uma vez exportados, os cookies funcionam independentemente do navegador.

---

## Método 2: Proxy Residencial (Complemento)

Um proxy residencial faz com que as requisições do yt-dlp pareçam vir de um IP doméstico em vez de um datacenter. O YouTube raramente bloqueia IPs residenciais.

**Pode ser usado sozinho ou combinado com cookies para máxima confiabilidade.**

### Provedores Recomendados

| Provedor | Preço | Tipo |
|----------|-------|------|
| [BrightData](https://brightdata.com/) | ~$15/GB | Residencial rotativo |
| [SmartProxy](https://smartproxy.com/) | ~$12/GB | Residencial rotativo |
| [IPRoyal](https://iproyal.com/) | ~$7/GB | Residencial estático |
| [Webshare](https://www.webshare.io/) | ~$5/mês | Datacenter (menos confiável) |

### Configuração

No `backend/.env`:

```env
# SOCKS5 (recomendado — menor overhead)
CLIPBUILDER_YTDLP_PROXY=socks5://usuario:senha@proxy-host:1080

# ou HTTP
CLIPBUILDER_YTDLP_PROXY=http://usuario:senha@proxy-host:8080
```

Reinicie:

```bash
docker compose restart backend
```

### Estimativa de Consumo

Um vídeo de 10 minutos em 720p ≈ 100-300 MB. Com proxy a $10/GB:

- 10 vídeos/dia ≈ 2 GB/dia ≈ $20/mês
- 3 vídeos/dia ≈ 600 MB/dia ≈ $6/mês

### Combinando Proxy + Cookies

Para máxima confiabilidade, use ambos:

```env
CLIPBUILDER_YTDLP_PROXY=socks5://usuario:senha@proxy-host:1080
CLIPBUILDER_YTDLP_COOKIES_FILE=/app/data/cookies.txt
```

O sistema tenta cookies+PO+proxy primeiro. Se falhar, tenta cookies+proxy, depois PO+proxy, etc.

---

## Método 3: PO Token (Automático / Fallback)

O PO Token (Proof of Origin) é gerado automaticamente pelo plugin `bgutil-ytdlp-pot-provider` instalado na imagem Docker. **Não requer configuração.**

Funciona em muitos casos, mas pode falhar se o IP do VPS estiver na blacklist do YouTube. É usado automaticamente como fallback quando cookies não estão configurados.

---

## Estratégias de Download (Ordem de Tentativas)

O ClipBuilder tenta múltiplas estratégias em sequência. Se uma falha, tenta a próxima:

```
1. Cookies + PO Token + Proxy    (se cookies E proxy configurados)
2. Cookies + Proxy               (sem PO Token, caso o plugin cause conflito)
3. Cookies only                  (se cookies configurados mas sem proxy)
4. PO Token + Proxy              (se proxy configurado)
5. PO Token only                 (sempre disponível via plugin)
6. Bare (sem nada)               (último recurso)
```

Estratégias duplicadas são automaticamente removidas (ex: se não há proxy, estratégias com e sem proxy são equivalentes).

---

## Troubleshooting

### "O YouTube bloqueou o download do vídeo"

1. Verifique se os cookies estão instalados:
   ```bash
   ./setup_youtube_cookies.sh --test
   ```

2. Se não estiverem, instale-os:
   ```bash
   ./setup_youtube_cookies.sh
   ```

3. Se os cookies existem mas o teste falha, re-exporte do navegador (podem estar expirados).

### "Sign in to confirm you're not a bot"

Soluções (por prioridade):
1. Instale cookies → `./setup_youtube_cookies.sh`
2. Adicione um proxy residencial → `CLIPBUILDER_YTDLP_PROXY=...`
3. Espere 15-30 minutos e tente novamente (pode ser throttle temporário)

### "yt-dlp timed out"

O download pode travar em conexões lentas ou vídeos grandes. O timeout padrão é 10 minutos. Se necessário, vídeos muito longos podem precisar de mais tempo.

### Ver logs detalhados do yt-dlp

```bash
docker compose logs backend | grep -i "yt-dlp"
docker compose logs backend | grep -i "youtube"
docker compose logs backend | grep -i "strategy"
```

### Forçar atualização do yt-dlp

O yt-dlp é atualizado a cada build do Docker. Para forçar:

```bash
docker compose build --no-cache backend
docker compose up -d backend
```

### Remover cookies instalados

```bash
./setup_youtube_cookies.sh --remove
```

---

## Variáveis de Ambiente (Referência Completa)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `CLIPBUILDER_YTDLP_COOKIES_FILE` | `/app/data/cookies.txt` | Caminho para cookies.txt dentro do container |
| `CLIPBUILDER_YTDLP_PROXY` | _(vazio)_ | URL de proxy (socks5:// ou http://) |
| `CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER` | _(vazio)_ | Nome do navegador para extrair cookies (ex: firefox, chrome) |
| `CLIPBUILDER_YTDLP_COOKIES_FROM_BROWSER_ARGS` | _(vazio)_ | Args extras para cookies do navegador |
| `CLIPBUILDER_YTDLP_PO_TOKEN_EXTRACTOR_URL` | _(vazio)_ | URL de servidor bgutil externo para PO Tokens |

---

## Segurança

- **cookies.txt** contém uma sessão autenticada do YouTube. Trate como uma senha:
  - Não commite no git (já está no `.gitignore`)
  - Use uma conta Google dedicada, não sua conta pessoal
  - O arquivo é armazenado no volume Docker `backend_data`
- **Proxy credentials** estão no `.env`, que já está no `.gitignore`
- **Acesso ao servidor**: qualquer pessoa com acesso root ao VPS pode ler os cookies

---

## Resumo de Comandos

```bash
# Setup interativo (guia completo)
./setup_youtube_cookies.sh

# Instalar cookies diretamente
./setup_youtube_cookies.sh /caminho/para/cookies.txt

# Testar cookies instalados
./setup_youtube_cookies.sh --test

# Remover cookies
./setup_youtube_cookies.sh --remove

# Ver ajuda
./setup_youtube_cookies.sh --help
```
