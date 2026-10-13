/**
 * API functions for AI Tools & Agents management.
 *
 * Uses the shared `api` axios instance from `./api.js` which already
 * injects Authorization headers and handles 401 redirects.
 */

import { api } from "./api";

const TOOLS_BASE = "/api/tools";

/**
 * List all AI tools, optionally filtered by scope/project.
 * @param {{ scope?: string, project_id?: string }} [params]
 * @returns {Promise<{ tools: Array, total: number }>}
 */
export async function listTools(params = {}) {
  const res = await api.get(TOOLS_BASE, { params });
  return res.data;
}

/**
 * Get a single tool by ID.
 * @param {string} id
 * @returns {Promise<Object>}
 */
export async function getTool(id) {
  const res = await api.get(`${TOOLS_BASE}/${id}`);
  return res.data;
}

/**
 * Create a new AI tool (admin only).
 * @param {Object} data - AiToolCreate fields
 * @returns {Promise<Object>}
 */
export async function createTool(data) {
  const res = await api.post(TOOLS_BASE, data);
  return res.data;
}

/**
 * Update an existing AI tool (admin only).
 * @param {string} id
 * @param {Object} data - AiToolUpdate fields (partial)
 * @returns {Promise<Object>}
 */
export async function updateTool(id, data) {
  const res = await api.patch(`${TOOLS_BASE}/${id}`, data);
  return res.data;
}

/**
 * Delete an AI tool (admin only, fails for native tools).
 * @param {string} id
 * @returns {Promise<Object>}
 */
export async function deleteTool(id) {
  const res = await api.delete(`${TOOLS_BASE}/${id}`);
  return res.data;
}

/**
 * Toggle a tool active/inactive.
 * @param {string} id
 * @param {boolean} isActive
 * @returns {Promise<Object>}
 */
export async function toggleTool(id, isActive) {
  const res = await api.patch(`${TOOLS_BASE}/${id}/toggle`, {
    is_active: isActive,
  });
  return res.data;
}

/**
 * Get execution logs for a specific tool.
 * @param {string} id
 * @param {number} [limit=50]
 * @returns {Promise<{ logs: Array, total: number }>}
 */
export async function getToolLogs(id, limit = 50) {
  const res = await api.get(`${TOOLS_BASE}/${id}/logs`, {
    params: { limit },
  });
  return res.data;
}

/**
 * Manually run all active tools for a given trigger.
 * 
 * @param {string} trigger - One of: on_frame_capture, on_export, on_video_upload, manual
 * @param {{ project_id?: string, image_base64?: string, previous_steps?: string[], full_document?: string }} [context={}]
 * @returns {Promise<{ results: Array<{ tool_id: string, tool_name: string, output_target: string, output?: string, error?: string, status: string, duration_ms?: number }> }>}
 */
export async function runToolsManually(trigger, context = {}) {
  const res = await api.post(`${TOOLS_BASE}/run/${trigger}`, context);
  return res.data;
}

/**
 * Trigger labels for display in the UI.
 */
export const TRIGGER_LABELS = {
  on_frame_capture: "Ao capturar frame",
  on_export: "Ao exportar",
  on_video_upload: "Ao iniciar vídeo",
  manual: "Manual",
};

/**
 * Output target labels for display in the UI.
 */
export const OUTPUT_TARGET_LABELS = {
  description: "Preenche descrição",
  log_only: "Apenas log",
  context_tag: "Tag de contexto",
  suggestion: "Sugestão de próximo passo",
};

/**
 * Provider display config (label + color).
 */
export const PROVIDER_CONFIG = {
  gemini: { label: "Gemini", color: "#4285F4", bg: "#e8f0fe" },
  
  whisper: { label: "Whisper", color: "#8B5CF6", bg: "#f5f3ff" },
};

/**
 * Available models per provider for the tool form selects.
 */
export const MODELS_BY_PROVIDER = {
  gemini: [{ value: "models/gemini-2.5-flash", label: "Gemini 2.5 Flash" }],
  whisper: [
    { value: "whisper-large-v3-turbo", label: "Whisper Large v3 Turbo" },
  ],
};

