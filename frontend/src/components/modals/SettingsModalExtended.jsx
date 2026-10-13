import { useState, useEffect, useMemo } from "react";
import { fetchDocumentTemplates } from "../../utils/api";

export default function SettingsModalExtended({
    open,
    onClose,
    aiContext,
    setAiContext,
    savedPrompt,
    setSavedPrompt,
    includeTimestamp,
    setIncludeTimestamp,

    imageNamePrefix,
    setImageNamePrefix,
    onExportMarkdown,
    onImportMarkdown,
    onEnhanceDocument,
    stepsCount,
    enhanceLoading,
    selectedTemplateId,
    setSelectedTemplateId,
    templateMetadata,
    setTemplateMetadata,
    currentUser,
}) {
    const [localPrompt, setLocalPrompt] = useState(aiContext || "");

    const [examplePreset, setExamplePreset] = useState("none");
    const [saved, setSaved] = useState(false);

    // Template state
    const [templates, setTemplates] = useState([]);
    const [templatesLoading, setTemplatesLoading] = useState(false);
    const [localTemplateId, setLocalTemplateId] = useState(
        selectedTemplateId || "clipbuilder_pro",
    );
    const [localTemplateMeta, setLocalTemplateMeta] = useState(
        templateMetadata || {},
    );
    const [templateSectionExpanded, setTemplateSectionExpanded] =
        useState(false);

    // Permissions are now handled via currentUser.permissions

    useEffect(() => {
        setLocalPrompt(aiContext || "");
    }, [aiContext]);

    useEffect(() => {
        setLocalTemplateId(selectedTemplateId || "clipbuilder_pro");
    }, [selectedTemplateId]);

    useEffect(() => {
        setLocalTemplateMeta(templateMetadata || {});
    }, [templateMetadata]);

    useEffect(() => {
        if (open) {
            setSaved(false);
            // Fetch templates when modal opens
            setTemplatesLoading(true);
            fetchDocumentTemplates()
                .then((data) => {
                    setTemplates(data || []);
                })
                .finally(() => setTemplatesLoading(false));

            // Permissions are now loaded from currentUser.permissions via AuthContext
        }
    }, [open]);


    const hasUnsavedChanges =
        (localPrompt || "") !== (aiContext || "") ||
        localTemplateId !== (selectedTemplateId || "clipbuilder_pro");

    const selectedTemplate = templates.find((t) => t.id === localTemplateId);
    const isCorporateTemplate =
        selectedTemplate?.category === "corporate" || false;

    const filteredTemplates = useMemo(() => {
        // Se o usuário for admin, ele vê tudo
        if (currentUser?.role === "admin") return templates;

        const perms = currentUser?.permissions || {};
        const enabled = perms.template_permissions_enabled;

        if (!enabled) return templates;

        let allowedIds = [];
        try {
            const raw = perms.allowed_templates;
            if (!raw) return [];
            allowedIds = typeof raw === "string" ? JSON.parse(raw) : raw;
        } catch (e) {
            console.error("Erro ao parsear allowed_templates:", e);
            return [];
        }

        if (!Array.isArray(allowedIds)) return [];

        return templates.filter((t) => allowedIds.includes(t.id));
    }, [templates, currentUser]);

    if (!open) return null;

    function handleMetaChange(key, value) {
        setLocalTemplateMeta((prev) => ({ ...prev, [key]: value }));
    }

    function handleSave() {
        try {
            localStorage.setItem("CLIPBUILDER_SAVED_PROMPT", localPrompt);
        } catch {}
        setSavedPrompt(localPrompt);
        setAiContext(localPrompt);

        // Save template selection
        try {
            localStorage.setItem("CLIPBUILDER_TEMPLATE_ID", localTemplateId);
        } catch {}
        if (typeof setSelectedTemplateId === "function")
            setSelectedTemplateId(localTemplateId);

        try {
            localStorage.setItem(
                "CLIPBUILDER_TEMPLATE_METADATA",
                JSON.stringify(localTemplateMeta),
            );
        } catch {}
        if (typeof setTemplateMetadata === "function")
            setTemplateMetadata({ ...localTemplateMeta });

        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    }

    function saveAndClose() {
        handleSave();
        onClose();
    }

    // Metadata field labels (PT-BR)
    const metaFieldLabels = {
        document_code: "Código do documento",
        revision: "Revisão",
        expiration_period: "Período de expiração",
        elaboration_date: "Data de elaboração",
        responsible_elaboration: "Responsável pela elaboração",
        responsible_consensus: "Responsável(eis) pelo consenso",
        responsible_approval: "Responsável(eis) pela aprovação",
    };

    const metaFieldPlaceholders = {
        document_code: "Ex: IT-TI-INF-0002",
        revision: "Ex: 00",
        expiration_period: "Ex: 1 ano",
        elaboration_date: "Ex: 14/08/2025",
        responsible_elaboration: "Nome do responsável",
        responsible_consensus: "Nome(s) do(s) responsável(eis)",
        responsible_approval: "Nome do aprovador",
    };

    // Get all metadata fields for corporate templates
    const allMetaFields = [
        "document_code",
        "revision",
        "expiration_period",
        "elaboration_date",
        "responsible_elaboration",
        "responsible_consensus",
        "responsible_approval",
    ];

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ backgroundColor: "var(--modal-overlay)" }}
        >
            <div className="cb-modal w-full max-w-2xl max-h-[90vh] overflow-y-auto">
                <div className="cb-modal-header">
                    <div className="flex items-center justify-between">
                        <div>
                            <h2
                                className="cb-modal-title text-xl font-semibold"
                                style={{ color: "var(--text)" }}
                            >
                                Ajuste de templates
                            </h2>
                            <p
                                className="text-sm mt-1"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Como a IA deve escrever e formatar a exportação.
                            </p>
                        </div>
                        <button
                            onClick={onClose}
                            className="cb-btn p-2"
                            aria-label="Fechar"
                        >
                            <svg
                                className="h-4 w-4"
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
                </div>
                <div className="cb-modal-body">


                    {/* Seção: Template de Documento */}
                    <div className="mb-6">
                        <button
                            type="button"
                            onClick={() =>
                                setTemplateSectionExpanded((v) => !v)
                            }
                            className="w-full flex items-center justify-between text-left"
                        >
                            <h3
                                className="text-sm font-semibold"
                                style={{ color: "var(--text)" }}
                            >
                                📄 Template de Documento
                            </h3>
                            <svg
                                className={`h-4 w-4 transition-transform duration-200 ${templateSectionExpanded ? "rotate-180" : ""}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                                style={{ color: "var(--muted-text)" }}
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M19 9l-7 7-7-7"
                                />
                            </svg>
                        </button>
                        <p
                            className="text-xs mt-1 mb-3"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Escolha o modelo de documento para exportações Doc
                            Pro (DOCX).
                        </p>

                        {templateSectionExpanded && (
                            <div className="space-y-4 mt-3">
                                {/* Template cards */}
                                {templatesLoading ? (
                                    <div
                                        className="flex items-center justify-center py-6 text-sm"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        <svg
                                            className="animate-spin h-4 w-4 mr-2"
                                            fill="none"
                                            viewBox="0 0 24 24"
                                        >
                                            <circle
                                                className="opacity-25"
                                                cx="12"
                                                cy="12"
                                                r="10"
                                                stroke="currentColor"
                                                strokeWidth="4"
                                            />
                                            <path
                                                className="opacity-75"
                                                fill="currentColor"
                                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                                            />
                                        </svg>
                                        Carregando templates...
                                    </div>
                                ) : templates.length === 0 ? (
                                    <div
                                        className="text-sm text-center py-4"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        Nenhum template disponível. Verifique se
                                        o backend está rodando.
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 gap-3">
                                        {(filteredTemplates || []).map((tmpl) => {
                                            const isSelected =
                                                localTemplateId === tmpl.id;
                                            const isCorp =
                                                tmpl.category === "corporate";
                                            return (
                                                <button
                                                    key={tmpl.id}
                                                    type="button"
                                                    onClick={() =>
                                                        setLocalTemplateId(
                                                            tmpl.id,
                                                        )
                                                    }
                                                    className="relative w-full text-left rounded-lg border p-4 transition-all duration-200"
                                                    style={{
                                                        borderColor: isSelected
                                                            ? "var(--accent)"
                                                            : "var(--card-border)",
                                                        backgroundColor:
                                                            isSelected
                                                                ? "var(--accent-light, rgba(59,130,246,0.08))"
                                                                : "var(--card-bg)",
                                                        boxShadow: isSelected
                                                            ? "0 0 0 2px var(--accent)"
                                                            : "none",
                                                    }}
                                                >
                                                    <div className="flex items-start gap-3">
                                                        {/* Icon / Logo indicator */}
                                                        <div
                                                            className="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-lg"
                                                            style={{
                                                                backgroundColor:
                                                                    isSelected
                                                                        ? "var(--accent)"
                                                                        : "var(--card-border)",
                                                                color: isSelected
                                                                    ? "#fff"
                                                                    : "var(--text)",
                                                            }}
                                                        >
                                                            {tmpl.icon || "📄"}
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2">
                                                                <span
                                                                    className="text-sm font-semibold"
                                                                    style={{
                                                                        color: "var(--text)",
                                                                    }}
                                                                >
                                                                    {tmpl.name}
                                                                </span>
                                                                {isCorp && (
                                                                    <span
                                                                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
                                                                        style={{
                                                                            backgroundColor:
                                                                                "#1F4E79",
                                                                            color: "#fff",
                                                                        }}
                                                                    >
                                                                        Corporativo
                                                                    </span>
                                                                )}
                                                                {tmpl.has_logo && (
                                                                    <span
                                                                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium"
                                                                        style={{
                                                                            backgroundColor:
                                                                                "var(--card-border)",
                                                                            color: "var(--text)",
                                                                        }}
                                                                    >
                                                                        🏢 Com
                                                                        Logo
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <p
                                                                className="text-xs mt-1 leading-relaxed"
                                                                style={{
                                                                    color: "var(--muted-text)",
                                                                }}
                                                            >
                                                                {
                                                                    tmpl.description
                                                                }
                                                            </p>
                                                            {/* Section preview chips */}
                                                            {tmpl.sections &&
                                                                tmpl.sections
                                                                    .length >
                                                                    0 && (
                                                                    <div className="flex flex-wrap gap-1 mt-2">
                                                                        {tmpl.sections
                                                                            .slice(
                                                                                0,
                                                                                6,
                                                                            )
                                                                            .map(
                                                                                (
                                                                                    sec,
                                                                                ) => (
                                                                                    <span
                                                                                        key={
                                                                                            sec
                                                                                        }
                                                                                        className="inline-block px-1.5 py-0.5 rounded text-[10px]"
                                                                                        style={{
                                                                                            backgroundColor:
                                                                                                "var(--card-border)",
                                                                                            color: "var(--muted-text)",
                                                                                        }}
                                                                                    >
                                                                                        {sec
                                                                                            .replace(
                                                                                                /_/g,
                                                                                                " ",
                                                                                            )
                                                                                            .replace(
                                                                                                /\b\w/g,
                                                                                                (
                                                                                                    c,
                                                                                                ) =>
                                                                                                    c.toUpperCase(),
                                                                                            )}
                                                                                    </span>
                                                                                ),
                                                                            )}
                                                                        {tmpl
                                                                            .sections
                                                                            .length >
                                                                            6 && (
                                                                            <span
                                                                                className="inline-block px-1.5 py-0.5 rounded text-[10px]"
                                                                                style={{
                                                                                    backgroundColor:
                                                                                        "var(--card-border)",
                                                                                    color: "var(--muted-text)",
                                                                                }}
                                                                            >
                                                                                +
                                                                                {tmpl
                                                                                    .sections
                                                                                    .length -
                                                                                    6}
                                                                            </span>
                                                                        )}
                                                                    </div>
                                                                )}
                                                        </div>
                                                        {/* Selection indicator */}
                                                        <div className="flex-shrink-0 mt-1">
                                                            {isSelected ? (
                                                                <svg
                                                                    className="h-5 w-5"
                                                                    fill="none"
                                                                    stroke="currentColor"
                                                                    viewBox="0 0 24 24"
                                                                    style={{
                                                                        color: "var(--accent)",
                                                                    }}
                                                                >
                                                                    <path
                                                                        strokeLinecap="round"
                                                                        strokeLinejoin="round"
                                                                        strokeWidth={
                                                                            2.5
                                                                        }
                                                                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                                                                    />
                                                                </svg>
                                                            ) : (
                                                                <div
                                                                    className="h-5 w-5 rounded-full border-2"
                                                                    style={{
                                                                        borderColor:
                                                                            "var(--card-border)",
                                                                    }}
                                                                />
                                                            )}
                                                        </div>
                                                    </div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}

                                {/* Corporate metadata fields (shown only for corporate templates) */}
                                {isCorporateTemplate && (
                                    <div
                                        className="mt-4 rounded-lg border p-4 space-y-3"
                                        style={{
                                            borderColor: "var(--card-border)",
                                            backgroundColor: "var(--card-bg)",
                                        }}
                                    >
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="text-base">
                                                🏢
                                            </span>
                                            <h4
                                                className="text-sm font-semibold"
                                                style={{ color: "var(--text)" }}
                                            >
                                                Dados do Documento Corporativo
                                            </h4>
                                        </div>
                                        <p
                                            className="text-xs mb-3"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Preencha os metadados que aparecerão
                                            no cabeçalho e rodapé do documento.
                                            Campos vazios usarão valores padrão.
                                        </p>

                                        {/* Header fields (2-col grid) */}
                                        <div className="grid grid-cols-2 gap-3">
                                            {[
                                                "document_code",
                                                "revision",
                                                "expiration_period",
                                                "elaboration_date",
                                            ].map((field) => (
                                                <div key={field}>
                                                    <label
                                                        className="block text-xs font-medium mb-1"
                                                        style={{
                                                            color: "var(--text)",
                                                        }}
                                                    >
                                                        {metaFieldLabels[field]}
                                                    </label>
                                                    <input
                                                        type="text"
                                                        value={
                                                            localTemplateMeta[
                                                                field
                                                            ] || ""
                                                        }
                                                        onChange={(e) =>
                                                            handleMetaChange(
                                                                field,
                                                                e.target.value,
                                                            )
                                                        }
                                                        placeholder={
                                                            metaFieldPlaceholders[
                                                                field
                                                            ]
                                                        }
                                                        className="cb-input text-sm"
                                                        style={{
                                                            fontSize: "0.8rem",
                                                        }}
                                                    />
                                                </div>
                                            ))}
                                        </div>

                                        <hr
                                            className="my-3"
                                            style={{
                                                borderColor:
                                                    "var(--card-border)",
                                            }}
                                        />

                                        {/* Footer/responsibility fields */}
                                        <div className="space-y-3">
                                            <div
                                                className="text-xs font-medium"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                Rodapé – Responsáveis
                                            </div>
                                            {[
                                                "responsible_elaboration",
                                                "responsible_consensus",
                                                "responsible_approval",
                                            ].map((field) => (
                                                <div key={field}>
                                                    <label
                                                        className="block text-xs font-medium mb-1"
                                                        style={{
                                                            color: "var(--text)",
                                                        }}
                                                    >
                                                        {metaFieldLabels[field]}
                                                    </label>
                                                    <input
                                                        type="text"
                                                        value={
                                                            localTemplateMeta[
                                                                field
                                                            ] || ""
                                                        }
                                                        onChange={(e) =>
                                                            handleMetaChange(
                                                                field,
                                                                e.target.value,
                                                            )
                                                        }
                                                        placeholder={
                                                            metaFieldPlaceholders[
                                                                field
                                                            ]
                                                        }
                                                        className="cb-input text-sm"
                                                        style={{
                                                            fontSize: "0.8rem",
                                                        }}
                                                    />
                                                </div>
                                            ))}
                                        </div>

                                        {/* Template preview hint */}
                                        <div
                                            className="mt-3 rounded-md p-3 text-xs leading-relaxed"
                                            style={{
                                                backgroundColor:
                                                    "var(--accent-light, rgba(59,130,246,0.06))",
                                                color: "var(--muted-text)",
                                                border: "1px dashed var(--card-border)",
                                            }}
                                        >
                                            <strong
                                                style={{ color: "var(--text)" }}
                                            >
                                                📋 Prévia da estrutura:
                                            </strong>
                                            <div className="mt-2 font-mono text-[10px] leading-5">
                                                <div>
                                                    ┌─────────┬──────────────────────────────┐
                                                </div>
                                                <div>
                                                    │ 🏢 Logo │{" "}
                                                    {localTemplateMeta.document_code ||
                                                        "CÓDIGO"}{" "}
                                                    –{" "}
                                                    {localTemplateMeta.title ||
                                                        selectedTemplate?.short_name ||
                                                        "Título"}
                                                </div>
                                                <div>
                                                    │ &nbsp; &nbsp; &nbsp;
                                                    &nbsp;
                                                    ├──────────────────────────────┤
                                                </div>
                                                <div>
                                                    │ &nbsp; &nbsp; &nbsp;
                                                    &nbsp; │ Rev:{" "}
                                                    {localTemplateMeta.revision ||
                                                        "00"}{" "}
                                                    | Exp:{" "}
                                                    {localTemplateMeta.expiration_period ||
                                                        "1 ano"}{" "}
                                                    | Data:{" "}
                                                    {localTemplateMeta.elaboration_date ||
                                                        "dd/mm/aaaa"}
                                                </div>
                                                <div>
                                                    ├─────────┴──────────────────────────────┤
                                                </div>
                                                <div>
                                                    │ (conteúdo do documento) │
                                                </div>
                                                <div>
                                                    ├─────────────────────────────────────────┤
                                                </div>
                                                <div>
                                                    │ Elab:{" "}
                                                    {localTemplateMeta.responsible_elaboration ||
                                                        "___"}{" "}
                                                    | Cons:{" "}
                                                    {localTemplateMeta.responsible_consensus ||
                                                        "___"}{" "}
                                                    | Aprov:{" "}
                                                    {localTemplateMeta.responsible_approval ||
                                                        "___"}
                                                </div>
                                                <div>
                                                    └─────────────────────────────────────────┘
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>


                    <div className="cb-modal-footer">
                        <div className="flex items-center gap-2 ml-auto">
                            {saved && (
                                <span
                                    className="text-xs font-medium flex items-center gap-1"
                                    style={{ color: "var(--success)" }}
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
                                            d="M5 13l4 4L19 7"
                                        />
                                    </svg>
                                    Salvo!
                                </span>
                            )}
                            <button
                                onClick={saveAndClose}
                                className="cb-btn cb-btn-primary"
                                aria-label="Salvar e fechar"
                                title="Salvar e fechar"
                            >
                                Salvar e Fechar
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
