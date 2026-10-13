# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Segurança
- **Token da API do Cloudflare removido do versionamento.** `cloudflare.ini` era
  um arquivo rastreado no Git contendo o token real; agora está no `.gitignore`,
  com `cloudflare.ini.example` como modelo. **O token precisa ser rotacionado no
  painel do Cloudflare** — ele permanece no histórico do repositório.
- Postgres deixou de publicar a porta `5432` no host da VPS; o banco agora é
  acessível apenas pela rede interna do Compose.
- `.gitignore` reescrito: os marcadores de conflito de merge não resolvidos
  faziam com que regras de `*.pem`/`*.key` não fossem aplicadas de forma confiável.
- Container do backend passou a rodar como usuário sem privilégios
  (`clipbuilder`) em vez de root, com `gosu` no entrypoint ajustando a posse dos
  volumes montados.
- `tempfile.mktemp()` (sujeito a corrida) substituído por `mkstemp()` na
  extração de áudio; conversão para PDF passou a usar um diretório temporário
  gerenciado em vez de caminhos fixos em `/tmp`.
- Removida uma segunda definição de `require_gemini_permission` que sobrescrevia
  a checagem de `can_use_gemini` por uma versão vazia. A dependência não estava
  aplicada a nenhuma rota, então não havia brecha ativa — mas o próximo uso de
  `RequireGemini` teria passado sem validar nada.
- nginx: `Permissions-Policy`, `Cross-Origin-Opener-Policy` e uma
  `Content-Security-Policy` em modo *Report-Only* (pronta para virar bloqueante
  após validação em produção).

### Corrigido
- **`/describe-gif`, `/format-and-export` e `/generate-documentation` estavam
  quebrados.** Os três referenciavam `x_gemini_key` sem declará-lo como header, e
  dois chamavam funções que não existiam (`format_document_like_template_with_gemini`,
  `generate_structured_documentation_with_gemini`).
- `generate_structured_documentation` e `format_document_like_template` ainda
  usavam a API estilo OpenAI (`client.chat.completions.create`) e um
  `_get_gemini_client` removido junto com o provider Groq; migradas para o SDK
  do `google-generativeai`.
- Exportar PDF ou HTML pelo Dashboard lançava `ReferenceError`:
  `downloadMarkdownAsPdf` e `downloadMarkdownAsHtml` não estavam importados.
- `/export` lançava `NameError` ao receber passos: o tipo `StepPayload` usado por
  `_parse_steps` não existia mais.
- Tabela de custos do admin tinha a chave `"gemini"` duplicada (resquício de um
  find/replace de `groq` → `gemini`), fazendo o custo por requisição ser
  registrado como 0.001 em vez de 0.002.
- Driver do Postgres explicitado como `psycopg2` na URL de conexão. A partir do
  SQLAlchemy 2.1 o esquema `postgresql://` passou a resolver para `psycopg` (v3),
  que não é dependência do projeto — o próximo `docker compose build` derrubaria
  o backend com `ModuleNotFoundError`.
- Fragmento de código inalcançável em `enhance.py`, restante de um merge.
- Exceções encadeadas (`raise ... from`) em 20 pontos onde a causa original se
  perdia.

### Desempenho
- **Trabalho bloqueante saiu do event loop.** `/export`, `/enhance-document`,
  `/markdown-to-docx`, `/markdown-to-pdf`, `/markdown-to-html`,
  `/format-and-export` e `/generate-documentation` executavam LibreOffice,
  python-docx e chamadas síncronas ao Gemini na thread do loop; com um único
  worker uvicorn, um export de PDF congelava a API para todos. O mesmo valia para
  a extração de frame/áudio e o corte de clipe em `/videos/{id}/smart-text`.
- Conversões de documento passaram a ter teto de concorrência
  (`CLIPBUILDER_EXPORT_CONCURRENCY`, padrão 2) para não estourar a memória da VPS.
- LibreOffice passou a usar um perfil de usuário por conversão — sem isso, duas
  conversões simultâneas disputariam `~/.config/libreoffice` e uma falharia.
- **Frontend com code splitting**: rotas em `React.lazy` e vendors separados em
  chunks. O primeiro carregamento caiu de 297 KB para 106 KB comprimidos (-64%);
  quem não é admin não baixa mais o painel administrativo nem o editor de imagem.
- nginx com gzip habilitado.

### Adicionado
- Suíte de testes do backend (`pytest`): smoke da aplicação, funções puras e um
  teste de análise estática que impede chamadas bloqueantes de voltarem para
  dentro de handlers `async`.
- Lint configurado dos dois lados: `ruff` (backend) e `eslint` + `prettier`
  (frontend), ambos sem erros.
- Workflow `ci.yml` (lint + testes + build das imagens Docker) rodando em todo
  push e PR; o deploy agora depende dele e não sobe nada sem o CI verde.
- Deploy com rollback automático: se o build ou o smoke test falhar, a VPS volta
  para o commit anterior.
- `.env.example` documentando todas as variáveis de ambiente do projeto.
- `HEALTHCHECK` nos containers de backend e frontend; o deploy espera o backend
  ficar saudável em vez de um `sleep` fixo.
- Rotação de logs dos containers (10 MB × 3 arquivos) e `restart: unless-stopped`.

### Removido
- `backend/app/main.py`: segundo entrypoint FastAPI, completo mas nunca
  referenciado — o Docker sempre rodou `main:app`.
- Componentes React órfãos: `auth/AdminRoute`, `auth/ProtectedRoute`,
  `auth/ClerkProviderWrapper`, `shared/Button` e `components/SettingsModal`.
- Arquivos de trabalho que estavam versionados: `Wolbito.docx`, `groq_matches.txt`,
  `debug_index.html`, `teste.py`, `Aba Validação de Usuários Clerk` e o template
  DOCX antigo.
- Workflow `teste.yml`, que apenas imprimia uma mensagem.

## [Anterior]

### Adicionado
- Badge de estrelas, issues, forks e PRs do GitHub no cabeçalho
- Badge do PydanticAI na seção de Tech Stack
- Badge do Mercado Pago na seção de Exportação/Pagamentos
- Links de navegação expandidos incluindo Roadmap, FAQ e Arquitetura
- Seção **🚀 Primeiros Passos** com guia passo-a-passo para novos usuários
- Seção **🗺️ Roadmap** com funcionalidades implementadas, em desenvolvimento e planejadas
- Seção **❓ FAQ** com 8 perguntas frequentes em formato de acordeão
- Seção **🔧 Solução de Problemas** com 12 problemas comuns e suas soluções
- Seção **🤝 Contribuição** com instruções para contribuir, reportar bugs e sugerir features
- Rodapé expandido com badges de redes sociais, links úteis e agradecimentos
- Instruções detalhadas sobre logs do Docker Compose
- Dicas de atalhos de teclado e melhores práticas
- Avisos importantes sobre configuração de admin no primeiro acesso

### Modificado
- Atualizado porta do frontend de `8081` para `80` em produção (conforme docker-compose.yml)
- Corrigido diagrama de arquitetura refletindo porta 80 para frontend
- URLs de acesso atualizadas para `http://localhost` (porta 80)
- Melhorada seção de configuração de variáveis de ambiente com exemplos mais completos
- Separação clara entre `.env` raiz e `backend/.env`
- Adicionadas variáveis obrigatórias faltantes: `DB_PASSWORD`, `ADMIN_PASSWORD`
- Expandida seção de configuração SMTP com exemplo completo
- Melhorada descrição do modelo Google Gemini (2.0 Flash)
- Links de navegação reorganizados e expandidos
- Rodapé reformulado com mais informações e links úteis
- Seção de licença aprimorada com copyright

### Corrigido
- Badge duplicado do PydanticAI removido
- URLs quebradas de acesso à aplicação
- Informações desatualizadas sobre portas de acesso
- Falta de documentação sobre variáveis de ambiente obrigatórias
- Links de navegação incompletos no início do README

## [1.0.0] - 2024-01-XX (Inicial)

### Adicionado
- README inicial com descrição do projeto
- Screenshots do dashboard, editor e painéis admin
- Documentação de funcionalidades principais
- Seção de Tech Stack com badges
- Instruções básicas de instalação
- Diagrama de arquitetura
- Seção de fluxo de uso
- Licença MIT
- Exemplo de documento exportado

---

**Legenda:**
- `Adicionado` para novas funcionalidades
- `Modificado` para mudanças em funcionalidades existentes
- `Depreciado` para funcionalidades que serão removidas
- `Removido` para funcionalidades removidas
- `Corrigido` para correção de bugs
- `Segurança` para vulnerabilidades corrigidas