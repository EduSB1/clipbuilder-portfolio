import React, { useState, useEffect, useMemo } from "react";
import { X, Download, Copy, Check, FileText, AlertCircle } from "lucide-react";
import { marked } from "marked";
import {
    downloadMarkdownAsDocx,
    buildImageMapFromSteps,
} from "../../utils/api";
import { useAppAuth } from "../../utils/AuthContext.jsx";

// Simple Error Boundary Component to prevent white screens
class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error(
            "DocPreview ErrorBoundary caught error:",
            error,
            errorInfo,
        );
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="flex flex-col items-center justify-center p-8 text-center h-full">
                    <AlertCircle className="h-12 w-12 text-red-500 mb-4" />
                    <h3 className="text-lg font-semibold text-red-600 mb-2">
                        Algo deu errado na visualização
                    </h3>
                    <p className="text-sm text-gray-600 mb-4 max-w-md">
                        Não foi possível renderizar o documento. Tente
                        visualizar no modo Markdown ou exportar.
                    </p>
                    <div className="p-2 bg-gray-100 rounded text-xs text-left w-full overflow-auto max-h-32 mb-4">
                        {this.state.error?.toString()}
                    </div>
                    <button
                        onClick={() => this.setState({ hasError: false })}
                        className="cb-btn cb-btn-primary"
                    >
                        Tentar novamente
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

export default function EnhancedDocPreview({
    open,
    onClose,
    markdown,
    onMarkdownChange,
    title,
    steps = [],
    selectedTemplateId = null,
    templateMetadata = null,
}) {
    const [copied, setCopied] = useState(false);
    const { user } = useAppAuth();
    const canExportMd = user?.role === "admin" || user?.permissions?.can_export_md === true;
    const canExportDocx = user?.role === "admin" || user?.permissions?.can_export_docx !== false;

    const [viewMode, setViewMode] = useState(canExportMd ? "markdown" : "word"); // 'markdown' | 'word'
    const [docxLoading, setDocxLoading] = useState(false);
    const [docxError, setDocxError] = useState("");
    const [localMarkdown, setLocalMarkdown] = useState(markdown || "");

    // Reset local state when modal opens
    useEffect(() => {
        if (open) {
            setLocalMarkdown(markdown || "");
        }
    }, [markdown, open]);

    if (!open) return null;

    const currentMarkdown =
        typeof onMarkdownChange === "function" ? localMarkdown : markdown || "";
    const isEditable = typeof onMarkdownChange === "function";

    function handleMarkdownChange(value) {
        setLocalMarkdown(value);
        if (typeof onMarkdownChange === "function") onMarkdownChange(value);
    }

    async function copyToClipboard() {
        try {
            await navigator.clipboard.writeText(currentMarkdown || "");
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (e) {
            console.error("Failed to copy:", e);
        }
    }

    function downloadMarkdownFile() {
        const safeTitle = (title || "documento")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/[^a-zA-Z0-9 _-]/g, "_")
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 50);
        const blob = new Blob([currentMarkdown || ""], {
            type: "text/markdown",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${safeTitle}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    async function handleDownloadDocx() {
        if (!currentMarkdown?.trim()) return;
        setDocxError("");
        setDocxLoading(true);
        try {
            const safeTitle = (title || "documento")
                .normalize("NFD")
                .replace(/[\u0300-\u036f]/g, "")
                .replace(/[^a-zA-Z0-9 _-]/g, "_")
                .replace(/\s+/g, " ")
                .trim()
                .slice(0, 50);
            const imageMap = await buildImageMapFromSteps(steps);
            await downloadMarkdownAsDocx(
                currentMarkdown,
                `${safeTitle}.docx`,
                true,
                imageMap,
                selectedTemplateId,
                templateMetadata,
            );
        } catch (e) {
            console.error("Erro ao baixar Word:", e);
            setDocxError(
                e?.parsedDetail ||
                    e?.message ||
                    "Falha ao gerar o arquivo DOCX.",
            );
        } finally {
            setDocxLoading(false);
        }
    }

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ backgroundColor: "var(--modal-overlay)" }}
        >
            <div className="cb-modal w-full max-w-4xl max-h-[90vh] flex flex-col">
                <div className="cb-modal-header flex items-center justify-between">
                    <h2 className="cb-modal-title text-xl font-semibold">
                        Documento Profissional
                    </h2>
                    <button
                        onClick={onClose}
                        className="cb-btn p-2"
                        aria-label="Fechar"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>

                <div className="cb-modal-body flex-1 overflow-hidden flex flex-col">
                    <ErrorBoundary>
                        <div className="flex flex-wrap items-center gap-2 mb-3">
                            {canExportMd && (
                                <div className="flex flex-wrap items-center gap-2 mb-3">
                                    <span
                                        className="text-sm font-medium"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        Ver como:
                                    </span>
                                    <div
                                        className="flex rounded-lg border overflow-hidden"
                                        style={{ borderColor: "var(--card-border)" }}
                                    >
                                        <button
                                            type="button"
                                            onClick={() => setViewMode("markdown")}
                                            className={`px-3 py-1.5 text-sm transition-all duration-200 ${viewMode === "markdown" ? "cb-btn-primary" : "cb-btn"}`}
                                        >
                                            Markdown
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setViewMode("word")}
                                            className={`px-3 py-1.5 text-sm transition-all duration-200 flex items-center gap-1.5 ${viewMode === "word" ? "cb-btn-primary" : "cb-btn"}`}
                                        >
                                            <FileText className="h-3.5 w-3.5" />
                                            Layout Word
                                        </button>
                                    </div>
                                </div>
                            )}
                            <div className="flex-1" />
                            {canExportMd && (
                                <button
                                    onClick={copyToClipboard}
                                    className="cb-btn h-9 text-sm"
                                >
                                    {copied ? (
                                        <Check className="h-4 w-4 text-emerald-500" />
                                    ) : (
                                        <Copy className="h-4 w-4" />
                                    )}
                                    {copied ? "Copiado!" : "Copiar"}
                                </button>
                            )}
                            {canExportMd && (
                                <button
                                    onClick={downloadMarkdownFile}
                                    className="cb-btn h-9 text-sm"
                                >
                                    <Download className="h-4 w-4" />
                                    Baixar Markdown
                                </button>
                            )}
                            {canExportDocx && (
                                <button
                                    onClick={handleDownloadDocx}
                                    disabled={
                                        !currentMarkdown?.trim() ||
                                        docxLoading
                                    }
                                    className="cb-btn cb-btn-primary h-9 text-sm"
                                >
                                    <Download className="h-4 w-4" />
                                    {docxLoading
                                        ? "A gerar…"
                                        : "Baixar Word (.docx)"}
                                </button>
                            )}
                        </div>
                        {docxError && (
                            <p
                                className="text-sm mt-2 px-1"
                                style={{ color: "var(--error-text, #dc2626)" }}
                                role="alert"
                            >
                                {docxError}
                            </p>
                        )}

                        <div
                            className="flex-1 overflow-auto rounded-lg border min-h-[200px]"
                            style={{
                                backgroundColor: "var(--card-bg)",
                                borderColor: "var(--card-border)",
                            }}
                        >
                            {viewMode === "markdown" ? (
                                <MarkdownEditor
                                    value={currentMarkdown}
                                    onChange={handleMarkdownChange}
                                    isEditable={isEditable}
                                />
                            ) : (
                                <WordPreview
                                    markdown={currentMarkdown}
                                    steps={steps}
                                />
                            )}
                        </div>
                    </ErrorBoundary>
                </div>

                <div className="cb-modal-footer">
                    <button onClick={onClose} className="cb-btn">
                        Fechar
                    </button>
                </div>
            </div>
        </div>
    );
}

// Sub-components to isolate errors
function MarkdownEditor({ value, onChange, isEditable }) {
    if (isEditable) {
        return (
            <textarea
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder="Nenhum conteúdo gerado."
                className="w-full h-full min-h-[280px] p-4 font-mono text-sm whitespace-pre-wrap resize-y rounded-lg border-0 focus:ring-2 focus:ring-offset-0 focus:outline-none"
                style={{
                    backgroundColor: "var(--card-bg)",
                    color: "var(--text)",
                }}
                spellCheck="false"
            />
        );
    }
    return (
        <div
            className="p-4 font-mono text-sm whitespace-pre-wrap"
            style={{ color: "var(--text)" }}
        >
            {value || "Nenhum conteúdo gerado."}
        </div>
    );
}

function WordPreview({ markdown, steps }) {
    const hasContent = Boolean(markdown?.trim());

    const wordHtml = useMemo(() => {
        if (!hasContent) return "";
        try {
            // Basic sanitation check
            if (typeof markdown !== "string") return "";

            const renderer = new marked.Renderer();
            renderer.image = (href, title, text) => {
                try {
                    let src = href || "";
                    // Try to resolve step image from blob
                    const match = src.match(/(\d+)/);
                    if (match && Array.isArray(steps)) {
                        const idx = parseInt(match[1], 10) - 1;
                        const step = steps[idx];
                        if (step && step.has_image && step.url) {
                            src = step.url;
                        }
                    }
                    return `<img src="${src}" alt="${text || ""}" title="${title || ""}" style="max-width:100%; height:auto;" />`;
                } catch {
                    return "";
                }
            };

            // marked v12+ safety
            return marked.parse(markdown, { renderer, async: false });
        } catch (e) {
            console.error(e);
            throw new Error("Erro ao processar Markdown: " + e.message);
        }
    }, [hasContent, markdown, steps]);

    return (
        <div
            className="enhanced-doc-word-layout p-6 overflow-auto"
            style={{
                backgroundColor: "var(--card-bg)",
                color: "var(--text)",
                minHeight: "280px",
            }}
        >
            {hasContent ? (
                <div
                    className="max-w-[21cm] mx-auto font-serif text-[15px] leading-relaxed"
                    dangerouslySetInnerHTML={{ __html: wordHtml }}
                />
            ) : (
                <p style={{ color: "var(--muted-text)" }}>
                    Nenhum conteúdo gerado.
                </p>
            )}
        </div>
    );
}
