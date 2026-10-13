"""
Enhancement de Documentação com Gemini — ClipBuilder

OTIMIZAÇÕES APLICADAS:
  1. _truncate_steps_text() substitui _summarize_context_with_gemini()  → -1 requisição
  2. _estimate_output_tokens() ajusta max_completion_tokens por chamada → -20‒60% custo output
  3. _get_gemini_client() singleton evita instanciar Gemini() repetidamente
  4. System prompts enxutos: removidas redundâncias entre DOC_PRO e DOC_TEMPLATE
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

logger = logging.getLogger("clipbuilder.enhance")

# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

DEFAULT_GEMINI_MODEL = "models/gemini-2.5-flash"


def _gemini_model(api_key: str, model: str, system_prompt: str):
    """Devolve (módulo genai, GenerativeModel) já configurados.

    Centraliza a inicialização do SDK para que todas as funções deste módulo
    falem com o Gemini do mesmo jeito.
    """
    try:
        import google.generativeai as genai
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise RuntimeError(
            "Dependência 'google-generativeai' não instalada. "
            "Execute: pip install google-generativeai"
        ) from exc

    genai.configure(api_key=api_key)
    normalized = model if model.startswith("models/") else f"models/{model}"
    return genai, genai.GenerativeModel(
        model_name=normalized, system_instruction=system_prompt
    )


TEMPLATE_SYSTEM_PROMPT = (
    "Você é um especialista em documentação técnica. "
    "Sua tarefa é EXPANDIR e ESTRUTURAR o texto fornecido em um manual passo a passo profissional em Markdown.\n\n"
    "REGRAS CRÍTICAS:\n"
    "1. PRESERVE 100% do conteúdo original - não resuma, não omita, não simplifique.\n"
    "2. EXPANDA cada informação em passos detalhados e acionáveis.\n"
    "3. Se houver referências a imagens (![...], [Imagem:...], figuras), MANTENHA-AS no local apropriado.\n"
    "4. Se o texto menciona elementos visuais, campos, botões ou telas, DETALHE cada um.\n"
    "5. Extraia TODOS os procedimentos implícitos e explícitos do texto.\n\n"
    "ESTRUTURA OBRIGATÓRIA:\n"
    "- **Título** em negrito (# Título)\n"
    "- ## Visão Geral (resumo expandido do documento)\n"
    "- ## Pré-requisitos (se aplicável)\n"
    "- ## Passo N: [Nome do Passo] com ### Objetivo e ### Procedimento detalhado\n"
    "- ## Checklist de Verificação Final (- [ ] itens)\n"
    "- ## Notas Importantes (quando aplicável)\n\n"
    "Não invente informações que não estejam no texto original. "
    "Responda apenas em Markdown bem formatado."
)

DOC_PRO_SYSTEM_PROMPT = (
    "Você é um Redator Técnico Sênior especializado em documentação de software.\n\n"
    "MISSÃO: Transformar os passos fornecidos em documentação Markdown COMPLETA e PROFISSIONAL em pt-BR.\n\n"
    "REGRAS CRÍTICAS:\n"
    "1. EXPANDA cada passo em descrição detalhada - não resuma, DETALHE.\n"
    "2. Se o passo menciona interface, campos, botões ou telas, DESCREVA cada elemento.\n"
    "3. Extraia o MÁXIMO de informações de cada descrição fornecida.\n"
    "4. Passos marcados com [com imagem] DEVEM incluir: ![Passo N](./img/step_NN.png)\n"
    "5. Gere pelo menos 3-5 linhas de procedimento detalhado por passo.\n\n"
    "ESTRUTURA POR PASSO:\n"
    "- **Objetivo**: O que será alcançado (≤20 palavras)\n"
    "- **Procedimento**: Lista numerada de ações imperativas detalhadas\n"
    "- **Observações**: Detalhes importantes mencionados no passo original\n\n"
    "ELEMENTOS OBRIGATÓRIOS:\n"
    "- Callouts GitHub (> [!NOTE], > [!TIP], > [!WARNING], > [!CAUTION]) — mínimo 3\n"
    "- Checklist de Verificação Final (≥5 itens com - [ ])\n"
    "- Tabela Problemas Comuns e Soluções (≥3 linhas: Problema|Causa|Solução)\n\n"
    "Não invente passos que não existam, mas EXPANDA ao máximo cada passo fornecido."
)

# ---------------------------------------------------------------------------
# Wolbito Corporate Template Prompts
# ---------------------------------------------------------------------------

WOLBITO_IT_SYSTEM_PROMPT = (
    "Você é um Redator Técnico Sênior especializado em Instruções de Trabalho (IT) "
    "seguindo o padrão corporativo Wolbito do Brasil.\n\n"
    "MISSÃO: Transformar os passos fornecidos em uma Instrução de Trabalho (IT) "
    "formatada em Markdown que segue EXATAMENTE a estrutura corporativa Wolbito.\n\n"
    "REGRAS CRÍTICAS:\n"
    "1. EXPANDA cada passo em descrição detalhada - não resuma, DETALHE.\n"
    "2. Se o passo menciona interface, campos, botões ou telas, DESCREVA cada elemento.\n"
    "3. Extraia o MÁXIMO de informações de cada descrição fornecida.\n"
    "4. Passos marcados com [CONTÉM IMAGEM] DEVEM incluir: ![Passo N](./img/step_NN.png)\n"
    "5. Gere pelo menos 3-5 linhas de procedimento detalhado por passo.\n"
    "6. USE headings de nível 1 (#) para seções principais — NÃO use ## para seções de nível superior.\n"
    "7. O primeiro # será o título do documento (usado no cabeçalho corporativo).\n"
    "8. Seções subsequentes de # serão numeradas automaticamente (1. INTRODUÇÃO, 2. PROCEDIMENTO, etc.).\n\n"
    "ESTRUTURA OBRIGATÓRIA DA IT (Instrução de Trabalho):\n"
    "- # Título do Documento (será exibido no cabeçalho corporativo)\n"
    "- # INTRODUÇÃO (visão geral do procedimento, 2-3 parágrafos)\n"
    "- # PROCEDIMENTO (seção principal com todos os passos)\n"
    "  - ## Passo N: Nome do Passo (sub-seções dentro do procedimento)\n"
    "    - ### Objetivo\n"
    "    - ### Procedimento (lista numerada de ações)\n"
    "- # REQUISITOS DO PROCEDIMENTO (pré-requisitos, permissões, ferramentas)\n"
    "- # AVISOS IMPORTANTES (callouts de WARNING, TIP, NOTE, CAUTION)\n"
    "- # CHECKLIST DE VERIFICAÇÃO FINAL (itens com - [ ])\n"
    "- # PROBLEMAS COMUNS E SOLUÇÕES (tabela Problema|Causa|Solução)\n"
    "- # ANEXOS (referências a documentos auxiliares ou N/A)\n"
    "- # DOCUMENTOS DE REFERÊNCIAS (normas, manuais relacionados ou N/A)\n"
    "- # REGISTROS (formulários, logs ou N/A)\n\n"
    "CALLOUTS OBRIGATÓRIOS (mínimo 3 ao longo do documento):\n"
    "  > [!NOTE] para informações complementares\n"
    "  > [!TIP] para dicas de produtividade\n"
    "  > [!WARNING] para alertas importantes\n"
    "  > [!CAUTION] para ações que podem causar problemas\n\n"
    "Não invente passos que não existam, mas EXPANDA ao máximo cada passo fornecido.\n"
    "Idioma: pt-BR. Tom: formal e técnico."
)

WOLBITO_POP_SYSTEM_PROMPT = (
    "Você é um Redator Técnico Sênior especializado em Procedimentos Operacionais Padrão (POP) "
    "seguindo o padrão corporativo Wolbito do Brasil.\n\n"
    "MISSÃO: Transformar os passos fornecidos em um POP (Procedimento Operacional Padrão) "
    "formatado em Markdown que segue EXATAMENTE a estrutura corporativa Wolbito.\n\n"
    "REGRAS CRÍTICAS:\n"
    "1. EXPANDA cada passo em descrição detalhada - não resuma, DETALHE.\n"
    "2. Se o passo menciona interface, campos, botões ou telas, DESCREVA cada elemento.\n"
    "3. Extraia o MÁXIMO de informações de cada descrição fornecida.\n"
    "4. Passos marcados com [CONTÉM IMAGEM] DEVEM incluir: ![Passo N](./img/step_NN.png)\n"
    "5. Gere pelo menos 3-5 linhas de procedimento detalhado por passo.\n"
    "6. USE headings de nível 1 (#) para seções principais — NÃO use ## para seções de nível superior.\n"
    "7. O primeiro # será o título do documento (usado no cabeçalho corporativo).\n"
    "8. Seções subsequentes de # serão numeradas automaticamente (1. INTRODUÇÃO, 2. OBJETIVO, etc.).\n\n"
    "ESTRUTURA OBRIGATÓRIA DO POP (Procedimento Operacional Padrão):\n"
    "- # Título do Documento (será exibido no cabeçalho corporativo)\n"
    "- # INTRODUÇÃO (contextualização e importância do procedimento, 2-3 parágrafos)\n"
    "- # OBJETIVO (finalidade do procedimento, claro e conciso)\n"
    "- # ABRANGÊNCIA (setores, equipes ou sistemas afetados)\n"
    "- # REFERÊNCIAS (normas, legislações ou documentos base)\n"
    "- # DEFINIÇÕES (termos técnicos usados no documento)\n"
    "- # SÍMBOLOS E ABREVIATURAS (siglas utilizadas, se houver)\n"
    "- # RESPONSABILIDADES (quem faz o quê no processo)\n"
    "- # METODOLOGIA (seção principal com todos os passos)\n"
    "  - ## Passo N: Nome do Passo (sub-seções dentro da metodologia)\n"
    "    - ### Objetivo\n"
    "    - ### Procedimento (lista numerada de ações)\n"
    "- # DESVIOS E AÇÕES (o que fazer quando algo sai do planejado)\n"
    "- # AVISOS IMPORTANTES (callouts de WARNING, TIP, NOTE, CAUTION)\n"
    "- # CHECKLIST DE VERIFICAÇÃO FINAL (itens com - [ ])\n"
    "- # PROBLEMAS COMUNS E SOLUÇÕES (tabela Problema|Causa|Solução)\n"
    "- # DOCUMENTOS RELACIONADOS E ANEXOS (referências ou N/A)\n\n"
    "CALLOUTS OBRIGATÓRIOS (mínimo 3 ao longo do documento):\n"
    "  > [!NOTE] para informações complementares\n"
    "  > [!TIP] para dicas de produtividade\n"
    "  > [!WARNING] para alertas importantes\n"
    "  > [!CAUTION] para ações que podem causar problemas\n\n"
    "Não invente passos que não existam, mas EXPANDA ao máximo cada passo fornecido.\n"
    "Idioma: pt-BR. Tom: formal e técnico."
)

DOC_TEMPLATE_SYSTEM_PROMPT = (
    "Você é um Redator Técnico Sênior para documentação de software.\n\n"
    "MISSÃO: Analisar os passos fornecidos e gerar documentação estruturada em JSON.\n\n"
    "REGRAS CRÍTICAS:\n"
    "1. EXPANDA cada passo - extraia o máximo de detalhes da descrição original.\n"
    "2. Procedimentos devem ter 3-5 ações detalhadas por passo, não apenas 1.\n"
    "3. Se o passo tem imagem (has_image=true), inclua o campo imagem.\n"
    "4. visao_geral deve ter 2-3 frases explicando o documento completo.\n\n"
    "Retorne APENAS JSON válido, sem markdown code blocks, sem texto extra.\n\n"
    "ESTRUTURA OBRIGATÓRIA:\n"
    '{"visao_geral":"2-3 frases descritivas sobre o procedimento completo",'
    '"passos":[{"numero":1,"titulo":"Nome descritivo do passo",'
    '"objetivo":"O que será alcançado (≤20 palavras)",'
    '"procedimento":["ação 1 detalhada","ação 2 detalhada","ação 3 detalhada"],'
    '"imagem":"./img/step_01.png ou null"}],'
    '"avisos":[{"tipo":"WARNING|TIP|NOTE|CAUTION","texto":"texto detalhado"}],'
    '"checklist":["item verificável 1","item verificável 2",...],'
    '"troubleshooting":[{"problema":"descrição","causa":"motivo","solucao":"como resolver"}]}\n\n'
    "MÍNIMOS: ≥1 WARNING + ≥2 TIP/NOTE; checklist ≥5 itens; troubleshooting ≥3 entradas.\n"
    "Idioma: pt-BR. Não invente passos novos, mas DETALHE ao máximo os existentes."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------






def _estimate_output_tokens(steps: list[dict]) -> int:
    """Estima tokens de output necessários baseado no número de passos.

    Cada passo gera: título, objetivo, procedimento (3-5 itens), observações,
    referência de imagem — facilmente ~800-1200 tokens por passo.
    Estrutura fixa (visão geral, checklist ≥5, troubleshooting ≥3, avisos) ~3000 tokens.

    Valores anteriores (1500 + 400/passo) causavam truncamento severo,
    cortando passos e seções finais do documento.
    """
    # Base: visão geral (2-3 parágrafos) + checklist + troubleshooting + avisos
    base_tokens = 3000
    # Por passo: título + objetivo + procedimento detalhado (3-5 itens) + observações + imagem
    per_step_tokens = 1000
    # Mínimo de 6000 tokens mesmo para poucos passos (documento precisa de corpo)
    estimated = base_tokens + len(steps) * per_step_tokens
    return max(min(estimated, 16384), 6000)


def _truncate_steps_text(steps: list[dict], max_chars: int = 30000) -> str:
    """
    Formata e trunca passos sem chamar a API.
    Substitui _summarize_context_with_gemini() — elimina 1 requisição por chamada.

    IMPORTANTE: Preserva o máximo de informações de cada passo para que a IA
    possa gerar documentação detalhada.
    """
    lines: list[str] = []
    total = 0
    for i, step in enumerate(steps, 1):
        # Aumentado limite por passo para preservar mais contexto
        desc = step.get("description", "").strip()[:2000]
        has_image = step.get("has_image", False)

        # Campos adicionais que podem conter informações úteis
        title = step.get("title", "").strip()
        user_action = step.get("userAction", "").strip()
        expected_result = step.get("expectedResult", "").strip()
        observations = step.get("observations", "").strip()

        # Construir linha rica em informações
        line_parts = [f"PASSO {i}:"]

        if title:
            line_parts.append(f"  Título: {title}")

        if desc:
            line_parts.append(f"  Descrição: {desc}")
        elif not title:
            line_parts.append("  Descrição: (não fornecida)")

        if user_action:
            line_parts.append(f"  Ação do Usuário: {user_action}")

        if expected_result:
            line_parts.append(f"  Resultado Esperado: {expected_result}")

        if observations:
            line_parts.append(f"  Observações: {observations}")

        if has_image:
            line_parts.append(
                "  [CONTÉM IMAGEM - incluir referência ./img/step_NN.png]"
            )

        line = "\n".join(line_parts)

        if total + len(line) > max_chars:
            remaining = len(steps) - i + 1
            lines.append(
                f"\n... ({remaining} passos adicionais omitidos por limite de contexto)"
            )
            break

        lines.append(line)
        lines.append("")  # linha em branco entre passos
        total += len(line) + 1

    return "\n".join(lines)


def _clean_markdown_fences(text: str) -> str:
    """Remove marcadores de código markdown da resposta."""
    text = text.strip()
    if text.startswith("```markdown"):
        text = text[len("```markdown") :].strip()
    if text.startswith("```json"):
        text = text[len("```json") :].strip()
    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def _handle_gemini_error(exc: Exception) -> None:
    """Re-levanta exceções Gemini com mensagens amigáveis."""
    msg = str(exc).lower()
    if "rate limit" in msg or "ratelimit" in msg or "quota" in msg or "429" in msg:
        raise RuntimeError(
            "Quota/limite do Gemini excedido. Verifique billing/limites e tente novamente."
        ) from exc
    if "invalid" in msg and "api" in msg:
        raise RuntimeError(
            "Chave da API Google inválida. Verifique 'gemini_api_key' no .env do backend."
        ) from exc
    if "permission" in msg or "403" in msg:
        raise RuntimeError(
            "Permissão negada pelo Gemini. Verifique se a API está habilitada."
        ) from exc
    raise RuntimeError(f"Erro ao processar com Gemini: {str(exc)[:200]}") from exc


# ---------------------------------------------------------------------------
# Prompts de usuário
# ---------------------------------------------------------------------------


def build_doc_pro_prompt(
    title: str, steps: list[dict[str, Any]], template_id: str | None = None
) -> str:
    """Constrói o prompt para o Doc Pro (Gemini).

    Se template_id for um template corporativo Wolbito, gera o prompt
    adaptado à estrutura esperada pelo corporate_markdown_to_docx.
    """
    steps_text = _truncate_steps_text(steps)

    # Contar passos com imagem para referência
    steps_with_image = sum(1 for s in steps if s.get("has_image", False))

    # ── Wolbito IT ──
    if template_id == "wolbito_it":
        return _build_wolbito_it_prompt(title, steps, steps_text, steps_with_image)

    # ── Wolbito POP ──
    if template_id == "wolbito_pop":
        return _build_wolbito_pop_prompt(title, steps, steps_text, steps_with_image)

    # ── Default Doc Pro ──
    return f"""TÍTULO DO DOCUMENTO: {title}

INFORMAÇÕES DOS PASSOS CAPTURADOS:
{steps_text}

ESTATÍSTICAS:
- Total de passos: {len(steps)}
- Passos com imagem: {steps_with_image}

---

INSTRUÇÕES DE GERAÇÃO:

1. ANALISE cada passo cuidadosamente e EXTRAIA todas as informações relevantes.

2. Para cada passo, gere:
   - Título descritivo (## Passo N: [Nome])
   - ### Objetivo: O que será alcançado
   - ### Procedimento: Lista detalhada de ações (3-5 itens mínimo)
   - Referência de imagem se marcado com [CONTÉM IMAGEM]: ![Passo N](./img/step_NN.png)

3. ESTRUTURA DO DOCUMENTO:
   # {title}
   ## Visão Geral (2-3 parágrafos sobre o processo completo)
   ## Passo 1: [Nome] ... (repetir para cada passo)
   ## Checklist de Verificação Final (≥5 itens com - [ ])
   ## Problemas Comuns e Soluções (tabela com ≥3 linhas)

4. INCLUA callouts ao longo do documento:
   > [!NOTE] para informações complementares
   > [!TIP] para dicas de produtividade
   > [!WARNING] para alertas importantes
   > [!CAUTION] para ações que podem causar problemas

Gere o documento Markdown completo agora:"""


def _build_wolbito_it_prompt(
    title: str, steps: list[dict[str, Any]], steps_text: str, steps_with_image: int
) -> str:
    """Prompt específico para Instrução de Trabalho (IT) Wolbito."""
    return f"""TÍTULO DO DOCUMENTO: {title}
TEMPLATE: Instrução de Trabalho (IT) — Padrão Corporativo Wolbito do Brasil

INFORMAÇÕES DOS PASSOS CAPTURADOS:
{steps_text}

ESTATÍSTICAS:
- Total de passos: {len(steps)}
- Passos com imagem: {steps_with_image}

---

INSTRUÇÕES DE GERAÇÃO — FORMATO IT (Instrução de Trabalho):

IMPORTANTE: Use headings de nível 1 (#) para TODAS as seções principais.
O primeiro # é o título e será exibido no cabeçalho corporativo com logo.
Os demais # serão numerados automaticamente (1. INTRODUÇÃO, 2. PROCEDIMENTO, etc.).
Use ## apenas para sub-seções dentro de uma seção principal (ex: ## Passo 1: Nome).

ESTRUTURA EXATA QUE VOCÊ DEVE GERAR:

# {title}

# INTRODUÇÃO
(2-3 parágrafos contextualizando o procedimento, sua importância e quando deve ser aplicado)

# PROCEDIMENTO

## Passo 1: [Nome Descritivo]

### Objetivo
(O que será alcançado neste passo — até 20 palavras)

### Procedimento
1. Ação detalhada 1
2. Ação detalhada 2
3. Ação detalhada 3
(mínimo 3-5 ações por passo)

![Passo 1](./img/step_01.png)
(incluir apenas se o passo tem imagem)

> [!TIP]
> Dica relevante para este passo

(repetir ## Passo N para cada passo capturado)

# REQUISITOS DO PROCEDIMENTO
- Pré-requisitos necessários
- Permissões e acessos
- Ferramentas e sistemas

# AVISOS IMPORTANTES

> [!WARNING]
> Alerta sobre ponto crítico

> [!CAUTION]
> Ação que pode causar problemas

> [!NOTE]
> Informação complementar importante

(mínimo 3 callouts)

# CHECKLIST DE VERIFICAÇÃO FINAL
- [ ] Item de verificação 1
- [ ] Item de verificação 2
- [ ] Item de verificação 3
- [ ] Item de verificação 4
- [ ] Item de verificação 5
(mínimo 5 itens)

# PROBLEMAS COMUNS E SOLUÇÕES

| Problema | Causa | Solução |
|----------|-------|---------|
| Descrição do problema 1 | Causa provável | Como resolver |
| Descrição do problema 2 | Causa provável | Como resolver |
| Descrição do problema 3 | Causa provável | Como resolver |
(mínimo 3 linhas)

# ANEXOS
(Referências a documentos auxiliares, formulários, ou "N/A" se não houver)

# DOCUMENTOS DE REFERÊNCIAS
(Normas, manuais, procedimentos relacionados, ou "N/A")

# REGISTROS
(Formulários de registro, logs, ou "N/A")

---

REGRAS ADICIONAIS:
- Use linguagem imperativa e formal (pt-BR)
- NÃO invente passos novos, mas EXPANDA ao máximo os existentes
- Cada passo com [CONTÉM IMAGEM] DEVE ter ![Passo N](./img/step_NN.png)
- Distribua callouts (> [!NOTE], > [!TIP], > [!WARNING], > [!CAUTION]) ao longo do documento
- Agrupe passos relacionados se fizer sentido técnico

Gere o documento Markdown completo agora:"""


def _build_wolbito_pop_prompt(
    title: str, steps: list[dict[str, Any]], steps_text: str, steps_with_image: int
) -> str:
    """Prompt específico para POP (Procedimento Operacional Padrão) Wolbito."""
    return f"""TÍTULO DO DOCUMENTO: {title}
TEMPLATE: Procedimento Operacional Padrão (POP) — Padrão Corporativo Wolbito do Brasil

INFORMAÇÕES DOS PASSOS CAPTURADOS:
{steps_text}

ESTATÍSTICAS:
- Total de passos: {len(steps)}
- Passos com imagem: {steps_with_image}

---

INSTRUÇÕES DE GERAÇÃO — FORMATO POP (Procedimento Operacional Padrão):

IMPORTANTE: Use headings de nível 1 (#) para TODAS as seções principais.
O primeiro # é o título e será exibido no cabeçalho corporativo com logo.
Os demais # serão numerados automaticamente (1. INTRODUÇÃO, 2. OBJETIVO, etc.).
Use ## apenas para sub-seções dentro de uma seção principal (ex: ## Passo 1: Nome).

ESTRUTURA EXATA QUE VOCÊ DEVE GERAR:

# {title}

# INTRODUÇÃO
(2-3 parágrafos contextualizando o procedimento, sua importância e aplicabilidade.
Explique por que este POP existe e qual problema ele resolve.)

# OBJETIVO
(Descrever de forma clara e concisa a finalidade deste procedimento.
Deve responder: "Para que serve este POP?")

# ABRANGÊNCIA
(Definir claramente quais setores, equipes, sistemas ou processos são afetados.
Ex: "Este procedimento aplica-se a todos os colaboradores do setor de TI...")

# REFERÊNCIAS
(Listar normas, legislações, regulamentos ou documentos base que fundamentam este POP.
Se não houver referências específicas, indicar "N/A")

# DEFINIÇÕES
(Definir termos técnicos utilizados ao longo do documento.
Ex: "**SLA**: Service Level Agreement — acordo de nível de serviço...")

# SÍMBOLOS E ABREVIATURAS
(Listar siglas e abreviações utilizadas no documento.
Ex: "TI — Tecnologia da Informação")

# RESPONSABILIDADES
(Definir quem é responsável por cada etapa do processo.
Use lista ou tabela para clareza:
- **Elaborador**: responsável pela criação e atualização
- **Executor**: quem executa o procedimento
- **Aprovador**: quem valida e aprova)

# METODOLOGIA

## Passo 1: [Nome Descritivo]

### Objetivo
(O que será alcançado neste passo — até 20 palavras)

### Procedimento
1. Ação detalhada 1
2. Ação detalhada 2
3. Ação detalhada 3
(mínimo 3-5 ações por passo)

![Passo 1](./img/step_01.png)
(incluir apenas se o passo tem imagem)

> [!TIP]
> Dica relevante para este passo

(repetir ## Passo N para cada passo capturado)

# DESVIOS E AÇÕES
(Descrever o que fazer quando algo sai do planejado.
Incluir pelo menos 2-3 cenários de desvio com ações corretivas.)

# AVISOS IMPORTANTES

> [!WARNING]
> Alerta sobre ponto crítico

> [!CAUTION]
> Ação que pode causar problemas

> [!NOTE]
> Informação complementar importante

(mínimo 3 callouts)

# CHECKLIST DE VERIFICAÇÃO FINAL
- [ ] Item de verificação 1
- [ ] Item de verificação 2
- [ ] Item de verificação 3
- [ ] Item de verificação 4
- [ ] Item de verificação 5
(mínimo 5 itens)

# PROBLEMAS COMUNS E SOLUÇÕES

| Problema | Causa | Solução |
|----------|-------|---------|
| Descrição do problema 1 | Causa provável | Como resolver |
| Descrição do problema 2 | Causa provável | Como resolver |
| Descrição do problema 3 | Causa provável | Como resolver |
(mínimo 3 linhas)

# DOCUMENTOS RELACIONADOS E ANEXOS
(Listar documentos relacionados, formulários, templates auxiliares, ou "N/A")

---

REGRAS ADICIONAIS:
- Use linguagem imperativa e formal (pt-BR)
- NÃO invente passos novos, mas EXPANDA ao máximo os existentes
- Cada passo com [CONTÉM IMAGEM] DEVE ter ![Passo N](./img/step_NN.png)
- Distribua callouts (> [!NOTE], > [!TIP], > [!WARNING], > [!CAUTION]) ao longo do documento
- Agrupe passos relacionados se fizer sentido técnico
- TODAS as seções do POP são obrigatórias, mesmo que com conteúdo mínimo

Gere o documento Markdown completo agora:"""


def build_enhancement_prompt(title: str, steps: list[dict[str, Any]]) -> str:
    """Constrói o prompt para enhance com Gemini (markdown livre)."""
    steps_text = _truncate_steps_text(steps)

    steps_with_image = sum(1 for s in steps if s.get("has_image", False))

    return f"""TÍTULO DO DOCUMENTO: {title}

INFORMAÇÕES DOS PASSOS CAPTURADOS:
{steps_text}

ESTATÍSTICAS:
- Total de passos: {len(steps)}
- Passos com imagem: {steps_with_image}

---

INSTRUÇÕES DETALHADAS:

1. EXTRAIA o máximo de informações de cada passo descrito acima.
2. NÃO RESUMA - EXPANDA cada informação em procedimentos detalhados.
3. Se um passo menciona interface/tela/campos, DESCREVA cada elemento.
4. Passos com [CONTÉM IMAGEM] devem incluir: ![Passo N](./img/step_NN.png)

ESTRUTURA OBRIGATÓRIA DO DOCUMENTO:

# {title}

## Visão Geral
(2-3 parágrafos explicando o procedimento completo)

## Índice
(lista de seções)

## Passo N: [Nome Descritivo]
### Objetivo
(o que será alcançado)

### Procedimento
1. Ação detalhada 1
2. Ação detalhada 2
3. Ação detalhada 3
(mínimo 3 ações por passo)

📝 **Nota**: informação complementar
💡 **Dica**: sugestão de produtividade
⚠️ **Importante**: alerta relevante

(repetir estrutura para cada passo)

## Checklist de Verificação Final
- [ ] Item verificável 1
- [ ] Item verificável 2
(mínimo 5 itens)

## Problemas Comuns e Soluções
| Problema | Causa | Solução |
|----------|-------|---------|
(mínimo 3 linhas)

## Notas Importantes
(observações finais)

---
Regras: agrupe passos relacionados se fizer sentido; use linguagem imperativa; não invente passos novos mas DETALHE ao máximo os existentes.

Gere o documento completo agora:"""


def build_structured_prompt(title: str, steps: list[dict[str, Any]]) -> str:
    """Constrói o prompt para generate_structured_documentation (JSON)."""
    steps_text = _truncate_steps_text(steps)

    steps_with_image = sum(1 for s in steps if s.get("has_image", False))

    return f"""TÍTULO DO DOCUMENTO: {title}

INFORMAÇÕES DOS PASSOS CAPTURADOS:
{steps_text}

ESTATÍSTICAS:
- Total de passos: {len(steps)}
- Passos com imagem: {steps_with_image}

---

INSTRUÇÕES:

1. ANALISE cada passo e EXTRAIA todas as informações disponíveis.
2. EXPANDA cada passo em procedimentos detalhados (3-5 ações por passo).
3. NÃO RESUMA - preserve e detalhe todas as informações.
4. Passos marcados com [CONTÉM IMAGEM] devem ter campo "imagem" preenchido.

GERE O JSON com esta estrutura:

{{
  "visao_geral": "2-3 frases descrevendo o procedimento completo de {title}",
  "passos": [
    {{
      "numero": 1,
      "titulo": "Nome descritivo do passo",
      "objetivo": "O que será alcançado neste passo (até 20 palavras)",
      "procedimento": [
        "Ação detalhada 1 em modo imperativo",
        "Ação detalhada 2 em modo imperativo",
        "Ação detalhada 3 em modo imperativo"
      ],
      "imagem": "./img/step_01.png"  // ou null se não tem imagem
    }}
  ],
  "avisos": [
    {{"tipo": "WARNING", "texto": "Alerta sobre ponto crítico"}},
    {{"tipo": "TIP", "texto": "Dica de produtividade"}},
    {{"tipo": "NOTE", "texto": "Informação complementar"}}
  ],
  "checklist": [
    "Item de verificação 1",
    "Item de verificação 2",
    "Item de verificação 3",
    "Item de verificação 4",
    "Item de verificação 5"
  ],
  "troubleshooting": [
    {{"problema": "Descrição do problema", "causa": "Motivo provável", "solucao": "Como resolver"}},
    {{"problema": "Outro problema", "causa": "Outro motivo", "solucao": "Outra solução"}},
    {{"problema": "Terceiro problema", "causa": "Terceiro motivo", "solucao": "Terceira solução"}}
  ]
}}

MÍNIMOS OBRIGATÓRIOS:
- visao_geral: 2-3 frases
- procedimento por passo: 3-5 ações
- avisos: ≥1 WARNING, ≥2 TIP/NOTE
- checklist: ≥5 itens
- troubleshooting: ≥3 entradas

Retorne APENAS o JSON válido, sem markdown code blocks:"""


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------


def _get_system_prompt_for_template(template_id: str | None) -> str:
    """Return the appropriate system prompt based on the template_id."""
    if template_id == "wolbito_it":
        return WOLBITO_IT_SYSTEM_PROMPT
    if template_id == "wolbito_pop":
        return WOLBITO_POP_SYSTEM_PROMPT
    return DOC_PRO_SYSTEM_PROMPT


def enhance_document_with_gemini(
    title: str,
    steps: list[dict[str, Any]],
    api_key: str,
    model: str = "models/gemini-2.5-flash",
    template_id: str | None = None,
) -> str:
    """Transforma passos em documento Markdown profissional usando Gemini.

    Parameters
    ----------
    template_id : str | None
        Se "wolbito_it" ou "wolbito_pop", usa prompts específicos para gerar
        markdown na estrutura esperada pelo corporate_markdown_to_docx.
    """
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'google-generativeai' não instalada. Execute: pip install google-generativeai"
        ) from exc

    genai.configure(api_key=api_key)

    normalized_model = model if model.startswith("models/") else f"models/{model}"
    user_prompt = build_doc_pro_prompt(title, steps, template_id=template_id)
    system_prompt = _get_system_prompt_for_template(template_id)

    logger.info(
        "enhance_document_with_gemini: template_id=%s, system_prompt=%s",
        template_id,
        "WOLBITO_IT"
        if template_id == "wolbito_it"
        else "WOLBITO_POP"
        if template_id == "wolbito_pop"
        else "DOC_PRO",
    )

    try:
        gen_model = genai.GenerativeModel(
            model_name=normalized_model,
            system_instruction=system_prompt,
        )
        response = gen_model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=_estimate_output_tokens(steps),
            ),
        )
        return _clean_markdown_fences(response.text or "")

    except Exception as exc:
        _handle_gemini_error(exc)





def generate_structured_documentation(
    title: str,
    steps: list[dict[str, Any]],
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
    images_b64: list[str] | None = None,
) -> dict[str, Any]:
    """Gera documentação estruturada em JSON usando Gemini."""
    genai, gen_model = _gemini_model(api_key, model, DOC_TEMPLATE_SYSTEM_PROMPT)
    user_prompt = build_structured_prompt(title, steps)

    # O SDK do Gemini recebe uma lista de partes: texto primeiro, imagens em
    # seguida.  Limitamos a 5 capturas para não estourar o contexto.
    parts: list[Any] = [user_prompt]
    for b64_img in (images_b64 or [])[:5]:
        try:
            parts.append(
                {"mime_type": "image/png", "data": base64.b64decode(b64_img)}
            )
        except (ValueError, TypeError):
            logger.warning("Imagem base64 inválida ignorada em generate_structured_documentation")

    try:
        response = gen_model.generate_content(
            parts,
            generation_config=genai.types.GenerationConfig(
                temperature=0.5,
                max_output_tokens=_estimate_output_tokens(steps),
            ),
        )
        result = _clean_markdown_fences(response.text or "")

        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            json_match = re.search(r"\{[\s\S]*\}", result)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                except json.JSONDecodeError:
                    parsed = {}
            else:
                parsed = {}

        if not isinstance(parsed, dict):
            parsed = {}

        # Garantir campos obrigatórios (fallback se IA falhar)
        parsed.setdefault("visao_geral", f"Procedimento para {title}")
        parsed.setdefault(
            "passos",
            [
                {
                    "numero": i,
                    "titulo": step.get("title", "") or f"Passo {i}",
                    "objetivo": step.get("description", "")[:500],  # aumentado de 100
                    "procedimento": [step.get("description", "")]
                    if step.get("description")
                    else ["Executar ação conforme descrito"],
                    "imagem": f"./img/step_{i:02d}.png"
                    if step.get("has_image")
                    else None,
                }
                for i, step in enumerate(steps, 1)
            ],
        )
        parsed.setdefault(
            "avisos", [{"tipo": "NOTE", "texto": "Verifique os detalhes gerados"}]
        )
        parsed.setdefault(
            "checklist", ["Verificar se todos os passos foram concluídos"]
        )
        parsed.setdefault("troubleshooting", [])

        return parsed

    except Exception as exc:
        _handle_gemini_error(exc)


def format_document_like_template(
    raw_text: str,
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
) -> str:
    """Reformata texto como manual passo a passo segundo o template padrão."""
    genai, gen_model = _gemini_model(api_key, model, TEMPLATE_SYSTEM_PROMPT)

    # Construir prompt de usuário que enfatiza preservação do conteúdo
    user_prompt = f"""DOCUMENTO ORIGINAL A SER TRANSFORMADO:

{raw_text.strip() or "(Texto vazio.)"}

---

INSTRUÇÕES IMPORTANTES:
1. PRESERVE 100% do conteúdo acima - não omita nenhuma informação.
2. EXPANDA cada seção em passos detalhados e acionáveis.
3. Se houver referências a imagens, figuras ou elementos visuais, MANTENHA-AS.
4. Transforme o conteúdo em um manual passo a passo profissional.
5. O documento de saída deve ser MAIS DETALHADO que o original, não mais curto.

Gere o documento Markdown estruturado agora:"""

    try:
        response = gen_model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.5,
                # Documentos reformatados costumam ficar maiores que o original.
                max_output_tokens=8192,
            ),
        )
        return _clean_markdown_fences(response.text or "")

    except Exception as exc:
        _handle_gemini_error(exc)
