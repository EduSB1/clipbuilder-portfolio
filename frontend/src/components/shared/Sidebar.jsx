import React, { useState, useEffect } from "react";
import {
  Sparkles,
  Zap,
  Mic,
  Loader2,
  Wand2,
  ListOrdered,
  ImageOff,
  FileText,
  Check,
} from "lucide-react";
import GifStepPreview from "../video/GifStepPreview";
import { PROVIDER_CONFIG, MODELS_BY_PROVIDER } from "../../utils/toolsApi";


/**
 * Parse a context_tag JSON string into a short display label.
 * Returns a string like "🌐 Browser · GitHub" or null.
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

export default function Sidebar({
  steps = [],
  selectedStepId,
  setSelectedStepId,
  reorderSteps,
  updateDescription,
  generateWithAI,
  removeStep,
  aiStepBusyId,
  videoId,
  aiStatus,
  onEditImage,
  documentTitle = "",
  setDocumentTitle,
  contextTags = {},
  className = "",
  style = {},
  geminiModel,
  setGeminiModel,
  flaggedModels = [],
  setFlaggedModels,
  currentUser,
}) {
  const [expandedProvider, setExpandedProvider] = useState(null);
  const providerRef = React.useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (providerRef.current && !providerRef.current.contains(event.target)) {
        setExpandedProvider(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const toggleFlag = (modelValue) => {
    if (flaggedModels.includes(modelValue)) {
      setFlaggedModels(flaggedModels.filter((m) => m !== modelValue));
    } else {
      setFlaggedModels([...flaggedModels, modelValue]);
    }
  };

  const perms = currentUser?.permissions || {};
  const isAdmin = currentUser?.role === "admin";

  const providers = [
    { id: "gemini", icon: Sparkles, enabled: isAdmin || perms.can_use_gemini !== false },
    { id: "whisper", icon: Mic, enabled: isAdmin || perms.can_use_whisper !== false },
  ].filter(p => p.enabled);

  const [draggingId, setDraggingId] = useState(null);
  const [previewLoadError, setPreviewLoadError] = useState(false);

  const selected =
    steps.find((s) => s.id === selectedStepId) || steps[0] || null;

  useEffect(() => {
    setPreviewLoadError(false);
  }, [selected?.id]);
  const canGenerate =
    !!selected &&
    !!videoId &&
    aiStatus === "ready" &&
    aiStepBusyId !== selected?.id &&
    // Permitir IA para GIFs (que têm imagem) ou frames normais com timestamp
    ((!!selected?.is_gif && !!selected?.url) ||
      (typeof selected?.seconds === "number" && !!selected?.timestamp));

  const hasSelectedImage = !!selected?.url;

  return (
    <aside className={`cb-sidebar flex flex-col ${className}`} style={{ ...style, backgroundColor: "var(--glass-bg)", backdropFilter: "blur(20px)", border: "none", borderRadius: "20px" }}>
      <div className="flex items-center justify-between mb-3 pr-4">
        <div className="flex items-center gap-2">
          <ListOrdered className="h-5 w-5 flex-shrink-0" style={{ color: "var(--text-primary)" }} />
          <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            Seus passos
          </h2>
        </div>
        
        {/* AI Provider Icons */}
        <div className="flex items-center gap-1.5" ref={providerRef}>

          {providers.map((p) => {
            const config = PROVIDER_CONFIG[p.id];
            const Icon = p.icon;
            const isExpanded = expandedProvider === p.id;
            const isActive = MODELS_BY_PROVIDER[p.id]?.some(m => m.value === geminiModel);

            return (
              <div key={p.id} className="relative">
                <button
                  onClick={() => {
                    if (!isActive) {
                      const firstModel = MODELS_BY_PROVIDER[p.id]?.[0]?.value;
                      if (firstModel) setGeminiModel(firstModel);
                    }
                    setExpandedProvider(isExpanded ? null : p.id);
                  }}
                  className="w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200 relative group"
                  style={{
                    backgroundColor: (isActive || isExpanded) ? config.bg : "rgba(255,255,255,0.03)",
                    color: (isActive || isExpanded) ? config.color : "var(--muted-text)",
                    border: (isActive || isExpanded) ? `1px solid ${config.color}` : "1px solid var(--border-subtle)",
                    boxShadow: isExpanded ? `0 0 10px ${config.color}40` : "none"
                  }}
                  title={config.label}
                >

                  <Icon size={16} className={isActive ? "" : "group-hover:scale-110 transition-transform"} />
                  
                  {/* Flag indicator */}
                  {MODELS_BY_PROVIDER[p.id]?.some(m => flaggedModels.includes(m.value)) && (
                    <div 
                      className="absolute -top-1 -right-1 w-3 h-3 rounded-full flex items-center justify-center text-[8px] font-bold text-white"
                      style={{ backgroundColor: config.color }}
                    >
                      !
                    </div>
                  )}
                </button>

                {/* Dropdown Menu */}
                {isExpanded && (
                  <div 
                    className="absolute right-0 top-full mt-2 z-50 w-56 rounded-xl p-1.5 animate-in fade-in zoom-in-95 duration-150"
                    style={{ 
                      backgroundColor: "var(--bg-elevated)", 
                      border: "1px solid var(--border)",
                      boxShadow: "var(--shadow-lg)"
                    }}
                  >
                    <div className="px-2 py-1.5 mb-1 border-b border-white/5">
                      <span className="text-[10px] font-bold uppercase tracking-wider opacity-60" style={{ color: config.color }}>
                        {config.label}
                      </span>
                    </div>
                    <div className="space-y-0.5">
                      {MODELS_BY_PROVIDER[p.id]?.map((m) => {
                        const isSelected = geminiModel === m.value;
                        const isFlagged = flaggedModels.includes(m.value);
                        
                        return (
                          <div 
                            key={m.value}
                            className="flex items-center gap-2 p-2 rounded-lg hover:bg-white/5 transition-colors group cursor-pointer"
                            onClick={() => {
                              setGeminiModel(m.value);
                              setExpandedProvider(null);
                            }}
                          >
                            <div className="flex-1 min-w-0">
                              <div className="text-xs font-medium truncate" style={{ color: isSelected ? "var(--text-primary)" : "var(--text-secondary)" }}>
                                {m.label}
                              </div>
                            </div>

                            {/* Flag Toggle */}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleFlag(m.value);
                              }}
                              className="w-6 h-6 rounded flex items-center justify-center transition-all"
                              style={{
                                backgroundColor: isFlagged ? `${config.color}20` : "transparent",
                                color: isFlagged ? config.color : "var(--muted-text)",
                                border: `1px solid ${isFlagged ? config.color : "var(--border-subtle)"}`,
                              }}
                              title={isFlagged ? "Desmarcar flag" : "Marcar flag"}
                            >
                              <Check size={12} className={isFlagged ? "opacity-100" : "opacity-0 group-hover:opacity-40"} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>


      <div className="mb-4">
        <div className="doc-title-wrapper">
          <div className="title-icon-line" aria-hidden="true">
            <FileText size={14} style={{ color: "var(--text-muted)" }} />
            <div className="title-underline" />
          </div>
          <input
            className="doc-title-input"
            type="text"
            value={documentTitle}
            onChange={(e) => setDocumentTitle?.(e.target.value)}
            placeholder="Título do documento"
          />
        </div>
      </div>

      {selected ? (
        <div className="mb-6 transition-all duration-200">
          <div
            className="text-xs font-medium mb-2"
            style={{ color: "var(--muted-text)" }}
          >
            Passo em edição
          </div>
          <div
            className="mb-4 rounded-xl overflow-hidden border min-h-64"
            style={{
              borderColor: "var(--card-border)",
              backgroundColor: "var(--card-bg)",
            }}
          >
            {hasSelectedImage && !previewLoadError ? (
              selected.is_gif ? (
                <GifStepPreview
                  gifUrl={selected.url}
                  thumbnailUrl={selected.thumbnailUrl}
                  isSelected={true}
                  alt={`Passo ${steps.indexOf(selected) + 1}`}
                  className="w-full h-64"
                  imgClassName="w-full h-64 object-cover"
                  onError={() => setPreviewLoadError(true)}
                />
              ) : (
                <img
                  src={selected.url}
                  alt={`Passo ${steps.indexOf(selected) + 1}`}
                  className="w-full h-64 object-cover"
                  onLoad={() => setPreviewLoadError(false)}
                  onError={() => setPreviewLoadError(true)}
                />
              )
            ) : (
              <div
                className="w-full h-64 flex items-center justify-center"
                style={{ color: "var(--muted-text)" }}
              >
                <div className="text-center space-y-3 px-4">
                  <ImageOff
                    className="h-10 w-10 mx-auto opacity-60"
                    style={{ color: "var(--muted-text)" }}
                  />
                  <div
                    className="text-sm font-medium"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    Sem prévia deste passo
                  </div>
                  <div className="text-xs">
                    A imagem não carregou ou o passo ainda não tem imagem.
                    Capture um frame ou use o botão Editar.
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <div
                className="text-xl font-semibold mb-1"
                style={{ color: "var(--text)" }}
              >
                Passo {steps.indexOf(selected) + 1}
              </div>
              {selected.timestamp && (
                <div
                  className="text-xs font-medium"
                  style={{ color: "var(--muted-text)" }}
                >
                  {selected.timestamp}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={() => onEditImage?.(selected.id)}
                disabled={!hasSelectedImage}
                className="cb-btn text-xs"
                title={
                  hasSelectedImage
                    ? "Editar imagem deste passo"
                    : "Adicione uma imagem primeiro"
                }
              >
                Editar
              </button>
              <button
                type="button"
                onClick={() => generateWithAI(selected.id)}
                disabled={!canGenerate}
                className="cb-btn cb-btn-primary flex items-center gap-1.5 text-xs"
                title={
                  canGenerate
                    ? "Gerar descrição com IA"
                    : "Aguarde a IA estar pronta"
                }
              >
                {aiStepBusyId === selected.id ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Gerando...</span>
                  </>
                ) : (
                  <>
                    <Wand2 className="h-3.5 w-3.5" />
                    <span>IA</span>
                  </>
                )}
              </button>
            </div>
          </div>
          <textarea
            className="cb-textarea"
            rows={14}
            placeholder="Descreva o que acontece neste passo… (ou use IA para gerar)."
            value={selected.description}
            onChange={(e) => updateDescription(selected.id, e.target.value)}
          />

          <div className="mt-4 flex items-center justify-end">
            <button
              type="button"
              onClick={() => removeStep(selected.id)}
              className="cb-btn cb-btn-danger text-xs"
            >
              Remover passo
            </button>
          </div>
        </div>
      ) : (
        <div className="mb-6 text-center py-8">
          <div
            className="text-sm font-medium mb-1"
            style={{ color: "var(--text-secondary)" }}
          >
            Nenhum passo selecionado
          </div>
          <div className="text-xs" style={{ color: "var(--muted-text)" }}>
            Selecione um passo na lista para editar a descrição.
          </div>
        </div>
      )}

      <div className="flex-1 cb-sidebar-scroll -mx-1 px-1">
        <div
          className="text-xs font-medium mb-2"
          style={{ color: "var(--muted-text)" }}
        >
          Todos os passos
        </div>
        <div className="space-y-2 stagger-children">
          {steps.length === 0 ? (
            <div className="text-center py-8">
              <div
                className="text-sm font-medium mb-1"
                style={{ color: "var(--text-secondary)" }}
              >
                Nenhum passo ainda
              </div>
              <div className="text-xs" style={{ color: "var(--muted-text)" }}>
                Pause o vídeo e capture um frame (tecla S) para começar.
              </div>
            </div>
          ) : (
            steps.map((s, idx) => {
              const isGenerating = aiStepBusyId === s.id;
              const isSelected = selectedStepId === s.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  draggable
                  onClick={() => setSelectedStepId(s.id)}
                  onDragStart={(e) => {
                    setDraggingId(s.id);
                    try {
                      e.dataTransfer.effectAllowed = "move";
                      e.dataTransfer.setData("text/plain", s.id);
                    } catch {
                      // ignore
                    }
                  }}
                  onDragOver={(e) => {
                    if (!draggingId || draggingId === s.id) return;
                    e.preventDefault();
                    try {
                      e.dataTransfer.dropEffect = "move";
                    } catch {
                      // ignore
                    }
                  }}
                  onDrop={(e) => {
                    if (!draggingId || draggingId === s.id) return;
                    e.preventDefault();
                    reorderSteps?.(draggingId, s.id);
                    setDraggingId(null);
                  }}
                  onDragEnd={() => setDraggingId(null)}
                  className={`step-card-btn ${isSelected ? "is-selected" : ""} ${
                    draggingId === s.id ? "opacity-50 border-dashed" : ""
                  } ${isGenerating ? "animate-pulse" : ""} animate-fade-up`}
                  style={{ animationDelay: `${idx * 0.05}s` }}
                >
                  {s?.url ? (
                    s.is_gif ? (
                      <div className="step-thumb">
                        <GifStepPreview
                          gifUrl={s.url}
                          thumbnailUrl={s.thumbnailUrl}
                          isSelected={isSelected}
                          alt={`Passo ${idx + 1}`}
                          className="h-full w-full"
                          imgClassName="h-full w-full object-cover"
                        />
                      </div>
                    ) : (
                      <div className="step-thumb">
                        <img
                          src={s.url}
                          alt={`Passo ${idx + 1}`}
                          className="h-full w-full object-cover"
                        />
                      </div>
                    )
                  ) : (
                    <div className="step-thumb grid place-items-center text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                      Texto
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="step-number-badge">{idx + 1}</span>
                        <div className="text-sm font-semibold" style={{ color: isSelected ? "var(--accent)" : "var(--text)" }}>
                          Passo
                        </div>
                        {isGenerating && (
                          <div className="flex items-center gap-1">
                            <Sparkles
                              className="h-3 w-3 animate-pulse"
                              style={{ color: "var(--accent)" }}
                            />
                            <Loader2
                              className="h-3 w-3 animate-spin"
                              style={{ color: "var(--accent)" }}
                            />
                          </div>
                        )}
                      </div>
                      {s.timestamp && (
                        <div className="step-timestamp-chip">
                          {s.timestamp}
                        </div>
                      )}
                    </div>
                    {contextTags[s.id] && (
                      <div className="mb-0.5">
                        <span
                          className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded-full"
                          style={{
                            color: "var(--accent)",
                            backgroundColor: "var(--accent-light)",
                            border: "1px solid var(--accent)30",
                          }}
                        >
                          {formatContextTag(contextTags[s.id])}
                        </span>
                      </div>
                    )}
                    <div
                      className="text-xs leading-relaxed line-clamp-2"
                      style={{
                        color: s.description
                          ? "var(--text-secondary)"
                          : "var(--muted-text)",
                      }}
                    >
                      {s.description || "Sem descrição"}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </aside>
  );
}
