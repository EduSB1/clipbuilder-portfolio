import axios from "axios";

// ---------------------------------------------------------------------------
// 402 (Insufficient Credits) event system
// ---------------------------------------------------------------------------
// Components can subscribe to this event to show the InsufficientCreditsModal.
// This avoids tight coupling between the axios interceptor and React state.

let _onInsufficientCredits = null;

/**
 * Register a callback to be invoked when a 402 (insufficient credits) response
 * is received from the backend. The callback receives the detail string.
 * @param {((detail: string) => void) | null} handler
 */
export function onInsufficientCredits(handler) {
  _onInsufficientCredits = handler;
}

// Determine default baseURL from Vite env or fallback
function resolveDefaultBaseUrl() {
  try {
    // Vite exposes import.meta.env.VITE_API_URL
    if (
      typeof import.meta !== "undefined" &&
      import.meta.env &&
      import.meta.env.VITE_API_URL
    ) {
      return import.meta.env.VITE_API_URL;
    }
  } catch {}

  // Default to same-origin proxy (works in Docker via nginx: /api -> backend:8000)
  // In dev, Vite proxies /api to http://127.0.0.1:8000 (see vite.config.js)
  return "/api";
}

export const api = axios.create({
  baseURL: resolveDefaultBaseUrl(),
  timeout: 120000,
});

// ─── Clerk token injection ────────────────────────────────────────────────────

let _clerkGetToken = null;

/**
 * Registra a função getToken() do Clerk no interceptor do axios.
 * Chamada uma vez pelo componente ClerkSetup.
 * @param {Function|null} getTokenFn
 */
export function setupClerkToken(getTokenFn) {
  _clerkGetToken = getTokenFn;
}

// ─────────────────────────────────────────────────────────────────────────────

/**
 * Converte steps (com .blob e .has_image) em image_map para o backend.
 * Chaves: "Passo 1", "Passo 2", ...; valores: base64 da imagem.
 * @param {Array<{ has_image?: boolean, blob?: Blob }>} steps
 * @returns {Promise<Record<string, string>>}
 */
export async function buildImageMapFromSteps(steps) {
  const map = {};
  if (!Array.isArray(steps)) return map;
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    if (!step?.has_image || !step?.blob) continue;
    try {
      const base64 = await blobToBase64(step.blob);
      if (base64) map[`Passo ${i + 1}`] = base64;
    } catch (_) {
      /* skip step */
    }
  }
  return map;
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const dataUrl = r.result;
      const base64 =
        typeof dataUrl === "string" && dataUrl.includes(",")
          ? dataUrl.split(",")[1]
          : "";
      resolve(base64 || null);
    };
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

// Auth tokens are managed entirely by Clerk via setupClerkToken().
// No localStorage token management needed.


// ---------------------------------------------------------------------------
// Server-side key status — cached from /ai-keys-status endpoint.
// Allows the frontend to know that the backend has keys configured (env/DB)
// even when the user has no keys in localStorage.
// ---------------------------------------------------------------------------

let _serverKeys = { gemini: false };
let _serverKeysFetched = false;

/**
 * Busca do backend quais chaves de IA estão configuradas no servidor (env ou DB).
 * O resultado é cacheado em memória para evitar chamadas repetidas.
 * @param {boolean} [force=false] - Se true, ignora o cache e busca novamente.
 * @returns {Promise<{ gemini: boolean, gemini: boolean }>}
 */
export async function fetchServerKeyStatus(force = false) {
  if (_serverKeysFetched && !force) return _serverKeys;
  try {
    const res = await api.get("/ai-keys-status");
    if (res.data) {
      _serverKeys = {
        gemini: !!res.data.gemini,
        
      };
      _serverKeysFetched = true;
    }
  } catch (err) {
    // Silently fail — we'll just rely on sessionStorage keys
    console.warn("Failed to fetch server AI key status:", err?.message);
  }
  return _serverKeys;
}

/**
 * Retorna o status cacheado das chaves do servidor (síncrono).
 * Deve ser chamado após fetchServerKeyStatus().
 * @returns {{ gemini: boolean, gemini: boolean }}
 */
export function getServerKeyStatus() {
  return _serverKeys;
}

/**
 * Verifica se as chaves de API estão disponíveis no servidor.
 * @returns {{ gemini: boolean, gemini: boolean }}
 */
export function hasApiKeys() {
  return {
    gemini: _serverKeys.gemini,
    
  };
}

export async function testApiKeys() {
  try {
    const res = await api.post("/test-api-keys");
    return res.data;
  } catch (err) {
    return {
      gemini: false,
      
      geminiError: err?.response?.data?.detail || err.message,
      
    };
  }
}

// ---------------------------------------------------------------------------
// Interceptor de REQUEST — injeta X-Gemini-Key e X-Gemini-Key em toda
// requisição que vá para endpoints de IA.
// ---------------------------------------------------------------------------

api.interceptors.request.use(async (config) => {
  // 1. Injetar token do Clerk (se disponível)
  if (_clerkGetToken) {
    try {
      const token = await _clerkGetToken();
      if (token) {
        config.headers.Authorization = "Bearer " + token;
      }
    } catch (err) {
      console.warn("Clerk getToken failed:", err);
    }
  }

  // 1b. Fallback: sys token (local JWT admin backdoor)
  // Only injected when Clerk token was not set and a sys token exists in sessionStorage.
  if (!config.headers.Authorization) {
    try {
      const sysToken = sessionStorage.getItem("__sys_token");
      if (sysToken) {
        config.headers.Authorization = "Bearer " + sysToken;
      }
    } catch (_) {}
  }

  return config;
});

// ---------------------------------------------------------------------------
// Interceptor de RESPONSE — trata 401 (API key vs Clerk session)
// ---------------------------------------------------------------------------

// Endpoints whose 401 means "missing/invalid API key", NOT "session expired".
const API_KEY_401_PATTERNS = [
  "/videos/youtube",
  "/smart-text",
  "/describe-gif",
  "/enhance-document",
  "/generate-documentation",
  "/format-and-export",
  "/videos/raw",
  "/test-api-keys",
];

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    const url = (original?.url || "").toString();

    // ── 402 Insufficient Credits ──────────────────────────────────────
    if (err?.response?.status === 402) {
      const detail =
        err?.response?.data?.detail ||
        "Créditos insuficientes. Adquira mais créditos para continuar.";
      if (_onInsufficientCredits) {
        _onInsufficientCredits(detail);
      }
      return Promise.reject(err);
    }

    if (err?.response?.status === 401) {
      const detail = (err?.response?.data?.detail || "")
        .toString()
        .toLowerCase();

      // Se o token expirou, tenta obter um novo token do Clerk (ignorando o cache) e refaz a requisição.
      const isExpired = detail.includes("expired") || detail.includes("expirado");
      if (isExpired && _clerkGetToken && original && !original._retry) {
        original._retry = true;
        try {
          const token = await _clerkGetToken({ skipCache: true });
          if (token) {
            original.headers.Authorization = "Bearer " + token;
            return api(original);
          }
        } catch (retryErr) {
          console.warn("Failed to retry request with refreshed token:", retryErr);
        }
      }

      // If the 401 came from an AI/video endpoint or mentions API key / Gemini / Gemini,
      // it's an API-key issue, not a session expiry.
      const isApiKey401 =
        API_KEY_401_PATTERNS.some((p) => url.includes(p)) ||
        detail.includes("api") ||
        detail.includes("gemini") ||
        
        detail.includes("chave");

      // Non-API-key 401: Clerk handles session management and redirect.
      if (!isApiKey401) {
        // Nothing to do — Clerk's ProtectedRoute handles redirect.
      }
    }
    return Promise.reject(err);
  },
);


// No localStorage token initialization — Clerk handles auth tokens.

/**
 * Converte markdown em .docx e dispara o download no browser.
 * @param {string} markdown - Conteúdo em markdown
 * @param {string} [filename] - Nome do ficheiro (ex: "documento_profissional.docx")
 * @param {boolean} [professional=true] - Se true, gera documento com formatação profissional
 * @param {Record<string, string>} [imageMap] - Mapa nome -> path ou base64 para [Imagem: Nome] / ![alt](...)
 * @param {string} [templateId] - ID do template corporativo (wolbito_it, wolbito_pop, clipbuilder_pro)
 * @param {Record<string, string>} [templateMetadata] - Metadados corporativos (document_code, revision, etc.)
 */
export async function downloadMarkdownAsDocx(
  markdown,
  filename = "documento_profissional.docx",
  professional = true,
  imageMap = null,
  templateId = null,
  templateMetadata = null,
) {
  const safeName = (filename || "documento_profissional.docx")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9 ._-]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  const finalName = safeName.endsWith(".docx") ? safeName : `${safeName}.docx`;
  // Title for display inside the document: preserve original name with accents/spaces
  const displayTitle = (filename || "documento_profissional")
    .replace(/\.\w+$/, "")
    .trim();
  const body = {
    markdown,
    title: displayTitle,
    professional,
  };
  if (imageMap && typeof imageMap === "object") {
    body.image_map = imageMap;
  }
  if (templateId) {
    body.template_id = templateId;
  }
  if (templateMetadata && typeof templateMetadata === "object") {
    body.template_metadata = templateMetadata;
  }
  console.log(
    "[downloadMarkdownAsDocx] Sending to /markdown-to-docx → template_id:",
    body.template_id ?? "(not set)",
    "| professional:",
    body.professional,
    "| templateMetadata keys:",
    body.template_metadata ? Object.keys(body.template_metadata) : "(none)",
  );
  try {
    const response = await api.post("/markdown-to-docx", body, {
      responseType: "blob",
    });
    const blob = response.data;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = finalName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    if (err.code === "ECONNABORTED") {
      err.parsedDetail =
        "O processamento demorou muito tempo (timeout). Tente exportar um documento menor ou com menos imagens.";
    } else if (err.response?.data instanceof Blob && err.response.status >= 400) {
      try {
        const text = await err.response.data.text();
        const parsed = JSON.parse(text);
        err.parsedDetail = parsed.detail;
      } catch (_) {
        /* ignore parse errors */
      }
    }
    throw err;
  }
}

/**
 * Converte markdown em .pdf e dispara o download no browser.
 * @param {string} markdown - Conteúdo em markdown
 * @param {string} [filename] - Nome do ficheiro (ex: "documento.pdf")
 * @param {Record<string, string>} [imageMap] - Mapa nome -> path ou base64 para [Imagem: Nome]
 */
export async function downloadMarkdownAsPdf(
  markdown,
  filename = "documento.pdf",
  imageMap = null,
) {
  const safeName = (filename || "documento.pdf")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9 ._-]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  const finalName = safeName.endsWith(".pdf") ? safeName : `${safeName}.pdf`;
  // Title for display inside the document: preserve original name with accents/spaces
  const title = (filename || "documento").replace(/\.\w+$/, "").trim();
  const body = { markdown, title };
  if (imageMap && typeof imageMap === "object") {
    body.image_map = imageMap;
  }
  try {
    const response = await api.post("/markdown-to-pdf", body, {
      responseType: "blob",
    });
    const blob = response.data;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = finalName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    if (err.response?.data instanceof Blob && err.response.status >= 400) {
      try {
        const text = await err.response.data.text();
        const parsed = JSON.parse(text);
        err.parsedDetail = parsed.detail;
      } catch (_) {
        /* ignore */
      }
    }
    throw err;
  }
}

/**
 * Converte markdown em .html e dispara o download no browser.
 * @param {string} markdown - Conteúdo em markdown
 * @param {string} [filename] - Nome do ficheiro (ex: "documento.html")
 */
export async function downloadMarkdownAsHtml(
  markdown,
  filename = "documento.html",
) {
  const safeName = (filename || "documento.html")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9 ._-]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  const finalName = safeName.endsWith(".html") ? safeName : `${safeName}.html`;
  // Title for display inside the document: preserve original name with accents/spaces
  const title = (filename || "documento").replace(/\.\w+$/, "").trim();
  const response = await api.post(
    "/markdown-to-html",
    { markdown, title },
    { responseType: "blob" },
  );
  const blob = response.data;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = finalName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Document Templates
// ---------------------------------------------------------------------------

/**
 * Fetch available document templates from the backend.
 * @returns {Promise<Array<{id: string, name: string, short_name: string, description: string, icon: string, category: string, has_logo: boolean, header_fields: string[], sections: string[], footer_fields: string[]}>>}
 */
export async function fetchDocumentTemplates() {
  try {
    const res = await api.get("/templates");
    return res?.data?.templates || [];
  } catch (err) {
    console.warn("Failed to fetch document templates:", err);
    return [];
  }
}

// Expose helper to clear stored credentials
export function clearStoredConfig() {
  if (api.defaults.headers) {
    delete api.defaults.headers.common?.["Authorization"];
  }
}
