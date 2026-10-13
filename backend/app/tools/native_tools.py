"""Definitions for the 5 native (built-in) AI tools.

These tools are seeded into the database on startup and cannot be deleted
(is_native=True), but they can be edited and toggled on/off by admins.
"""

from __future__ import annotations

NATIVE_TOOLS: list[dict] = [
    {
        "name": "Detecção de Contexto de Tela",
        "description": (
            "Identifica automaticamente o tipo de interface capturada "
            "(browser, terminal, IDE, formulário, dashboard) e adiciona "
            "uma tag de contexto ao passo."
        ),
        "prompt": (
            "Analise esta captura de tela e identifique:\n"
            "1. Tipo de interface: browser web, terminal/CLI, IDE/editor de código, "
            "formulário, dashboard, aplicativo desktop, outro\n"
            "2. Nome do sistema/aplicação (se visível)\n"
            "3. Seção/tela específica (se identificável)\n"
            "\n"
            "Responda APENAS em JSON com este formato:\n"
            '{"interface_type": "...", "app_name": "...", "screen_section": "...", '
            '"confidence": 0.0-1.0}'
        ),
        "model_provider": "gemini",
        "model_name": "models/gemini-2.5-flash",
        "triggers": ["on_frame_capture"],
        "output_target": "context_tag",
        "is_native": True,
        "is_active": True,
        "scope": "global",
    },
    {
        "name": "Descrição com Contexto entre Frames",
        "description": (
            "Gera descrição do frame atual levando em conta os passos anteriores "
            "já documentados, mantendo coerência narrativa."
        ),
        "prompt": (
            "Você está documentando um processo passo a passo.\n"
            "\n"
            "PASSOS JÁ DOCUMENTADOS:\n"
            "{previous_steps}\n"
            "\n"
            "Agora descreva este novo frame como o próximo passo do processo, "
            "mantendo coerência com o fluxo anterior.\n"
            "Use modo imperativo, mencione elementos visuais visíveis e "
            "contextualize no fluxo."
        ),
        "model_provider": "gemini",
        "model_name": "models/gemini-2.5-flash",
        "triggers": ["on_frame_capture"],
        "output_target": "description",
        "is_native": True,
        "is_active": False,  # disabled by default — user opts in
        "scope": "global",
    },
    {
        "name": "Sugestão de Próximo Passo",
        "description": (
            "Com base nos frames já capturados, sugere o que deveria ser o "
            "próximo passo lógico do processo."
        ),
        "prompt": (
            "Com base nos passos já documentados:\n"
            "{previous_steps}\n"
            "\n"
            "E no frame atual, sugira qual seria o próximo passo lógico "
            "esperado neste processo.\n"
            "Seja conciso, use no máximo 2 frases. Comece com "
            '"Próximo passo sugerido: ".'
        ),
        "model_provider": "gemini",
        "model_name": "meta-llama/llama-4-scout-17b-16e-instruct",
        "triggers": ["on_frame_capture"],
        "output_target": "suggestion",
        "is_native": True,
        "is_active": True,
        "scope": "global",
    },
    {
        "name": "Agente de Revisão ao Exportar",
        "description": (
            "Antes de exportar, revisa toda a documentação gerada, corrige "
            "inconsistências entre passos e melhora a clareza do texto."
        ),
        "prompt": (
            "Você é um revisor técnico especializado em documentação de processos.\n"
            "\n"
            "Revise a seguinte documentação e retorne uma versão melhorada:\n"
            "- Corrija inconsistências entre os passos\n"
            "- Padronize o modo imperativo\n"
            "- Melhore a clareza sem alterar o conteúdo técnico\n"
            "- Mantenha o mesmo número de passos\n"
            "\n"
            "DOCUMENTAÇÃO:\n"
            "{full_document}\n"
            "\n"
            "Retorne APENAS o texto revisado dos passos, um por linha, no formato:\n"
            "PASSO_ID|||DESCRIÇÃO_REVISADA"
        ),
        "model_provider": "gemini",
        "model_name": "models/gemini-2.5-flash",
        "triggers": ["on_export"],
        "output_target": "description",
        "is_native": True,
        "is_active": False,  # disabled by default — user opts in
        "scope": "global",
    },
    {
        "name": "Transcrição Sincronizada com Frames",
        "description": (
            "Usa o Whisper para transcrever o áudio do vídeo e associa "
            "automaticamente o trecho de fala ao timestamp do frame capturado."
        ),
        "prompt": (
            "Transcreva o áudio do trecho de vídeo fornecido. "
            "Retorne apenas o texto transcrito, sem timestamps ou "
            "formatação adicional."
        ),
        "model_provider": "gemini",
        "model_name": "models/gemini-2.5-flash",
        "triggers": ["on_frame_capture"],
        "output_target": "description",
        "is_native": True,
        "is_active": False,  # disabled by default — user opts in
        "scope": "global",
    },
]
