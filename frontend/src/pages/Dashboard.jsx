import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useAppAuth } from "../utils/AuthContext.jsx";
import {
    api,
    downloadMarkdownAsDocx,
    downloadMarkdownAsPdf,
    downloadMarkdownAsHtml,
    buildImageMapFromSteps,
    hasApiKeys,
    fetchServerKeyStatus,
} from "../utils/api";
import {
    saveDashboardCache,
    restoreDashboardCache,
    hasDashboardCache,
    clearDashboardCache,
    cacheSteps,
    removeCachedStepBlob,
    cacheSet,
} from "../utils/sessionCache";
import { generateMarkdown, parseMarkdown } from "../utils/markdownUtils";
import Header from "../components/shared/Header";
import MouseTilt from "../components/shared/MouseTilt";
import VideoArea from "../components/video/VideoArea";
import StepCard from "../components/video/StepCard";
import Sidebar from "../components/shared/Sidebar";
import SettingsModal from "../components/modals/SettingsModalExtended";
import ImageEditorModal from "../components/modals/ImageEditorModal";
import ImportMarkdownModal from "../components/modals/ImportMarkdownModal";
import EnhancedDocPreview from "../components/modals/EnhancedDocPreview";
import GifPreviewModal from "../components/modals/GifPreviewModal";
import GIF from "gif.js";
import LoginBackground from "../pages/login/LoginBackground";


import {
    Wand2,
    Settings,
    Download,
    Upload,
    FileText,
    File,
    Code,
    FileDown,
    Loader2,
    ChevronDown,
    Play,
} from "lucide-react";

// Polyfill: crypto.randomUUID() only works in secure contexts (HTTPS/localhost).
// This fallback works over plain HTTP (e.g. http://192.168.x.x).
function generateUUID() {
    if (
        typeof crypto !== "undefined" &&
        typeof crypto.randomUUID === "function"
    ) {
        return crypto.randomUUID();
    }
    // Fallback using crypto.getRandomValues if available
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
    // Last resort fallback
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
}

const LS = {
    geminiModel: "CLIPBUILDER_GEMINI_MODEL",
    savedPrompt: "CLIPBUILDER_SAVED_PROMPT",
    imageNamePrefix: "CLIPBUILDER_IMAGE_NAME_PREFIX",
    includeTimestamp: "CLIPBUILDER_INCLUDE_TIMESTAMP",
};

function lsGet(k) {
    try {
        return localStorage.getItem(k);
    } catch {
        return null;
    }
}

/**
 * Parse a context_tag JSON string from the AI tool into a display label.
 * Returns a short string like "🌐 Browser · GitHub" or null if unparseable.
 */
function formatContextTag(raw) {
    if (!raw) return null;
    try {
        const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
        const parts = [];
        const typeIcons = {
            "browser web": "🌐",
            "terminal/cli": "💻",
            "ide/editor de código": "📝",
            formulário: "📋",
            dashboard: "📊",
            "aplicativo desktop": "🖥️",
        };
        const iType = (obj.interface_type || "").toLowerCase();
        const icon = typeIcons[iType] || "🖥️";
        parts.push(icon);
        if (obj.interface_type) parts.push(obj.interface_type);
        if (obj.app_name) parts.push("·");
        if (obj.app_name) parts.push(obj.app_name);
        return parts.join(" ") || null;
    } catch {
        return typeof raw === "string" && raw.length < 100 ? raw : null;
    }
}

function lsSet(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch {}
}

function lsRemove(key) {
    try {
        localStorage.removeItem(key);
    } catch {}
}

function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "";
    const units = ["B", "KB", "MB", "GB"];
    let idx = 0;
    let value = bytes;
    while (value >= 1024 && idx < units.length - 1) {
        value /= 1024;
        idx++;
    }
    return `${value.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Revoke later; immediate revoke can cancel downloads in some browsers.
    setTimeout(() => {
        try {
            URL.revokeObjectURL(url);
        } catch {}
    }, 1500);
}

function formatTimestamp(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const hh = Math.floor(total / 3600);
    const mm = Math.floor((total % 3600) / 60);
    const ss = total % 60;
    return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

export default function Dashboard() {
    const { signOut, user: authUser } = useAppAuth();
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const youtubePollRef = useRef(null);
    const gifEncoderRef = useRef(null);
    const gifFrameIntervalRef = useRef(null);
    const videoFileRef = useRef(null); // arquivo de vídeo local (para cache)
    const cacheRestoredRef = useRef(false); // evita restaurar cache mais de uma vez

    const [videoUrl, setVideoUrl] = useState(null);
    const [videoId, setVideoId] = useState(null);
    const [videoSourceType, setVideoSourceType] = useState(null); // 'local' | 'youtube' | null
    const [youtubeUrl, setYoutubeUrl] = useState("");
    const [youtubeImporting, setYoutubeImporting] = useState(false);
    const [geminiModel, setGeminiModel] = useState(() => {
        const stored = lsGet(LS.geminiModel);
        const allowed = new Set([
            "models/gemini-2.5-flash",
            "whisper-large-v3-turbo",
        ]);
        if (stored && (allowed.has(stored) || stored.startsWith("models/"))) return stored;
        return "models/gemini-2.5-flash";
    });

    const [flaggedModels, setFlaggedModels] = useState(() => {
        try {
            const stored = localStorage.getItem("CLIPBUILDER_FLAGGED_MODELS");
            return stored ? JSON.parse(stored) : [];
        } catch {
            return [];
        }
    });

    useEffect(() => {
        localStorage.setItem("CLIPBUILDER_FLAGGED_MODELS", JSON.stringify(flaggedModels));
    }, [flaggedModels]);

    const [aiStatus, setAiStatus] = useState("idle"); // idle|uploading|processing|ready|error
    const [aiError, setAiError] = useState("");
    const [uploadProgress, setUploadProgress] = useState(0);
    const [aiStepBusyId, setAiStepBusyId] = useState(null);
    const [steps, setSteps] = useState([]);
    const [busy, setBusy] = useState(false);
    const [selectedStepId, setSelectedStepId] = useState(null);
    const [settingsOpen, setSettingsOpen] = useState(false);
    // apiKeyWarning removido — chaves são configuradas pelo administrador no painel admin
    const [imageEditorOpen, setImageEditorOpen] = useState(false);
    const [editingStepId, setEditingStepId] = useState(null);
    const [error, setError] = useState("");
    const [capturing, setCapturing] = useState(false);
    const [aiContext, setAiContext] = useState("");
    const [includeTimestamp, setIncludeTimestamp] = useState(() => {
        const v = lsGet(LS.includeTimestamp);
        return v === undefined ? true : v === "true";
    });
    const [savedPrompt, setSavedPrompt] = useState(() => {
        try {
            return lsGet(LS.savedPrompt) || "";
        } catch {
            return "";
        }
    });
    const [imageNamePrefix, setImageNamePrefix] = useState(() => {
        try {
            return lsGet(LS.imageNamePrefix) || "step_";
        } catch {
            return "step_";
        }
    });

    // === TEMPLATE DE DOCUMENTO ===
    const [selectedTemplateId, setSelectedTemplateId] = useState(() => {
        try {
            return (
                localStorage.getItem("CLIPBUILDER_TEMPLATE_ID") ||
                "clipbuilder_pro"
            );
        } catch {
            return "clipbuilder_pro";
        }
    });
    const [templateMetadata, setTemplateMetadata] = useState(() => {
        try {
            const raw = localStorage.getItem("CLIPBUILDER_TEMPLATE_METADATA");
            return raw ? JSON.parse(raw) : {};
        } catch {
            return {};
        }
    });

    // === NOVOS ESTADOS PARA MARKDOWN ===
    const [importModalOpen, setImportModalOpen] = useState(false);
    const [documentTitle, setDocumentTitle] = useState("");

    // === ESTADOS PARA ENHANCEMENT COM GEMINI ===
    const [enhanceLoading, setEnhanceLoading] = useState(false);
    const [enhancedMarkdown, setEnhancedMarkdown] = useState("");
    const [enhancePreviewOpen, setEnhancePreviewOpen] = useState(false);
    const [docProDropdownOpen, setDocProDropdownOpen] = useState(false);
    const docProDropdownRef = useRef(null);
    const [documentStatus, setDocumentStatus] = useState("em_progresso"); // em_progresso | pausado | concluido
    const [lastCompletedStep, setLastCompletedStep] = useState(0);
    const [documentOverview, setDocumentOverview] = useState("");
    const [documentGeneratedAt, setDocumentGeneratedAt] = useState(() =>
        new Date().toISOString(),
    );

    // === ESTADOS PARA TOOLS & AGENTES ===
    const [suggestion, setSuggestion] = useState(null);
    const [contextTags, setContextTags] = useState({}); // stepId -> context_tag string

    // === ESTADOS PARA GRAVAÇÃO DE GIF ===
    const [isRecordingGif, setIsRecordingGif] = useState(false);
    const [gifProgress, setGifProgress] = useState(0);
    const [gifBlob, setGifBlob] = useState(null);
    const [gifUrl, setGifUrl] = useState("");
    const [gifPreviewOpen, setGifPreviewOpen] = useState(false);
    const [isGeneratingGif, setIsGeneratingGif] = useState(false);
    const [gifDescribeLoading, setGifDescribeLoading] = useState(false);
    const [isGeneratingDoc, setIsGeneratingDoc] = useState(false);
    const [generationStage, setGenerationStage] = useState(""); // 'analyzing' | 'generating' | 'downloading'

    // Usuário autenticado (vem do AuthContext)
    const currentUser = authUser || null;

    const totalImageBytes = useMemo(() => {
        return steps.reduce((sum, s) => sum + (s.blob?.size ?? 0), 0);
    }, [steps]);

    /**
     * Verifica se a chave de API necessária está presente no localStorage.
     * Se ausente, abre o modal de configurações com um aviso explicativo.
     * @param {'gemini'|'gemini'|'any'} type
     * @returns {boolean} true se a chave está disponível, false caso contrário
     */
    const requireApiKey = useCallback(
        (type = "any") => {
            const keys = hasApiKeys();
            if (type === "gemini" && !keys.gemini) {
                setError(
                    "Chave de API Gemini não configurada. Solicite ao administrador do sistema que configure as chaves de IA.",
                );
                return false;
            }
            if (type === "any") {
                if (!keys.gemini) {
                    setError(
                        "Nenhuma chave de IA configurada. Solicite ao administrador do sistema que configure as chaves de API.",
                    );
                    return false;
                }
            }
            return true;
        },
        [setError],
    );

    // Fetch server-side AI key status on mount so hasApiKeys() considers
    // keys configured by the admin (env / DB) even when the user has none
    // in localStorage.
    useEffect(() => {
        fetchServerKeyStatus();
    }, []);

    // ── Cache: restaurar estado ao montar (ex: voltando do Admin) ──
    useEffect(() => {
        if (cacheRestoredRef.current) return;
        cacheRestoredRef.current = true;

        // Só restaurar se não há vídeo carregado (primeira montagem limpa)
        if (videoUrl || steps.length > 0) return;

        (async () => {
            try {
                const cached = await restoreDashboardCache();
                if (!cached) return;

                if (cached.videoUrl) setVideoUrl(cached.videoUrl);
                if (cached.videoId) setVideoId(cached.videoId);
                if (cached.videoSourceType)
                    setVideoSourceType(cached.videoSourceType);
                if (cached.youtubeUrl) setYoutubeUrl(cached.youtubeUrl);
                if (cached.steps && cached.steps.length > 0)
                    setSteps(cached.steps);
                if (cached.selectedStepId)
                    setSelectedStepId(cached.selectedStepId);
                if (cached.documentTitle)
                    setDocumentTitle(cached.documentTitle);
                if (cached.documentStatus)
                    setDocumentStatus(cached.documentStatus);
                if (cached.lastCompletedStep != null)
                    setLastCompletedStep(cached.lastCompletedStep);
                if (cached.documentOverview)
                    setDocumentOverview(cached.documentOverview);
                if (cached.documentGeneratedAt)
                    setDocumentGeneratedAt(cached.documentGeneratedAt);
                if (cached.aiStatus && cached.aiStatus !== "idle")
                    setAiStatus(cached.aiStatus);
                if (cached.aiContext) setAiContext(cached.aiContext);
                if (cached.videoFile) videoFileRef.current = cached.videoFile;

                console.info(
                    "[ClipBuilder] Estado restaurado do cache da sessão.",
                );
            } catch (err) {
                console.warn("[ClipBuilder] Falha ao restaurar cache:", err);
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ── Cache: salvar estado ao desmontar (ex: navegando para Admin) ──
    // Usamos refs para capturar os valores mais recentes sem re-registrar o effect.
    const cacheStateRef = useRef({});
    useEffect(() => {
        cacheStateRef.current = {
            videoUrl,
            videoId,
            videoSourceType,
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
            videoFile: videoFileRef.current,
        };
    });

    useEffect(() => {
        return () => {
            // Salvar cache ao desmontar o Dashboard
            const state = cacheStateRef.current;
            if (state.videoUrl || (state.steps && state.steps.length > 0)) {
                saveDashboardCache(state).catch((err) =>
                    console.warn(
                        "[ClipBuilder] Falha ao salvar cache no unmount:",
                        err,
                    ),
                );
            }
        };
    }, []);

    // ── Cache: salvar incrementalmente quando steps mudam ──
    useEffect(() => {
        if (!cacheRestoredRef.current) return;
        if (steps.length === 0 && !videoUrl) return;
        // Debounce: salvar 500ms após última mudança
        const timer = setTimeout(() => {
            cacheSteps(steps).catch(() => {});
            cacheSet("selectedStepId", selectedStepId);
        }, 500);
        return () => clearTimeout(timer);
    }, [steps, selectedStepId, videoUrl]);

    // ── Cache: salvar metadata quando campos-chave mudam ──
    useEffect(() => {
        if (!cacheRestoredRef.current) return;
        if (!videoUrl && steps.length === 0) return;
        const timer = setTimeout(() => {
            cacheSet("documentTitle", documentTitle);
            cacheSet("documentStatus", documentStatus);
            cacheSet("lastCompletedStep", lastCompletedStep);
            cacheSet("documentOverview", documentOverview);
            cacheSet("aiContext", aiContext);
            cacheSet("aiStatus", aiStatus);
            cacheSet("videoId", videoId);
            cacheSet("videoSourceType", videoSourceType);
            cacheSet("youtubeUrl", youtubeUrl);
            cacheSet("hasCache", true);
        }, 300);
        return () => clearTimeout(timer);
    }, [
        documentTitle,
        documentStatus,
        lastCompletedStep,
        documentOverview,
        aiContext,
        aiStatus,
        videoId,
        videoSourceType,
        youtubeUrl,
        videoUrl,
        steps.length,
    ]);

    useEffect(() => {
        function onKeyDown(e) {
            if (e.key === "Escape" && settingsOpen) {
                e.preventDefault();
                setSettingsOpen(false);
                return;
            }

            // Don't bind global shortcuts while modals are open
            if (settingsOpen || imageEditorOpen) return;

            // Avoid shortcuts while typing
            const el = document.activeElement;
            const tag = el?.tagName?.toLowerCase();
            const isTyping =
                tag === "textarea" || tag === "input" || el?.isContentEditable;
            if (isTyping) return;

            const k = (e.key || "").toLowerCase();
            if (k === "s") {
                e.preventDefault();
                captureFrame();
                return;
            }

            if (e.key === "Delete") {
                if (!selectedStepId) return;
                e.preventDefault();
                removeStep(selectedStepId);
            }
        }

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [steps, videoUrl, selectedStepId, settingsOpen, imageEditorOpen]);

    useEffect(() => {
        if (geminiModel) lsSet(LS.geminiModel, geminiModel);
    }, [geminiModel]);

    // Validate model selection against user permissions
    useEffect(() => {
        if (!currentUser) return;
        if (currentUser.role === "admin") return;

        const perms = currentUser.permissions || {};
        const isGemini = geminiModel?.startsWith("models/");
        const isWhisper = geminiModel === "whisper-large-v3-turbo";

        if (isGemini && perms.can_use_gemini === false) {
            if (perms.can_use_whisper !== false)
                setGeminiModel("whisper-large-v3-turbo");
        } else if (isWhisper && perms.can_use_whisper === false) {
            if (perms.can_use_gemini !== false)
                setGeminiModel("models/gemini-2.5-flash");
        }
    }, [currentUser, geminiModel, setGeminiModel]);

    useEffect(() => {
        lsSet(LS.includeTimestamp, includeTimestamp ? "1" : "0");
    }, [includeTimestamp]);

    useEffect(() => {
        if (!docProDropdownOpen) return;
        function handleClickOutside(e) {
            if (
                docProDropdownRef.current &&
                !docProDropdownRef.current.contains(e.target)
            ) {
                setDocProDropdownOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () =>
            document.removeEventListener("mousedown", handleClickOutside);
    }, [docProDropdownOpen]);

    async function handleLogout() {
        await signOut();
    }

    function onPickVideo(file) {
        setError("");
        setAiError("");

        if (!file) return;
        const ext = (file.name.split(".").pop() || "").toLowerCase();
        if (!["mp4", "mkv"].includes(ext)) {
            setError("Formato inválido. Use .mp4 ou .mkv");
            return;
        }

        if (videoUrl && String(videoUrl).startsWith("blob:"))
            URL.revokeObjectURL(videoUrl);
        videoFileRef.current = file;
        setVideoSourceType("local");
        setVideoUrl(URL.createObjectURL(file));
        setSteps([]);
        setVideoId(null);
        setAiStatus("uploading");
        uploadToGemini(file);
    }

    function clearVideo() {
        if (videoUrl && String(videoUrl).startsWith("blob:")) {
            try {
                URL.revokeObjectURL(videoUrl);
            } catch {}
        }
        if (youtubePollRef.current) {
            clearInterval(youtubePollRef.current);
            youtubePollRef.current = null;
        }
        videoFileRef.current = null;
        setVideoSourceType(null);
        setVideoUrl(null);
        setVideoId(null);
        setAiStatus("idle");
        setYoutubeUrl("");
        setYoutubeImporting(false);
        setError("");
        setAiError("");
        // Limpar cache da sessão ao descartar o vídeo
        clearDashboardCache();
    }


    async function importYoutube() {
        setError("");
        setAiError("");

        const url = (youtubeUrl || "").toString().trim();
        if (!url) {
            setError("Cole uma URL do YouTube para importar.");
            return;
        }

        setYoutubeImporting(true);
        setAiStatus("processing");
        try {
            const youtubeResponse = await api.post("/videos/youtube", { url });
            const id = youtubeResponse?.data?.video_id;
            if (!id) throw new Error("missing video_id");

            if (videoUrl && String(videoUrl).startsWith("blob:")) {
                try {
                    URL.revokeObjectURL(videoUrl);
                } catch {}
            }

            setSteps([]);
            setSelectedStepId(null);
            setVideoId(id);
            setVideoSourceType("youtube");
            videoFileRef.current = null;

            const base = (api.defaults.baseURL || "").replace(/\/$/, "");

            // Poll until backend finishes downloading.
            if (youtubePollRef.current) {
                clearInterval(youtubePollRef.current);
                youtubePollRef.current = null;
            }
            let failCount = 0;
            const startTime = Date.now();
            const MAX_POLL_TIME = 30 * 60 * 1000; // 30 minutes

            youtubePollRef.current = setInterval(async () => {
                // Safety: Stop polling if it takes too long
                if (Date.now() - startTime > MAX_POLL_TIME) {
                    clearInterval(youtubePollRef.current);
                    youtubePollRef.current = null;
                    setAiStatus("error");
                    setAiError("O processamento do vídeo excedeu o tempo limite (30 min). Verifique se o vídeo é muito longo ou tente novamente.");
                    setYoutubeImporting(false);
                    return;
                }

                try {
                    const statusResponse = await api.get(`/videos/${id}/status`);
                    const status = statusResponse?.data?.status;
                    failCount = 0; // reset on success

                    if (status === "ready") {
                        clearInterval(youtubePollRef.current);
                        youtubePollRef.current = null;
                        setVideoUrl(`${base}/videos/${id}/file`);
                        setAiStatus("ready");
                        setYoutubeImporting(false);
                    } else if (status === "error") {
                        clearInterval(youtubePollRef.current);
                        youtubePollRef.current = null;
                        setAiStatus("error");
                        setYoutubeImporting(false);
                        const err = statusResponse?.data?.error;
                        setAiError(err || "Falha ao importar do YouTube. Verifique a URL ou tente novamente mais tarde.");
                    }
                } catch (e) {
                    failCount++;
                    // If we fail too many times (e.g. 10 times * 3s = 30s of constant failures)
                    // it usually means the backend is down or the video ID is lost.
                    if (failCount > 10) {
                        clearInterval(youtubePollRef.current);
                        youtubePollRef.current = null;
                        setAiStatus("error");
                        setAiError("Perda de conexão com o servidor de processamento. Tente recarregar a página.");
                        setYoutubeImporting(false);
                    }
                }
            }, 3000);
        } catch (e) {
            setAiStatus("error");
            const detail = e?.response?.data?.detail;
            setAiError(detail || "Falha ao importar do YouTube. Verifique a URL ou tente novamente mais tarde.");
            setYoutubeImporting(false);
        }
    }

    useEffect(() => {
        return () => {
            if (youtubePollRef.current) {
                clearInterval(youtubePollRef.current);
                youtubePollRef.current = null;
            }
        };
    }, []);

    async function uploadToGemini(file) {
        try {
            setAiStatus("uploading");
            setUploadProgress(0);

            const chunkSize = 25 * 1024 * 1024; // 25MB
            const totalChunks = Math.ceil(file.size / chunkSize);
            const uploadId = generateUUID();

            let videoId = null;

            for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                const start = chunkIndex * chunkSize;
                const end = Math.min(start + chunkSize, file.size);
                const chunk = file.slice(start, end);

                const uploadRes = await api.post("/videos/raw", chunk, {
                    headers: {
                        "Content-Type": "application/octet-stream",
                        "X-Filename": file.name,
                        "X-Upload-Id": uploadId,
                        "X-Chunk-Index": chunkIndex.toString(),
                        "X-Total-Chunks": totalChunks.toString(),
                    },
                });

                const progress = Math.round(((chunkIndex + 1) / totalChunks) * 100);
                setUploadProgress(progress);

                if (uploadRes?.data?.video_id) {
                    videoId = uploadRes.data.video_id;
                }
            }

            if (!videoId) {
                throw new Error("missing video_id after chunked upload");
            }
            setVideoId(videoId);

            setAiStatus("processing");
            setAiStatus("ready");
        } catch (e) {
            setAiStatus("error");
            const detail = e?.response?.data?.detail;
            setAiError(detail || "Falha ao processar o vídeo com IA. Tente novamente mais tarde.");
        }
    }

    async function captureFrame() {
        setError("");

        if (capturing) return;
        setCapturing(true);

        try {
            const video = videoRef.current;
            const canvas = canvasRef.current;
            if (!video || !canvas) {
                setError("Vídeo não disponível para captura.");
                return;
            }

            if (!videoUrl) {
                setError("Faça upload de um vídeo primeiro.");
                return;
            }

            if (!video.videoWidth || !video.videoHeight) {
                setError("Vídeo ainda não está pronto para captura.");
                return;
            }

            try {
                video.pause();
            } catch {
                // ignore
            }

            const seconds = Math.max(0, Number(video.currentTime) || 0);
            console.log("[captureFrame] Captured seconds:", seconds, "video.currentTime:", video.currentTime);
            const timestamp = formatTimestamp(seconds);

            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext("2d", { willReadFrequently: true });
            if (!ctx) {
                setError("Não foi possível capturar o frame (canvas).");
                return;
            }

            try {
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            } catch (e) {
                console.error("[captureFrame] drawImage failed:", e);
                setError(
                    "Falha ao desenhar o vídeo no canvas. (Possível problema de CORS)",
                );
                return;
            }

            // Check if canvas is tainted before trying toBlob
            try {
                ctx.getImageData(0, 0, 1, 1);
            } catch (e) {
                console.error("[captureFrame] Canvas tainted (CORS):", e);
                setError(
                    "Não foi possível capturar o frame: o vídeo está protegido por CORS. Tente recarregar a página (F5).",
                );
                return;
            }

            let blob = null;
            try {
                blob = await new Promise((resolve) =>
                    canvas.toBlob(resolve, "image/png"),
                );
            } catch (e) {
                console.error("[captureFrame] toBlob failed:", e);
                setError(
                    "Falha ao exportar o frame. (Possível problema de CORS)",
                );
                return;
            }
            if (!blob) {
                setError(
                    "Falha ao gerar imagem do frame. (Possível problema de CORS)",
                );
                return;
            }


            let description = "";
            let stepSuggestion = null;
            let stepContextTag = null;

            const newStepId = generateUUID();
            const url = URL.createObjectURL(blob);

            // Handle suggestion from tools
            if (stepSuggestion) {
                setSuggestion(stepSuggestion);
            }

            // Handle context_tag from tools
            if (stepContextTag) {
                setContextTags((prev) => ({
                    ...prev,
                    [newStepId]: stepContextTag,
                }));
            }

            setSteps((prev) => [
                ...prev,
                {
                    id: newStepId,
                    blob,
                    url,
                    description,
                    timestamp,
                    seconds,
                    has_image: true,
                },
            ]);
        } catch (e) {
            console.error("[captureFrame] Unexpected error:", e);
            setError(
                "Erro inesperado ao capturar frame. Tente recarregar a página.",
            );
        } finally {
            setCapturing(false);
        }
    }

    function createTextStep() {
        setError("");
        setAiError("");
        const id = generateUUID();
        setSteps((prev) => [
            ...prev,
            {
                id,
                description: "",
                timestamp: "",
                seconds: null,
                blob: null,
                url: "",
                has_image: false,
            },
        ]);
        setSelectedStepId(id);
    }

    function updateDescription(id, description) {
        setSteps((prev) =>
            prev.map((s) => (s.id === id ? { ...s, description } : s)),
        );
    }

    function updateStepImage(id, blob) {
        if (!blob) return;
        setSteps((prev) => {
            return prev.map((s) => {
                if (s.id !== id) return s;
                try {
                    if (s.url) URL.revokeObjectURL(s.url);
                } catch {}
                const url = URL.createObjectURL(blob);
                return { ...s, blob, url, has_image: true };
            });
        });
    }

    function removeStep(id) {
        setSteps((prev) => {
            const step = prev.find((s) => s.id === id);
            if (step?.url) URL.revokeObjectURL(step.url);
            return prev.filter((s) => s.id !== id);
        });
        // Limpar blob do cache IndexedDB
        removeCachedStepBlob(id).catch(() => {});
    }
    async function generateWithAI(id) {
        setAiError("");

        if (!videoId || aiStatus !== "ready") {
            setAiError(
                'IA não está pronta. Faça upload do vídeo e aguarde "IA pronta".',
            );
            return;
        }

        const step = steps.find((s) => s.id === id);

        // Para GIFs, usar endpoint /describe-gif (Gemini)
        if (step?.is_gif && step?.blob) {
            if (!requireApiKey("gemini")) return;
            setAiStepBusyId(id);
            try {
                const form = new FormData();
                form.append(
                    "file",
                    new File([step.blob], "clipbuilder.gif", {
                        type: "image/gif",
                    }),
                );
                if (documentTitle && documentTitle.trim()) {
                    form.append("document_title", documentTitle.trim());
                }
                const contextParts = [];
                if (documentTitle && documentTitle.trim()) {
                    contextParts.push(`Título: ${documentTitle.trim()}`);
                }
                steps.forEach((s, i) => {
                    if (s.id !== id && s.description && s.description.trim()) {
                        contextParts.push(
                            `Passo ${i + 1}: ${s.description.trim()}`,
                        );
                    }
                });
                if (contextParts.length > 0) {
                    form.append("document_context", contextParts.join("\n"));
                }

                const gifDescriptionResponse = await api.post("/describe-gif", form, {
                    headers: { "Content-Type": "multipart/form-data" },
                });
                const text = gifDescriptionResponse?.data?.description;
                if (text && typeof text === "string" && text.trim()) {
                    updateDescription(id, text.trim());
                }
            } catch (e) {
                const status = e?.response?.status;
                const detail = e?.response?.data?.detail;
                if (status === 401) {
                    setError(
                        detail ||
                            "Chave de API Gemini não configurada. Preencha sua chave no 'Ajuste de templates' para usar os recursos de IA.",
                    );
                    setSettingsOpen(true);
                } else if (status === 429) {
                    setAiError(
                        detail || "Limite/quota do Gemini excedida (429).",
                    );
                } else {
                    setAiError("Falha ao descrever GIF com IA. Tente novamente.");
                }
            } finally {
                setAiStepBusyId(null);
            }
            return;
        }

        // Para frames normais, precisa de timestamp
        if (!step?.timestamp) {
            setAiError("Não foi possível determinar o timestamp deste frame.");
            return;
        }

        // Verificar chave necessária para o modelo selecionado
        const isGeminiModel = geminiModel && !geminiModel.startsWith("models/");
        if (!requireApiKey("gemini")) return;

        setAiStepBusyId(id);
        try {
            const params = {
                model: geminiModel,
                t: step.seconds ?? 0,
                include_timestamp: includeTimestamp,
            };
            if (aiContext) params.prompt = aiContext;
            const res = await api.get(`/videos/${videoId}/smart-text`, {
                params,
            });
            const text = (res?.data?.text ?? "").toString();
            updateDescription(id, text);
        } catch (e) {
            const status = e?.response?.status;
            const detail = e?.response?.data?.detail;
            if (status === 401) {
                setError(
                    detail ||
                        "Chave de API não configurada. Preencha sua chave no 'Ajuste de templates' para usar os recursos de IA.",
                );
                setSettingsOpen(true);
            } else if (status === 429) {
                setAiError(detail || "Limite/quota do Gemini excedida (429).");
            } else {
                setAiError("Falha ao descrever com IA. Tente novamente.");
            }
        } finally {
            setAiStepBusyId(null);
        }
    }

    // === EXPORTAÇÃO/IMPORTAÇÃO MARKDOWN ===

    async function exportMarkdownDoc() {
        setError("");
        if (steps.length === 0) {
            setError("Capture pelo menos um passo antes de exportar Markdown.");
            setSettingsOpen(true);
            return;
        }

        if (!documentTitle || !documentTitle.trim()) {
            setError("Preencha o título do documento antes de exportar.");
            return;
        }

        const rawPrefix = (imageNamePrefix || "").toString().trim();
        if (!rawPrefix) {
            setError(
                "Preencha o prefixo do nome dos arquivos de imagem no 'Ajuste de templates' antes de exportar.",
            );
            setSettingsOpen(true);
            return;
        }

        if (!documentTitle || !documentTitle.trim()) {
            setError("Preencha o título do documento antes de exportar.");
            return;
        }

        setBusy(true);
        try {
            // Importar JSZip dinamicamente
            const JSZip = (await import("jszip")).default;
            const zip = new JSZip();

            const sanitizePrefix = (raw) => {
                let v = (raw || "").toString().trim();
                if (!v) return "step_";
                v = v.replace(/\.png$/i, "");
                v = v.replace(/[\\/]/g, "_");
                v = v.replace(/\s+/g, "_");
                v = v.replace(/[^a-zA-Z0-9._-]/g, "_");
                v = v.slice(0, 60);
                return v || "step_";
            };

            const prefix = sanitizePrefix(rawPrefix);

            // Preparar steps com campos expandidos para o Markdown
            const enrichedSteps = steps.map((step, idx) => ({
                ...step,
                title: step.title || `Passo ${idx + 1}`,
                userAction: step.userAction || step.description || "",
                expectedResult: step.expectedResult || "",
                observations: step.observations || "",
                imageName:
                    step.has_image && step.blob
                        ? `images/${prefix}${String(idx + 1).padStart(2, "0")}.png`
                        : "",
            }));

            const metadata = {
                title: documentTitle,
                status: documentStatus,
                videoSource: videoId || youtubeUrl || "local",
                lastCompletedStep: lastCompletedStep,
                generatedAt: documentGeneratedAt,
            };

            // Gerar o markdown com schema completo (frontmatter válido)
            const markdown = generateMarkdown(
                enrichedSteps,
                metadata,
                documentOverview,
            );

            // Adicionar o markdown ao ZIP
            const safeTitle =
                (documentTitle || "documento")
                    .normalize("NFD")
                    .replace(/[\u0300-\u036f]/g, "")
                    .replace(/[^a-zA-Z0-9 _-]/g, "_")
                    .replace(/\s+/g, " ")
                    .trim()
                    .slice(0, 50) || "documento";
            zip.file(`${safeTitle}.md`, markdown);

            // Criar pasta de imagens e adicionar as imagens
            const imagesFolder = zip.folder("images");
            steps.forEach((step, idx) => {
                if (step.has_image && step.blob) {
                    const imageName = `${prefix}${String(idx + 1).padStart(2, "0")}.png`;
                    imagesFolder.file(imageName, step.blob);
                }
            });

            // Gerar o arquivo ZIP
            const zipBlob = await zip.generateAsync({ type: "blob" });
            const filename = `${safeTitle}_backup.zip`;
            downloadBlob(zipBlob, filename);
        } catch (e) {
            console.error("Erro ao exportar:", e);
            setError(
                "Falha ao exportar Markdown: " +
                    (e.message || "Erro desconhecido"),
            );
        } finally {
            setBusy(false);
        }
    }

    function handleImportMarkdown(parsed, rawContent, images = {}) {
        if (!parsed || !parsed.isValid) {
            setError("Arquivo Markdown inválido.");
            return;
        }

        // Restaurar metadados
        if (parsed.metadata.title) setDocumentTitle(parsed.metadata.title);
        if (parsed.metadata.status) setDocumentStatus(parsed.metadata.status);
        if (parsed.metadata.lastCompletedStep !== undefined)
            setLastCompletedStep(parsed.metadata.lastCompletedStep);
        if (parsed.metadata.generatedAt)
            setDocumentGeneratedAt(parsed.metadata.generatedAt);
        if (parsed.metadata.videoSource)
            setVideoSource(parsed.metadata.videoSource);
        if (parsed.overview) setDocumentOverview(parsed.overview);

        // Converter passos importados para o formato do app
        const importedSteps = parsed.steps.map((step, idx) => {
            // Tentar encontrar a imagem correspondente
            const stepNum = String(idx + 1).padStart(2, "0");
            let imageBlob = null;
            let imageUrl = "";

            // Procurar imagem pelo nome do passo
            for (const [imageName, blob] of Object.entries(images)) {
                // Verificar se o nome da imagem corresponde ao passo
                if (
                    imageName.includes(stepNum) ||
                    imageName.includes(`step_${stepNum}`) ||
                    imageName.includes(`passo_${stepNum}`)
                ) {
                    imageBlob = blob;
                    imageUrl = URL.createObjectURL(blob);
                    break;
                }
            }

            // Se não encontrou por número, tentar pelo imageName do passo
            if (!imageBlob && step.imageName && images[step.imageName]) {
                imageBlob = images[step.imageName];
                imageUrl = URL.createObjectURL(imageBlob);
            }

            return {
                id: step.id || generateUUID(),
                description: step.description || "",
                userAction: step.userAction || "",
                expectedResult: step.expectedResult || "",
                observations: step.observations || "",
                timestamp: step.timestamp || "",
                seconds: null,
                title: step.title || "",
                completed: step.completed || false,
                has_image: !!imageBlob,
                blob: imageBlob,
                url: imageUrl,
            };
        });

        setSteps(importedSteps);
        setSelectedStepId(
            importedSteps.length > 0 ? importedSteps[0].id : null,
        );
    }

    function markStepCompleted(stepIndex) {
        setSteps((prev) =>
            prev.map((s, idx) =>
                idx === stepIndex ? { ...s, completed: !s.completed } : s,
            ),
        );

        // Atualizar último passo concluído
        let lastCompleted = 0;
        steps.forEach((step, idx) => {
            if (idx === stepIndex ? !step.completed : step.completed) {
                lastCompleted = idx + 1;
            }
        });
        setLastCompletedStep(lastCompleted);
    }

    // Função auxiliar para videoSource (usado na importação)
    function setVideoSource(source) {
        // Se for uma URL do YouTube, configurar para importação
        if (source && source.includes("youtube")) {
            setYoutubeUrl(source);
        }
    }

    // === FUNÇÃO DE ENHANCEMENT COM GEMINI (Doc Pro) ===
    async function enhanceAndExport(format) {
        setError("");
        setAiError("");

        if (steps.length === 0) {
            setError(
                "Capture pelo menos um passo antes de gerar o documento profissional.",
            );
            setSettingsOpen(true);
            return;
        }

        if (!documentTitle || !documentTitle.trim()) {
            setError("Preencha o título do documento antes de exportar.");
            return;
        }

        const rawPrefix = (imageNamePrefix || "").toString().trim();
        if (!rawPrefix) {
            setError(
                "Preencha o prefixo do nome dos arquivos de imagem no 'Ajuste de templates' antes de exportar.",
            );
            setSettingsOpen(true);
            return;
        }

        if (!documentTitle || !documentTitle.trim()) {
            setError("Preencha o título do documento antes de exportar.");
            return;
        }

        // Doc Pro usa Gemini (enhance-document)
        if (!requireApiKey("gemini")) return;

        const title = documentTitle || "Documento Sem Título";
        const safeTitle = (title || "documento")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/[^a-zA-Z0-9 _-]/g, "_")
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 50);

        setEnhanceLoading(true);
        try {
            const stepsPayload = steps.map((step, idx) => ({
                description: step.description || "",
                has_image: !!step.has_image,
                title: step.title || `Passo ${idx + 1}`,
                userAction: step.userAction || step.description || "",
                expectedResult: step.expectedResult || "",
                observations: step.observations || "",
            }));

            if (import.meta.env.DEV) {
                console.debug(
                    "[enhanceAndExport] Template:",
                    selectedTemplateId,
                    "| metadata:",
                    templateMetadata,
                );
            }

            const response = await api.post("/enhance-document", {
                title,
                steps: stepsPayload,
                template_id: selectedTemplateId || null,
            });

            const markdown = response?.data?.markdown || "";
            if (!markdown) {
                throw new Error("Resposta vazia do servidor");
            }

            if (format === "md") {
                setEnhancedMarkdown(markdown);
                setEnhancePreviewOpen(true);
                return;
            }

            if (format === "docx") {
                if (import.meta.env.DEV) {
                    console.debug(
                        "[enhanceAndExport→docx] Template:",
                        selectedTemplateId,
                        "| metadata:",
                        templateMetadata,
                    );
                }
                const imageMap = await buildImageMapFromSteps(steps);
                await downloadMarkdownAsDocx(
                    markdown,
                    `${safeTitle}.docx`,
                    true,
                    imageMap,
                    selectedTemplateId,
                    templateMetadata,
                );
                return;
            }
            if (format === "pdf") {
                const imageMap = await buildImageMapFromSteps(steps);
                await downloadMarkdownAsPdf(
                    markdown,
                    `${safeTitle}.pdf`,
                    imageMap,
                );
                return;
            }
            if (format === "html") {
                await downloadMarkdownAsHtml(markdown, `${safeTitle}.html`);
                return;
            }
        } catch (e) {
            const status = e?.response?.status;
            const detail = e?.response?.data?.detail ?? e?.parsedDetail;
            if (status === 401) {
                setError(
                    detail ||
                        "Chave de API não configurada. Preencha sua chave no 'Ajuste de templates' para usar os recursos de IA.",
                );
                setSettingsOpen(true);
            } else if (status === 429) {
                setAiError(
                    detail ||
                        "Limite de requisições da IA excedido. Tente novamente em alguns segundos.",
                );
            } else if (status === 400) {
                setAiError(detail || "Erro nos dados enviados.");
            } else {
                setAiError(detail || "Falha ao gerar o arquivo DOCX.");
            }
        } finally {
            setEnhanceLoading(false);
        }
    }

    async function exportDoc() {
        setError("");
        if (steps.length === 0) {
            setError("Capture pelo menos um frame antes de exportar.");
            setSettingsOpen(true);
            return;
        }

        if (!documentTitle || !documentTitle.trim()) {
            setError("Preencha o título do documento antes de exportar.");
            return;
        }

        const rawPrefix = (imageNamePrefix || "").toString().trim();
        if (!rawPrefix) {
            setError(
                "Preencha o prefixo do nome dos arquivos de imagem no 'Ajuste de templates' antes de exportar.",
            );
            setSettingsOpen(true);
            return;
        }

        const parseFilenameFromContentDisposition = (value) => {
            const cd = (value || "").toString();
            // RFC 5987 / RFC 6266
            const mStar = cd.match(/filename\*=UTF-8''([^;\n]+)/i);
            if (mStar && mStar[1]) {
                try {
                    return decodeURIComponent(
                        mStar[1].trim().replace(/^"|"$/g, ""),
                    );
                } catch {
                    return mStar[1].trim().replace(/^"|"$/g, "");
                }
            }
            const m = cd.match(/filename=([^;\n]+)/i);
            if (m && m[1]) return m[1].trim().replace(/^"|"$/g, "");
            return "";
        };

        const sanitizePrefix = (raw) => {
            let v = (raw || "").toString().trim();
            if (!v) return "step_";
            // If user typed an extension, drop it to avoid "foo.png01.png"
            v = v.replace(/\.png$/i, "");
            // Remove path separators and keep it filename-friendly
            v = v.replace(/[\\/]/g, "_");
            v = v.replace(/\s+/g, "_");
            v = v.replace(/[^a-zA-Z0-9._-]/g, "_");
            v = v.slice(0, 60);
            return v || "step_";
        };

        const prefix = sanitizePrefix(rawPrefix);

        setBusy(true);
        try {
            const form = new FormData();
            form.append(
                "steps",
                JSON.stringify(
                    steps.map((s, idx) => ({
                        description: s.description ?? "",
                        has_image: !!(s?.has_image && s?.blob),
                        title: s.title || `Passo ${idx + 1}`,
                        userAction: s.userAction || s.description || "",
                        expectedResult: s.expectedResult || "",
                        observations: s.observations || "",
                    })),
                ),
            );
            form.append("image_name_prefix", prefix);
            form.append("output_format", "markdown");

            // Only send images for steps that actually have them.
            steps.forEach((s, idx) => {
                if (!s?.blob || !s?.has_image) return;
                const file = new File(
                    [s.blob],
                    `${prefix}${String(idx + 1).padStart(2, "0")}.png`,
                    { type: "image/png" },
                );
                form.append("images", file);
            });

            const res = await api.post("/export", form, {
                responseType: "blob",
            });

            const cd = res?.headers?.["content-disposition"];
            const serverName = parseFilenameFromContentDisposition(cd);
            const fallbackName = "clipbuilder_export.zip";
            downloadBlob(res.data, serverName || fallbackName);
        } catch (e) {
            const status = e?.response?.status;
            let detail = e?.response?.data?.detail;

            // When responseType is 'blob', error bodies come as Blob (even for JSON).
            if (!detail && e?.response?.data instanceof Blob) {
                try {
                    const text = await e.response.data.text();
                    try {
                        const parsed = JSON.parse(text);
                        detail = parsed?.detail || text;
                    } catch {
                        detail = text;
                    }
                } catch {}
            }
            if (status === 413) {
                setError(
                    "Payload muito grande para exportar. Tente menos passos ou frames menores.",
                );
            } else if (status) {
                setError(
                    detail
                        ? `Falha ao exportar: ${detail}`
                        : `Falha ao exportar (HTTP ${status}).`,
                );
            } else {
                setError(
                    "Falha ao exportar. Verifique se o backend está rodando.",
                );
            }
        } finally {
            setBusy(false);
        }
    }

    function reorderSteps(fromId, toId) {
        if (!fromId || !toId || fromId === toId) return;
        setSteps((prev) => {
            const fromIndex = prev.findIndex((s) => s.id === fromId);
            const toIndex = prev.findIndex((s) => s.id === toId);
            if (fromIndex === -1 || toIndex === -1 || fromIndex === toIndex) {
                return prev;
            }
            const next = [...prev];
            const [moved] = next.splice(fromIndex, 1);
            next.splice(toIndex, 0, moved);
            return next;
        });
    }

    // Handlers to pass to Sidebar
    function handleSelectStep(id) {
        setSelectedStepId(id);
    }

    function handleEditImage(id) {
        const step = steps.find((s) => s.id === id);
        if (!step?.url || !step?.blob || !step?.has_image) return;
        setEditingStepId(id);
        setImageEditorOpen(true);
    }

    // === FUNÇÕES DE GRAVAÇÃO DE GIF ===
    function startGifRecording() {
        if (!videoRef.current || !canvasRef.current || !videoUrl) {
            setError("Carregue um vídeo primeiro para gravar GIF.");
            return;
        }

        setError("");
        setIsRecordingGif(true);
        setGifProgress(0);

        const video = videoRef.current;
        const canvas = canvasRef.current;

        // Configurar canvas com tamanho do vídeo
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d");

        // Criar encoder GIF
        const gif = new GIF({
            workers: 2,
            quality: 10,
            width: canvas.width,
            height: canvas.height,
            workerScript: "/gif.worker.js",
        });

        gifEncoderRef.current = gif;

        // Iniciar o vídeo se estiver pausado
        if (video.paused) {
            video.play().catch(() => {});
        }

        // Capturar frames a cada 100ms (10 FPS)
        gifFrameIntervalRef.current = setInterval(() => {
            try {
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                gif.addFrame(ctx, { copy: true, delay: 100 });
            } catch (e) {
                console.error("Erro ao capturar frame:", e);
            }
        }, 100);
    }

    function stopGifRecording() {
        setIsRecordingGif(false);

        // Parar captura de frames
        if (gifFrameIntervalRef.current) {
            clearInterval(gifFrameIntervalRef.current);
            gifFrameIntervalRef.current = null;
        }

        // Pausar vídeo
        if (videoRef.current) {
            videoRef.current.pause();
        }

        const gif = gifEncoderRef.current;
        if (!gif) return;

        setIsGeneratingGif(true);
        setGifPreviewOpen(true);

        gif.on("progress", (p) => {
            setGifProgress(p);
        });

        gif.on("finished", (blob) => {
            setGifBlob(blob);
            setGifUrl(URL.createObjectURL(blob));
            setIsGeneratingGif(false);
            gifEncoderRef.current = null;
        });

        gif.render();
    }

    async function addGifAsStep() {
        if (!gifBlob) return;

        // Gemini é usado para descrever GIFs
        if (!requireApiKey("gemini")) return;

        setGifDescribeLoading(true);
        let description = "GIF animado";

        // Capturar timestamp do momento atual do vídeo (se disponível)
        const video = videoRef.current;
        const seconds = video
            ? Math.max(0, Number(video.currentTime) || 0)
            : null;
        const timestamp = seconds !== null ? formatTimestamp(seconds) : "";

        // Gerar thumbnail do primeiro frame do GIF
        let thumbnailUrl = null;
        try {
            const img = new Image();
            img.crossOrigin = "anonymous";
            await new Promise((resolve, reject) => {
                img.onload = resolve;
                img.onerror = reject;
                img.src = gifUrl;
            });
            const canvas = document.createElement("canvas");
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(img, 0, 0);
            thumbnailUrl = canvas.toDataURL("image/png");
        } catch (_) {
            // Se falhar, thumbnailUrl fica null e o GifStepPreview tentará extrair
        }

        try {
            const form = new FormData();
            form.append(
                "file",
                new File([gifBlob], "clipbuilder.gif", { type: "image/gif" }),
            );
            if (documentTitle && documentTitle.trim()) {
                form.append("document_title", documentTitle.trim());
            }
            const contextParts = [];
            if (documentTitle && documentTitle.trim()) {
                contextParts.push(`Título: ${documentTitle.trim()}`);
            }
            steps.forEach((s, i) => {
                if (s.description && s.description.trim()) {
                    contextParts.push(
                        `Passo ${i + 1}: ${s.description.trim()}`,
                    );
                }
            });
            if (contextParts.length > 0) {
                form.append("document_context", contextParts.join("\n"));
            }

            const descriptionResponse = await api.post("/describe-gif", form, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            const text = descriptionResponse?.data?.description;
            if (text && typeof text === "string" && text.trim()) {
                description = text.trim();
            }
        } catch (e) {
            // Se for 401 (chave ausente), abrir modal de configurações
            const status = e?.response?.status;
            const detail = e?.response?.data?.detail;
            if (status === 401) {
                setError(
                    detail ||
                        "Chave de API Gemini não configurada. Preencha sua chave no 'Ajuste de templates' para usar os recursos de IA.",
                );
                setSettingsOpen(true);
            }
            // Keep fallback "GIF animado" para outros erros
        } finally {
            setGifDescribeLoading(false);
        }

        const id = generateUUID();
        // Criar novo blob URL para o passo (o gifUrl original será revogado no closeGifPreview)
        const stepGifUrl = URL.createObjectURL(gifBlob);
        setSteps((prev) => [
            ...prev,
            {
                id,
                blob: gifBlob,
                url: stepGifUrl,
                thumbnailUrl,
                description,
                timestamp,
                seconds,
                has_image: true,
                is_gif: true,
            },
        ]);
        setSelectedStepId(id);
        closeGifPreview();
    }

    function downloadGif() {
        if (!gifBlob) return;
        downloadBlob(gifBlob, `clipbuilder_gif_${Date.now()}.gif`);
    }

    function closeGifPreview() {
        setGifPreviewOpen(false);
        setGifBlob(null);
        if (gifUrl) {
            URL.revokeObjectURL(gifUrl);
            setGifUrl("");
        }
        setGifProgress(0);
        setIsGeneratingGif(false);
    }

    async function handleGenerateDocumentation() {
        if (!gifBlob) return;
        // Usa Gemini para descrever + gerar documentação
        if (!requireApiKey("gemini")) return;
        setIsGeneratingDoc(true);
        setGenerationStage("analyzing");
        setAiError("");

        try {
            // Stage 1: Describe GIF (Extract context)
            // Send as Multipart form data - efficient for large files
            const form = new FormData();
            form.append(
                "file",
                new File([gifBlob], "clipbuilder.gif", { type: "image/gif" }),
            );

            // Add minimal context
            if (documentTitle) form.append("document_title", documentTitle);

            const descriptionResponse = await api.post("/describe-gif", form, {
                headers: { "Content-Type": "multipart/form-data" },
            });

            const description =
                descriptionResponse?.data?.description ||
                "Procedimento demonstrado no GIF (análise automática indisponível)";

            // Generate Thumbnail for DocContext
            let thumbBase64 = null;
            try {
                const img = new Image();
                img.src = URL.createObjectURL(gifBlob);
                await new Promise((resolve) => (img.onload = resolve));

                const canvas = document.createElement("canvas");
                const scale = Math.min(1, 800 / img.naturalWidth);
                canvas.width = img.naturalWidth * scale;
                canvas.height = img.naturalHeight * scale;
                const ctx = canvas.getContext("2d");
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

                thumbBase64 = canvas.toDataURL("image/jpeg", 0.8).split(",")[1];
            } catch (err) {
                console.warn("Thumbnail generation failed", err);
            }

            // Stage 2: Generate Structured Document (with Text + Thumbnail)
            setGenerationStage("generating");

            const res = await api.post(
                "/generate-documentation",
                {
                    title: documentTitle || "Procedimento",
                    steps: [
                        {
                            description: description,
                            has_image: !!thumbBase64,
                        },
                    ],
                    images: thumbBase64 ? [thumbBase64] : [],
                    output_format: "docx",
                    template_id: selectedTemplateId || null,
                    template_metadata: templateMetadata || {},
                },
                {
                    responseType: "blob",
                },
            );

            setGenerationStage("downloading");
            const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
            downloadBlob(res.data, `procedimento_${timestamp}.docx`);
            closeGifPreview();
        } catch (e) {
            console.error(e);
            const status = e?.response?.status;
            let msg = e.message;
            if (e.response?.data instanceof Blob) {
                try {
                    const text = await e.response.data.text();
                    const parsed = JSON.parse(text);
                    msg = parsed.detail || msg;
                    if (status === 401) {
                        setError(
                            parsed.detail ||
                                "Chave de API não configurada. Preencha sua chave no 'Ajuste de templates' para usar os recursos de IA.",
                        );
                        setSettingsOpen(true);
                        return;
                    }
                } catch {}
            } else if (e.response?.data?.detail) {
                msg = e.response.data.detail;
            }
            if (status === 401) {
                setError(
                    msg ||
                        "Chave de API não configurada. Preencha sua chave no 'Ajuste de templates' para usar os recursos de IA.",
                );
                setSettingsOpen(true);
                return;
            }
            setAiError("Falha ao gerar documentação: " + msg);
        } finally {
            setIsGeneratingDoc(false);
            setGenerationStage("");
        }
    }

    const editingStep = steps.find((s) => s.id === editingStepId) || null;

    return (
        <div className="cb-app-shell min-h-screen" style={{ background: "transparent", color: "var(--text)", position: "relative" }}>
            <LoginBackground />
            <Header
                exportDoc={exportDoc}
                busy={busy}
                user={currentUser}
                onLogout={handleLogout}
            />

            <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-6 py-8 lg:grid-cols-[1fr_440px]">

                <MouseTilt className="animate-fade-up">
                    <section className="h-full p-6 rounded-3xl" style={{ backgroundColor: "var(--glass-bg)", backdropFilter: "blur(12px)" }}>
                        <div className="flex flex-col items-center gap-8">
                            <VideoArea
                                videoUrl={videoUrl}
                                videoRef={videoRef}
                                canvasRef={canvasRef}
                                onPickVideo={onPickVideo}
                                youtubeUrl={youtubeUrl}
                                setYoutubeUrl={setYoutubeUrl}
                                onImportYoutube={importYoutube}
                                youtubeImporting={youtubeImporting}
                                capturing={capturing}
                                aiStatus={aiStatus}
                                aiError={aiError}
                                uploadProgress={uploadProgress}
                                isRecordingGif={isRecordingGif}
                                onStartGifRecording={startGifRecording}
                                onStopGifRecording={stopGifRecording}
                                onClearVideo={clearVideo}
                                onDismissError={() => {
                                    setAiStatus("idle");
                                    setAiError("");
                                }}
                                onManualUpload={onPickVideo}
                            />

                        <div className="w-full max-w-[960px]">
                            {steps.length === 0 ? (
                                <div className="text-center py-4">
                                    <div
                                        className="text-sm font-medium mb-1"
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Capture frames para montar o tutorial
                                    </div>
                                    <div
                                        className="text-xs"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        Use a tecla{" "}
                                        <kbd
                                            className="px-1.5 py-0.5 rounded text-xs font-mono border"
                                            style={{
                                                borderColor:
                                                    "var(--card-border)",
                                                backgroundColor:
                                                    "var(--card-bg)",
                                            }}
                                        >
                                            S
                                        </kbd>{" "}
                                        para capturar rapidamente
                                    </div>
                                </div>
                            ) : (
                                <div className="text-center py-4">
                                    <div
                                        className="text-sm font-medium"
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Selecione um passo à direita para editar
                                    </div>
                                </div>
                            )}
                        </div>
                        <div className="w-full max-w-[960px]">
                            <div className="space-y-5">
                                {/* Criar: adicionar ao tutorial */}
                                <div>
                                    <div
                                        className="text-xs font-medium mb-2"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        Adicionar ao tutorial
                                    </div>
                                    <div className="grid grid-cols-1 gap-3">
                                        <button
                                            onClick={captureFrame}
                                            disabled={!videoUrl || capturing}
                                            className="cb-btn cb-btn-primary w-full h-12 text-base font-semibold"
                                            title="Pause no vídeo e capture (tecla S)"
                                        >
                                            <Play className="h-5 w-5" />
                                            {capturing
                                                ? "Capturando..."
                                                : "Capturar Frame"}
                                        </button>
                                    </div>
                                </div>

                                {/* Ajustes + Finalizar: mesma linha em telas médias */}
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                                    <div>
                                        <div
                                            className="text-xs font-medium mb-2"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Projeto
                                        </div>
                                        <div className="grid grid-cols-2 gap-3">
                                            <button
                                                onClick={() =>
                                                    setSettingsOpen(true)
                                                }
                                                className="cb-btn w-full h-11"
                                                title="Ajustar templates, IA e exportação"
                                            >
                                                <Settings className="h-4 w-4" />
                                                Ajuste de templates
                                            </button>
                                            <button
                                                onClick={() =>
                                                    setImportModalOpen(true)
                                                }
                                                className="cb-btn w-full h-11"
                                                title="Importar projeto (.md)"
                                            >
                                                <Upload className="h-4 w-4" />
                                                Importar
                                            </button>
                                        </div>
                                    </div>
                                    <div>
                                        <div
                                            className="text-xs font-medium mb-2"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Exportar
                                        </div>
                                        <div className={`grid gap-3 ${currentUser?.role === 'admin' || currentUser?.permissions?.can_export_md === true ? 'grid-cols-2' : 'grid-cols-1'}`}>
                                            {(currentUser?.role === "admin" || currentUser?.permissions?.can_export_md === true) && (
                                                <button
                                                    onClick={exportMarkdownDoc}
                                                    disabled={busy || steps.length === 0}
                                                    className="cb-btn w-full h-11 disabled:opacity-50 disabled:cursor-not-allowed"
                                                    title="Salvar projeto (.md + imagens)"
                                                >
                                                    <Download className="h-4 w-4" />
                                                    {busy
                                                        ? "Salvando..."
                                                        : "Exportar .md"}
                                                </button>
                                            )}
                                            <div ref={docProDropdownRef} className="docpro-container w-full">
                                                {selectedTemplateId && selectedTemplateId !== "clipbuilder_pro" ? (
                                                    <div className="absolute -top-5 left-0 right-0 flex justify-center z-10 pointer-events-none">
                                                        <span
                                                            className="inline-flex items-center px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider shadow-sm"
                                                            style={{ backgroundColor: "#1F4E79", color: "#fff" }}
                                                        >
                                                            {selectedTemplateId === "wolbito_it"
                                                                ? "📋 IT"
                                                                : selectedTemplateId === "wolbito_pop"
                                                                  ? "📑 POP"
                                                                  : selectedTemplateId}
                                                        </span>
                                                    </div>
                                                ) : null}

                                                <button
                                                    className="docpro-btn"
                                                    type="button"
                                                    onClick={() => {
                                                        if (enhanceLoading || steps.length === 0) return;
                                                        setDocProDropdownOpen((v) => !v);
                                                    }}
                                                    disabled={enhanceLoading || steps.length === 0}
                                                    aria-haspopup="menu"
                                                    aria-expanded={docProDropdownOpen}
                                                    aria-label="Doc Pro — abrir opções de formato"
                                                    title={`Doc Pro: gerar documento e escolher formato (MD, DOCX, HTML, PDF) — Template: ${selectedTemplateId === "wolbito_it" ? "Wolbito IT" : selectedTemplateId === "wolbito_pop" ? "Wolbito POP" : "ClipBuilder Pro"}`}
                                                >
                                                    <div className="docpro-icon-wrapper" aria-hidden="true">
                                                        {enhanceLoading ? (
                                                            <Loader2 size={16} className="animate-spin" />
                                                        ) : (
                                                            <Wand2 size={16} />
                                                        )}
                                                    </div>
                                                    <div className="docpro-text">
                                                        <span className="docpro-label">Doc Pro</span>
                                                        <span className="docpro-hint">IA • Exportar</span>
                                                    </div>
                                                    <ChevronDown
                                                        size={14} 
                                                        className={`docpro-chevron ${docProDropdownOpen ? "open" : ""}`}
                                                    />
                                                </button>

                                                {docProDropdownOpen ? (
                                                    <div className="docpro-menu" role="menu">
                                                        <div className="docpro-menu-header">Gerar com IA e exportar como:</div>
                                                        {[
                                                            {
                                                                id: "md",
                                                                icon: <FileText size={16} />,
                                                                label: "Markdown",
                                                                hint: "Preview editável",
                                                                permission: "can_export_md"
                                                            },
                                                            {
                                                                id: "docx",
                                                                icon: <File size={16} />,
                                                                label: "Word",
                                                                hint: ".docx profissional",
                                                                permission: "can_export_docx"
                                                            },
                                                            {
                                                                id: "html",
                                                                icon: <Code size={16} />,
                                                                label: "HTML",
                                                                hint: "Página web",
                                                                permission: "can_export_html"
                                                            },
                                                            {
                                                                id: "pdf",
                                                                icon: <FileDown size={16} />,
                                                                label: "PDF",
                                                                hint: "Via LibreOffice",
                                                                permission: "can_export_pdf"
                                                            },
                                                        ].filter(opt => {
                                                            if (currentUser?.role === "admin") return true;
                                                            const val = currentUser?.permissions?.[opt.permission];
                                                            if (opt.id === "docx") return val !== false;
                                                            return val === true;
                                                        }).map((opt) => (
                                                            <button
                                                                key={opt.id}
                                                                type="button"
                                                                role="menuitem"
                                                                className="docpro-option"
                                                                onClick={() => {
                                                                    setDocProDropdownOpen(false);
                                                                    enhanceAndExport(opt.id);
                                                                }}
                                                            >
                                                                <span className="docpro-opt-icon">{opt.icon}</span>
                                                                <span className="docpro-opt-label">{opt.label}</span>
                                                                <span className="docpro-opt-hint">{opt.hint}</span>
                                                            </button>
                                                        ))}
                                                    </div>
                                                ) : null}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Suggestion banner from AI tools */}
                                {suggestion && (
                                    <div
                                        className="rounded-lg border p-3 text-sm flex items-start gap-2"
                                        style={{
                                            borderColor: "var(--accent)",
                                            backgroundColor:
                                                "var(--accent-light)",
                                            color: "var(--text)",
                                        }}
                                    >
                                        <span className="text-base flex-shrink-0">
                                            💡
                                        </span>
                                        <span className="flex-1">
                                            {suggestion}
                                        </span>
                                        <button
                                            onClick={() => setSuggestion(null)}
                                            className="text-xs flex-shrink-0 p-1 rounded hover:opacity-70"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                            aria-label="Fechar sugestão"
                                        >
                                            <svg
                                                className="h-3.5 w-3.5"
                                                fill="none"
                                                stroke="currentColor"
                                                viewBox="0 0 24 24"
                                            >
                                                <path
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                    strokeWidth={2}
                                                    d="M6 18L18 6M6 6l12 12"
                                                />
                                            </svg>
                                        </button>
                                    </div>
                                )}

                                {error || aiError ? (
                                    <div
                                        className="rounded-lg border p-4 text-sm relative"
                                        style={{
                                            borderColor: error
                                                ? "var(--danger)"
                                                : "var(--warning)",
                                            backgroundColor: error
                                                ? "var(--danger-bg)"
                                                : "var(--warning-bg)",
                                            color: error
                                                ? "var(--danger)"
                                                : "var(--warning)",
                                        }}
                                    >
                                        {/* Dismiss button */}
                                        <button
                                            onClick={() => {
                                                setError("");
                                                setAiError("");
                                                if (aiStatus === "error")
                                                    setAiStatus("idle");
                                            }}
                                            className="absolute top-2 right-2 p-1 rounded-md opacity-60 hover:opacity-100 transition-opacity"
                                            style={{
                                                color: "inherit",
                                            }}
                                            title="Dispensar"
                                        >
                                            <svg
                                                className="h-4 w-4"
                                                fill="none"
                                                viewBox="0 0 24 24"
                                                stroke="currentColor"
                                                strokeWidth="2"
                                            >
                                                <path
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                    d="M6 18L18 6M6 6l12 12"
                                                />
                                            </svg>
                                        </button>
                                        {error ? (
                                            <div className="flex items-start gap-2 pr-6">
                                                <svg
                                                    className="h-4 w-4 mt-0.5 flex-shrink-0"
                                                    fill="currentColor"
                                                    viewBox="0 0 20 20"
                                                >
                                                    <path
                                                        fillRule="evenodd"
                                                        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                                                        clipRule="evenodd"
                                                    />
                                                </svg>
                                                <span>{error}</span>
                                            </div>
                                        ) : null}
                                        {aiError ? (
                                            <div className="flex items-start gap-2 pr-6">
                                                <svg
                                                    className="h-4 w-4 mt-0.5 flex-shrink-0"
                                                    fill="currentColor"
                                                    viewBox="0 0 20 20"
                                                >
                                                    <path
                                                        fillRule="evenodd"
                                                        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                                                        clipRule="evenodd"
                                                    />
                                                </svg>
                                                <span>{aiError}</span>
                                            </div>
                                        ) : null}
                                    </div>
                                ) : null}
                            </div>
                        </div>
                    </div>
                </section>
            </MouseTilt>

                <MouseTilt 
                    className="animate-fade-up"
                    style={{ animationDelay: '0.1s' }}
                >
                    <Sidebar
                        steps={steps}
                        selectedStepId={selectedStepId}
                        setSelectedStepId={handleSelectStep}
                        reorderSteps={reorderSteps}
                        updateDescription={updateDescription}
                        generateWithAI={generateWithAI}
                        removeStep={removeStep}
                        aiStepBusyId={aiStepBusyId}
                        videoId={videoId}
                        aiStatus={aiStatus}
                        onEditImage={handleEditImage}
                        documentTitle={documentTitle}
                        setDocumentTitle={setDocumentTitle}
                        contextTags={contextTags}
                        className="h-full"
                        geminiModel={geminiModel}
                        setGeminiModel={setGeminiModel}
                        flaggedModels={flaggedModels}
                        setFlaggedModels={setFlaggedModels}
                        currentUser={currentUser}
                    />

                </MouseTilt>
                <ImageEditorModal
                    open={imageEditorOpen}
                    step={editingStep}
                    onClose={() => {
                        setImageEditorOpen(false);
                        setEditingStepId(null);
                    }}
                    onSave={(blob) => {
                        if (!editingStepId) return;
                        updateStepImage(editingStepId, blob);
                    }}
                />
                <SettingsModal
                    open={settingsOpen}
                    onClose={() => setSettingsOpen(false)}
                    aiContext={aiContext}
                    setAiContext={setAiContext}
                    savedPrompt={savedPrompt}
                    setSavedPrompt={setSavedPrompt}

                    imageNamePrefix={imageNamePrefix}
                    setImageNamePrefix={setImageNamePrefix}
                    onExportMarkdown={exportMarkdownDoc}
                    onImportMarkdown={() => setImportModalOpen(true)}
                    onEnhanceDocument={() => enhanceAndExport("md")}
                    stepsCount={steps.length}
                    enhanceLoading={enhanceLoading}
                    selectedTemplateId={selectedTemplateId}
                    setSelectedTemplateId={setSelectedTemplateId}
                    templateMetadata={templateMetadata}
                    setTemplateMetadata={setTemplateMetadata}
                    currentUser={currentUser}
                />
                <ImportMarkdownModal
                    open={importModalOpen}
                    onClose={() => setImportModalOpen(false)}
                    onImport={handleImportMarkdown}
                />
                <EnhancedDocPreview
                    open={enhancePreviewOpen}
                    onClose={() => setEnhancePreviewOpen(false)}
                    markdown={enhancedMarkdown}
                    onMarkdownChange={setEnhancedMarkdown}
                    title={documentTitle}
                    steps={steps}
                    selectedTemplateId={selectedTemplateId}
                    templateMetadata={templateMetadata}
                />
                <GifPreviewModal
                    isOpen={gifPreviewOpen}
                    onClose={closeGifPreview}
                    gifUrl={gifUrl}
                    gifBlob={gifBlob}
                    onAddToDoc={addGifAsStep}
                    onDownload={downloadGif}
                    isGenerating={isGeneratingGif}
                    progress={gifProgress}
                    gifDescribeLoading={gifDescribeLoading}
                    onGenerateDoc={handleGenerateDocumentation}
                    isGeneratingDoc={isGeneratingDoc}
                    generationStage={generationStage}
                />
            </main>
        </div>
    );
}
