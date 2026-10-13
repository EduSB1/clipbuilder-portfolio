// ---------------------------------------------------------------------------
// sessionCache.js – Persiste estado do Dashboard entre navegações (ex: Admin)
//
// Usa sessionStorage para dados serializáveis (metadata, strings, números)
// e IndexedDB para dados binários (blobs de imagens/GIFs do vídeo).
//
// O cache sobrevive a navegações SPA (troca de rota) e até F5 para metadata.
// Blobs no IndexedDB também sobrevivem a refresh.
// ---------------------------------------------------------------------------

const SS_PREFIX = "CLIPBUILDER_CACHE_";
const IDB_NAME = "ClipBuilderCache";
const IDB_VERSION = 1;
const IDB_STORE_BLOBS = "blobs";
const IDB_STORE_VIDEO = "video";

// ===================== sessionStorage helpers =====================

function ssKey(key) {
  return SS_PREFIX + key;
}

function ssGet(key) {
  try {
    const raw = sessionStorage.getItem(ssKey(key));
    if (raw === null || raw === undefined) return undefined;
    return JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function ssSet(key, value) {
  try {
    sessionStorage.setItem(ssKey(key), JSON.stringify(value));
  } catch {
    // quota exceeded – silently ignore
  }
}

function ssRemove(key) {
  try {
    sessionStorage.removeItem(ssKey(key));
  } catch {
    // ignore
  }
}

// ===================== IndexedDB helpers =====================

let _dbPromise = null;

function openDB() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB not available"));
      return;
    }
    const req = indexedDB.open(IDB_NAME, IDB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(IDB_STORE_BLOBS)) {
        db.createObjectStore(IDB_STORE_BLOBS);
      }
      if (!db.objectStoreNames.contains(IDB_STORE_VIDEO)) {
        db.createObjectStore(IDB_STORE_VIDEO);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => {
      _dbPromise = null;
      reject(req.error);
    };
  });
  return _dbPromise;
}

async function idbPut(storeName, key, value) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, "readwrite");
      tx.objectStore(storeName).put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    // silently fail
  }
}

async function idbGet(storeName, key) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, "readonly");
      const req = tx.objectStore(storeName).get(key);
      req.onsuccess = () => resolve(req.result ?? null);
      req.onerror = () => reject(req.error);
    });
  } catch {
    return null;
  }
}

async function idbDelete(storeName, key) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, "readwrite");
      tx.objectStore(storeName).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    // silently fail
  }
}

async function idbClear(storeName) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, "readwrite");
      tx.objectStore(storeName).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    // silently fail
  }
}

// ===================== Step serialization =====================

/**
 * Serializa um step para sessionStorage (sem blob/url).
 * Os campos binários são salvos separadamente no IndexedDB.
 */
function serializeStep(step) {
  return {
    id: step.id,
    description: step.description || "",
    timestamp: step.timestamp || "",
    seconds: step.seconds ?? null,
    has_image: !!step.has_image,
    is_gif: !!step.is_gif,
    title: step.title || "",
    userAction: step.userAction || "",
    expectedResult: step.expectedResult || "",
    observations: step.observations || "",
    completed: !!step.completed,
    thumbnailUrl: step.thumbnailUrl || "",
  };
}

// ===================== Public API =====================

/**
 * Salva todo o estado relevante do Dashboard no cache do navegador.
 * Deve ser chamado no useEffect de cleanup (unmount) ou periodicamente.
 *
 * @param {object} state - Estado do Dashboard
 */
export async function saveDashboardCache(state) {
  const {
    videoUrl,
    videoId,
    youtubeUrl,
    steps,
    documentTitle,
    documentStatus,
    lastCompletedStep,
    documentOverview,
    documentGeneratedAt,
    aiStatus,
    aiContext,
    selectedStepId,
    geminiModel,
    includeTimestamp,
    imageNamePrefix,
    savedPrompt,
    videoSourceType, // 'local' | 'youtube' | null
  } = state;

  // ---- sessionStorage (metadata leve) ----
  ssSet("videoId", videoId || null);
  ssSet("youtubeUrl", youtubeUrl || "");
  ssSet("documentTitle", documentTitle || "");
  ssSet("documentStatus", documentStatus || "em_progresso");
  ssSet("lastCompletedStep", lastCompletedStep ?? 0);
  ssSet("documentOverview", documentOverview || "");
  ssSet("documentGeneratedAt", documentGeneratedAt || "");
  ssSet("aiStatus", aiStatus || "idle");
  ssSet("aiContext", aiContext || "");
  ssSet("selectedStepId", selectedStepId || null);
  ssSet("videoSourceType", videoSourceType || null);
  ssSet("hasCache", true);

  // Serializar metadata dos steps (sem blobs)
  const stepsMeta = (steps || []).map(serializeStep);
  ssSet("steps", stepsMeta);

  // ---- IndexedDB (blobs pesados) ----
  // Salvar blobs de cada step
  const blobPromises = (steps || []).map(async (step) => {
    if (step.blob) {
      await idbPut(IDB_STORE_BLOBS, `step_blob_${step.id}`, step.blob);
    }
    // Para GIFs, salvar o blob do GIF original se existir
    if (step.is_gif && step.blob) {
      await idbPut(IDB_STORE_BLOBS, `step_gif_${step.id}`, step.blob);
    }
  });

  // Salvar o arquivo de vídeo local no IndexedDB (se for blob URL local)
  // Nota: só salvamos se for vídeo local (não YouTube) e o videoFile foi fornecido
  if (state.videoFile) {
    await idbPut(IDB_STORE_VIDEO, "currentVideoFile", state.videoFile);
    ssSet("videoFileName", state.videoFile.name || "video.mp4");
  }

  // Se for YouTube, o vídeo pode ser re-obtido via videoId, não precisamos salvar o blob
  if (videoSourceType === "youtube" && videoId) {
    ssSet("youtubeVideoReady", aiStatus === "ready");
  }

  await Promise.all(blobPromises);
}

/**
 * Restaura o estado do Dashboard a partir do cache do navegador.
 * Retorna null se não houver cache salvo.
 *
 * @returns {Promise<object|null>} Estado parcial para hidratar o Dashboard
 */
export async function restoreDashboardCache() {
  const hasCache = ssGet("hasCache");
  if (!hasCache) return null;

  const videoId = ssGet("videoId");
  const youtubeUrl = ssGet("youtubeUrl");
  const documentTitle = ssGet("documentTitle");
  const documentStatus = ssGet("documentStatus");
  const lastCompletedStep = ssGet("lastCompletedStep");
  const documentOverview = ssGet("documentOverview");
  const documentGeneratedAt = ssGet("documentGeneratedAt");
  const aiStatus = ssGet("aiStatus");
  const aiContext = ssGet("aiContext");
  const selectedStepId = ssGet("selectedStepId");
  const videoSourceType = ssGet("videoSourceType");
  const youtubeVideoReady = ssGet("youtubeVideoReady");
  const videoFileName = ssGet("videoFileName");

  // Restaurar steps com blobs do IndexedDB
  const stepsMeta = ssGet("steps") || [];
  const steps = await Promise.all(
    stepsMeta.map(async (meta) => {
      let blob = null;
      let url = "";

      try {
        blob = await idbGet(IDB_STORE_BLOBS, `step_blob_${meta.id}`);
        if (blob) {
          url = URL.createObjectURL(blob);
        }
      } catch {
        // blob perdido – step continua sem imagem visual
      }

      return {
        ...meta,
        blob: blob || null,
        url: url || "",
        has_image: !!blob && meta.has_image,
      };
    }),
  );

  // Restaurar vídeo
  let videoUrl = null;
  let videoFile = null;

  if (videoSourceType === "local") {
    // Tentar restaurar o arquivo de vídeo do IndexedDB
    try {
      const cachedFile = await idbGet(IDB_STORE_VIDEO, "currentVideoFile");
      if (cachedFile) {
        videoFile = cachedFile;
        videoUrl = URL.createObjectURL(cachedFile);
      }
    } catch {
      // Vídeo local perdido – usuário precisará reimportar
    }
  } else if (videoSourceType === "youtube" && videoId) {
    // Para YouTube, reconstruir a URL do vídeo a partir do videoId
    // A URL é servida pelo backend: /api/videos/{id}/file
    // Precisamos do baseURL da API
    try {
      const { api } = await import("./api.js");
      const base = (api.defaults.baseURL || "").replace(/\/$/, "");
      videoUrl = `${base}/videos/${videoId}/file`;
    } catch {
      // fallback
      videoUrl = `/api/videos/${videoId}/file`;
    }
  }

  return {
    videoUrl,
    videoId,
    videoFile,
    youtubeUrl: youtubeUrl || "",
    steps,
    documentTitle: documentTitle || "",
    documentStatus: documentStatus || "em_progresso",
    lastCompletedStep: lastCompletedStep ?? 0,
    documentOverview: documentOverview || "",
    documentGeneratedAt: documentGeneratedAt || "",
    aiStatus: videoUrl && videoId ? aiStatus || "ready" : "idle",
    aiContext: aiContext || "",
    selectedStepId: selectedStepId || null,
    videoSourceType: videoSourceType || null,
    youtubeVideoReady: !!youtubeVideoReady,
  };
}

/**
 * Verifica se existe cache salvo sem restaurar dados pesados.
 * @returns {boolean}
 */
export function hasDashboardCache() {
  return !!ssGet("hasCache");
}

/**
 * Limpa todo o cache do Dashboard (sessionStorage + IndexedDB).
 */
export async function clearDashboardCache() {
  // Limpar sessionStorage
  const keysToRemove = [
    "videoId",
    "youtubeUrl",
    "documentTitle",
    "documentStatus",
    "lastCompletedStep",
    "documentOverview",
    "documentGeneratedAt",
    "aiStatus",
    "aiContext",
    "selectedStepId",
    "videoSourceType",
    "hasCache",
    "steps",
    "youtubeVideoReady",
    "videoFileName",
  ];
  keysToRemove.forEach((k) => ssRemove(k));

  // Limpar IndexedDB
  await idbClear(IDB_STORE_BLOBS);
  await idbClear(IDB_STORE_VIDEO);
}

/**
 * Salva apenas os steps no cache (útil para salvar incrementalmente
 * após cada captura de frame sem reescrever tudo).
 *
 * @param {Array} steps
 */
export async function cacheSteps(steps) {
  const stepsMeta = (steps || []).map(serializeStep);
  ssSet("steps", stepsMeta);

  // Salvar blobs novos no IndexedDB
  await Promise.all(
    (steps || []).map(async (step) => {
      if (step.blob) {
        // Verificar se já existe para evitar reescrita desnecessária
        const existing = await idbGet(IDB_STORE_BLOBS, `step_blob_${step.id}`);
        if (!existing) {
          await idbPut(IDB_STORE_BLOBS, `step_blob_${step.id}`, step.blob);
        }
      }
    }),
  );
}

/**
 * Remove o blob de um step específico do IndexedDB.
 * Chamar ao remover um step do Dashboard.
 *
 * @param {string} stepId
 */
export async function removeCachedStepBlob(stepId) {
  await idbDelete(IDB_STORE_BLOBS, `step_blob_${stepId}`);
  await idbDelete(IDB_STORE_BLOBS, `step_gif_${stepId}`);
}

/**
 * Salva metadados simples no cache de sessão.
 * Útil para salvar campos individuais (ex: documentTitle, aiContext).
 *
 * @param {string} key
 * @param {*} value
 */
export function cacheSet(key, value) {
  ssSet(key, value);
}

/**
 * Lê um valor do cache de sessão.
 *
 * @param {string} key
 * @returns {*}
 */
export function cacheGet(key) {
  return ssGet(key);
}
