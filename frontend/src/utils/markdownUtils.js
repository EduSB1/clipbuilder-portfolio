/**
 * Utilitários para exportação e importação de Markdown estruturado
 * seguindo o schema obrigatório de documentação de processos.
 */

// Polyfill: crypto.randomUUID() only works in secure contexts (HTTPS/localhost).
function generateUUID() {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.getRandomValues === "function"
  ) {
    return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) =>
      (
        c ^
        (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))
      ).toString(16),
    );
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/**
 * Gera o frontmatter YAML
 */
function generateFrontmatter(metadata) {
  const now = new Date().toISOString();
  return `---
title: "${metadata.title || "Processo Sem Título"}"
status: "${metadata.status || "em_progresso"}"
video_source: "${metadata.videoSource || ""}"
last_completed_step: ${metadata.lastCompletedStep || 0}
generated_at: "${metadata.generatedAt || now}"
updated_at: "${now}"
---`;
}

/**
 * Serializa um passo individual no formato Markdown
 */
function serializeStep(step, index) {
  const stepNumber = index + 1;
  const title = step.title || `Passo ${stepNumber}`;
  const completed = step.completed ? " ✅" : "";

  let md = `### Passo ${stepNumber} - ${title}${completed}\n`;
  md += `- **Descrição:** ${step.description || "(Não preenchido)"}\n`;
  md += `- **Ação do usuário:** ${step.userAction || "(Não preenchido)"}\n`;
  md += `- **Resultado esperado:** ${step.expectedResult || "(Não preenchido)"}\n`;

  if (step.observations) {
    md += `- **Observações:** ${step.observations}\n`;
  }

  if (step.has_image && step.imageName) {
    md += `- **Imagem:** ![${step.imageName}](./images/${step.imageName})\n`;
  }

  return md;
}

/**
 * Gera o Markdown completo a partir dos passos e metadados
 */
export function generateMarkdown(steps, metadata, overview = "") {
  const frontmatter = generateFrontmatter(metadata);

  // Calcular último passo concluído
  let lastCompleted = 0;
  steps.forEach((step, idx) => {
    if (step.completed) {
      lastCompleted = idx + 1;
    }
  });

  // Visão geral
  const overviewSection =
    overview ||
    `Documentação gerada automaticamente pelo ClipBuilder. ` +
      `Total de ${steps.length} passo(s) documentado(s).`;

  // Passos
  const stepsSection = steps
    .map((step, idx) => serializeStep(step, idx))
    .join("\n");

  // Estado atual
  const nextStep = Math.min(lastCompleted + 1, steps.length);
  const statusLabel =
    metadata.status === "concluido"
      ? "Processo finalizado."
      : metadata.status === "pausado"
        ? "Documentação pausada. Retomar a partir do próximo passo."
        : "Documentação em andamento.";

  const stateSection = `## ⏸️ Estado Atual
- Último passo concluído: ${lastCompleted}
- Próximo passo esperado: ${nextStep}
- ${statusLabel}`;

  return `${frontmatter}

# 📄 Documentação do Processo

## 🧠 Visão Geral
${overviewSection}

---

## 🔢 Passos do Processo

${stepsSection}
---

${stateSection}
`;
}

/**
 * Faz parsing do frontmatter YAML
 */
function parseFrontmatter(content) {
  const frontmatterRegex = /^---\n([\s\S]*?)\n---/;
  const match = content.match(frontmatterRegex);

  if (!match) {
    return { metadata: {}, body: content };
  }

  const yamlContent = match[1];
  const body = content.slice(match[0].length).trim();

  const metadata = {};
  const lines = yamlContent.split("\n");

  for (const line of lines) {
    const colonIndex = line.indexOf(":");
    if (colonIndex === -1) continue;

    const key = line.slice(0, colonIndex).trim();
    let value = line.slice(colonIndex + 1).trim();

    // Remove quotes
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    // Parse numbers
    if (/^\d+$/.test(value)) {
      value = parseInt(value, 10);
    }

    // Convert snake_case to camelCase
    const camelKey = key.replace(/_([a-z])/g, (_, letter) =>
      letter.toUpperCase(),
    );
    metadata[camelKey] = value;
  }

  return { metadata, body };
}

/**
 * Faz parsing dos passos do Markdown
 */
function parseSteps(body) {
  const steps = [];
  const stepRegex =
    /### Passo (\d+) - (.+?)(?:\s*[✅])?\n([\s\S]*?)(?=### Passo \d+|## ⏸️|---\s*$|$)/g;

  let match;
  while ((match = stepRegex.exec(body)) !== null) {
    const stepNumber = parseInt(match[1], 10);
    const title = match[2].trim();
    const content = match[3].trim();

    const step = {
      id: generateUUID(),
      stepNumber,
      title,
      description: "",
      userAction: "",
      expectedResult: "",
      observations: "",
      timestamp: "",
      imageName: "",
      completed: match[0].includes("✅"),
      has_image: false,
      blob: null,
      url: "",
    };

    // Parse fields - suporta campos multi-linha
    // Primeiro, encontrar todas as posições dos marcadores de campo
    const fieldMarkerRegex = /- \*\*(.+?):\*\* /g;
    const fieldPositions = [];
    let markerMatch;
    while ((markerMatch = fieldMarkerRegex.exec(content)) !== null) {
      fieldPositions.push({
        fieldName: markerMatch[1].toLowerCase(),
        startIndex: markerMatch.index + markerMatch[0].length,
      });
    }

    // Extrair o valor de cada campo (até o próximo campo ou fim do conteúdo)
    for (let i = 0; i < fieldPositions.length; i++) {
      const field = fieldPositions[i];
      const nextFieldStart =
        fieldPositions[i + 1]?.startIndex -
        (fieldPositions[i + 1]
          ? content
              .slice(0, fieldPositions[i + 1].startIndex)
              .match(/- \*\*[^*]+:\*\* $/m)?.[0]?.length || 0
          : 0);

      // Encontrar onde termina este campo
      let endIndex = content.length;
      if (i + 1 < fieldPositions.length) {
        // Encontrar o início da próxima linha que contém o próximo campo
        const nextMarkerSearch = content
          .slice(field.startIndex)
          .search(/\n- \*\*/);
        if (nextMarkerSearch !== -1) {
          endIndex = field.startIndex + nextMarkerSearch;
        }
      }

      const fieldValue = content.slice(field.startIndex, endIndex).trim();

      if (fieldValue === "(Não preenchido)") continue;

      switch (field.fieldName) {
        case "descrição":
          step.description = fieldValue;
          break;
        case "ação do usuário":
          step.userAction = fieldValue;
          break;
        case "resultado esperado":
          step.expectedResult = fieldValue;
          break;
        case "observações":
          step.observations = fieldValue;
          break;
        case "timestamp":
          step.timestamp = fieldValue;
          break;
        case "imagem": {
          // Parse image reference
          const imgMatch = fieldValue.match(/!\[(.+?)\]\((.+?)\)/);
          if (imgMatch) {
            step.imageName = imgMatch[1];
            step.has_image = true;
          }
          break;
        }
      }
    }

    steps.push(step);
  }

  return steps;
}

/**
 * Faz parsing da visão geral
 */
function parseOverview(body) {
  const overviewRegex = /## 🧠 Visão Geral\n([\s\S]*?)(?=---|##|$)/;
  const match = body.match(overviewRegex);
  return match ? match[1].trim() : "";
}

/**
 * Faz parsing completo do Markdown
 */
export function parseMarkdown(content) {
  if (!content || typeof content !== "string") {
    return null;
  }

  const { metadata, body } = parseFrontmatter(content);
  const steps = parseSteps(body);
  const overview = parseOverview(body);

  return {
    metadata,
    steps,
    overview,
    isValid: steps.length > 0 || Object.keys(metadata).length > 0,
  };
}

/**
 * Valida se o Markdown segue o schema obrigatório
 */
export function validateSchema(parsed) {
  const errors = [];

  if (!parsed) {
    errors.push("Conteúdo inválido ou vazio");
    return { valid: false, errors };
  }

  const { metadata } = parsed;

  // Validar campos obrigatórios do frontmatter
  if (!metadata.title) {
    errors.push('Campo "title" ausente no frontmatter');
  }

  if (!metadata.status) {
    errors.push('Campo "status" ausente no frontmatter');
  } else if (
    !["em_progresso", "pausado", "concluido"].includes(metadata.status)
  ) {
    errors.push('Campo "status" deve ser: em_progresso, pausado ou concluido');
  }

  if (metadata.lastCompletedStep === undefined) {
    errors.push('Campo "last_completed_step" ausente no frontmatter');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Gera nome de arquivo baseado no título
 */
export function generateFilename(title, extension = "md") {
  let name = (title || "processo")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // Remove acentos
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "_")
    .slice(0, 50);

  if (!name) name = "processo";

  const timestamp = new Date().toISOString().slice(0, 10);
  return `${name}_${timestamp}.${extension}`;
}
