import { useState, useEffect, useCallback } from "react";
import {
    listTools,
    createTool,
    updateTool,
    deleteTool,
    toggleTool,
    getToolLogs,
    TRIGGER_LABELS,
    OUTPUT_TARGET_LABELS,
    PROVIDER_CONFIG,
    MODELS_BY_PROVIDER,
} from "../../utils/toolsApi";

// ── Badge component ──────────────────────────────────────────────────

function Badge({ label, color, bg, small }) {
    return (
        <span
            className={`inline-flex items-center rounded-full font-medium ${small ? "text-[10px] px-1.5 py-0.5" : "text-xs px-2 py-0.5"}`}
            style={{
                color,
                backgroundColor: bg,
                border: `1px solid ${color}30`,
            }}
        >
            {label}
        </span>
    );
}

// ── Toggle switch ────────────────────────────────────────────────────

function Toggle({ checked, onChange, disabled }) {
    return (
        <label className="relative inline-flex cursor-pointer items-center flex-shrink-0">
            <input
                type="checkbox"
                className="sr-only"
                checked={checked}
                onChange={(e) => onChange(e.target.checked)}
                disabled={disabled}
            />
            <div
                className="h-6 w-11 rounded-full transition-colors"
                style={{
                    backgroundColor: checked
                        ? "var(--success)"
                        : "var(--card-border)",
                    opacity: disabled ? 0.5 : 1,
                }}
            />
            <div
                className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform shadow-sm"
                style={{
                    transform: checked
                        ? "translateX(1.25rem)"
                        : "translateX(0)",
                }}
            />
        </label>
    );
}

// ── Status icon ──────────────────────────────────────────────────────

function StatusIcon({ status }) {
    if (status === "success") {
        return (
            <span title="Sucesso" style={{ color: "var(--success)" }}>
                ✅
            </span>
        );
    }
    if (status === "error") {
        return (
            <span title="Erro" style={{ color: "var(--danger)" }}>
                ❌
            </span>
        );
    }
    if (status === "cancelled") {
        return (
            <span title="Cancelado" style={{ color: "var(--muted-text)" }}>
                ⏹
            </span>
        );
    }
    return <span>—</span>;
}

// ── Tool Form Modal ──────────────────────────────────────────────────

function ToolFormModal({ open, onClose, onSave, tool, saving }) {
    const isEditing = !!tool;

    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [prompt, setPrompt] = useState("");
    const [modelProvider, setModelProvider] = useState("gemini");
    const [modelName, setModelName] = useState("models/gemini-2.5-flash");
    const [triggers, setTriggers] = useState(["on_frame_capture"]);
    const [outputTarget, setOutputTarget] = useState("description");
    const [scope, setScope] = useState("global");
    const [isActive, setIsActive] = useState(true);
    const [errors, setErrors] = useState({});

    useEffect(() => {
        if (tool) {
            setName(tool.name || "");
            setDescription(tool.description || "");
            setPrompt(tool.prompt || "");
            setModelProvider(tool.model_provider || "gemini");
            setModelName(tool.model_name || "models/gemini-2.5-flash");
            setTriggers(
                Array.isArray(tool.triggers)
                    ? tool.triggers
                    : ["on_frame_capture"],
            );
            setOutputTarget(tool.output_target || "description");
            setScope(tool.scope || "global");
            setIsActive(tool.is_active !== undefined ? tool.is_active : true);
        } else {
            setName("");
            setDescription("");
            setPrompt("");
            setModelProvider("gemini");
            setModelName("models/gemini-2.5-flash");
            setTriggers(["on_frame_capture"]);
            setOutputTarget("description");
            setScope("global");
            setIsActive(true);
        }
        setErrors({});
    }, [tool, open]);

    useEffect(() => {
        const models = MODELS_BY_PROVIDER[modelProvider] || [];
        const currentValid = models.some((m) => m.value === modelName);
        if (!currentValid && models.length > 0) {
            setModelName(models[0].value);
        }
    }, [modelProvider]);

    function handleTriggerToggle(trigger) {
        setTriggers((prev) =>
            prev.includes(trigger)
                ? prev.filter((t) => t !== trigger)
                : [...prev, trigger],
        );
    }

    function validate() {
        const e = {};
        if (!name.trim()) e.name = "Nome é obrigatório";
        if (!description.trim()) e.description = "Descrição é obrigatória";
        if (!prompt.trim()) e.prompt = "Prompt é obrigatório";
        if (triggers.length === 0) e.triggers = "Selecione ao menos um trigger";
        setErrors(e);
        return Object.keys(e).length === 0;
    }

    function handleSubmit(e) {
        e.preventDefault();
        if (!validate()) return;

        onSave({
            name: name.trim(),
            description: description.trim(),
            prompt: prompt.trim(),
            model_provider: modelProvider,
            model_name: modelName,
            triggers,
            output_target: outputTarget,
            scope,
            is_active: isActive,
        });
    }

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4"
            style={{ backgroundColor: "var(--modal-overlay)" }}
        >
            <div className="cb-modal w-full max-w-2xl max-h-[90vh] overflow-y-auto">
                <div className="cb-modal-header">
                    <div className="flex items-center justify-between">
                        <h2
                            className="cb-modal-title text-lg font-semibold"
                            style={{ color: "var(--text)" }}
                        >
                            {isEditing ? "Editar Tool" : "Nova Tool"}
                        </h2>
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

                <form
                    onSubmit={handleSubmit}
                    className="cb-modal-body space-y-4"
                >
                    {/* Name */}
                    <div>
                        <label
                            className="block text-sm font-medium mb-1"
                            style={{ color: "var(--text)" }}
                        >
                            Nome
                        </label>
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className={`cb-input w-full ${errors.name ? "border-[var(--danger)]" : ""}`}
                            placeholder="Nome da tool"
                            maxLength={100}
                        />
                        {errors.name && (
                            <p
                                className="text-xs mt-1"
                                style={{ color: "var(--danger)" }}
                            >
                                {errors.name}
                            </p>
                        )}
                    </div>

                    {/* Description */}
                    <div>
                        <label
                            className="block text-sm font-medium mb-1"
                            style={{ color: "var(--text)" }}
                        >
                            Descrição
                        </label>
                        <textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            className={`cb-textarea w-full ${errors.description ? "border-[var(--danger)]" : ""}`}
                            rows={2}
                            placeholder="O que esta tool faz..."
                        />
                        {errors.description && (
                            <p
                                className="text-xs mt-1"
                                style={{ color: "var(--danger)" }}
                            >
                                {errors.description}
                            </p>
                        )}
                    </div>

                    {/* Prompt */}
                    <div>
                        <label
                            className="block text-sm font-medium mb-1"
                            style={{ color: "var(--text)" }}
                        >
                            Prompt
                        </label>
                        <textarea
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            className={`cb-textarea w-full font-mono text-sm ${errors.prompt ? "border-[var(--danger)]" : ""}`}
                            rows={6}
                            placeholder="Instrução para a IA..."
                        />
                        <p
                            className="text-xs mt-1"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Variáveis disponíveis:{" "}
                            <code className="font-mono text-[11px]">
                                {"{previous_steps}"}
                            </code>
                            ,{" "}
                            <code className="font-mono text-[11px]">
                                {"{full_document}"}
                            </code>
                        </p>
                        {errors.prompt && (
                            <p
                                className="text-xs mt-1"
                                style={{ color: "var(--danger)" }}
                            >
                                {errors.prompt}
                            </p>
                        )}
                    </div>

                    {/* Provider + Model */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label
                                className="block text-sm font-medium mb-1"
                                style={{ color: "var(--text)" }}
                            >
                                Provider
                            </label>
                            <select
                                value={modelProvider}
                                onChange={(e) =>
                                    setModelProvider(e.target.value)
                                }
                                className="cb-select w-full"
                            >
                                <option value="gemini">Gemini</option>
                                <option value="whisper">Whisper</option>
                            </select>
                        </div>
                        <div>
                            <label
                                className="block text-sm font-medium mb-1"
                                style={{ color: "var(--text)" }}
                            >
                                Modelo
                            </label>
                            <select
                                value={modelName}
                                onChange={(e) => setModelName(e.target.value)}
                                className="cb-select w-full"
                            >
                                {(MODELS_BY_PROVIDER[modelProvider] || []).map(
                                    (m) => (
                                        <option key={m.value} value={m.value}>
                                            {m.label}
                                        </option>
                                    ),
                                )}
                            </select>
                        </div>
                    </div>

                    {/* Triggers */}
                    <div>
                        <label
                            className="block text-sm font-medium mb-2"
                            style={{ color: "var(--text)" }}
                        >
                            Triggers (quando executar)
                        </label>
                        <div className="flex flex-wrap gap-3">
                            {Object.entries(TRIGGER_LABELS).map(
                                ([key, label]) => (
                                    <label
                                        key={key}
                                        className="flex items-center gap-2 text-sm cursor-pointer"
                                        style={{ color: "var(--text)" }}
                                    >
                                        <input
                                            type="checkbox"
                                            checked={triggers.includes(key)}
                                            onChange={() =>
                                                handleTriggerToggle(key)
                                            }
                                            className="rounded"
                                        />
                                        {label}
                                    </label>
                                ),
                            )}
                        </div>
                        {errors.triggers && (
                            <p
                                className="text-xs mt-1"
                                style={{ color: "var(--danger)" }}
                            >
                                {errors.triggers}
                            </p>
                        )}
                    </div>

                    {/* Output Target */}
                    <div>
                        <label
                            className="block text-sm font-medium mb-1"
                            style={{ color: "var(--text)" }}
                        >
                            Destino do resultado
                        </label>
                        <select
                            value={outputTarget}
                            onChange={(e) => setOutputTarget(e.target.value)}
                            className="cb-select w-full"
                        >
                            {Object.entries(OUTPUT_TARGET_LABELS).map(
                                ([key, label]) => (
                                    <option key={key} value={key}>
                                        {label}
                                    </option>
                                ),
                            )}
                        </select>
                    </div>

                    {/* Scope + Active */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label
                                className="block text-sm font-medium mb-2"
                                style={{ color: "var(--text)" }}
                            >
                                Escopo
                            </label>
                            <div className="flex gap-4">
                                <label
                                    className="flex items-center gap-2 text-sm cursor-pointer"
                                    style={{ color: "var(--text)" }}
                                >
                                    <input
                                        type="radio"
                                        name="scope"
                                        value="global"
                                        checked={scope === "global"}
                                        onChange={() => setScope("global")}
                                    />
                                    Global
                                </label>
                                <label
                                    className="flex items-center gap-2 text-sm cursor-pointer"
                                    style={{ color: "var(--text)" }}
                                >
                                    <input
                                        type="radio"
                                        name="scope"
                                        value="project"
                                        checked={scope === "project"}
                                        onChange={() => setScope("project")}
                                    />
                                    Por projeto
                                </label>
                            </div>
                        </div>
                        <div>
                            <label
                                className="block text-sm font-medium mb-2"
                                style={{ color: "var(--text)" }}
                            >
                                Status
                            </label>
                            <div className="flex items-center gap-2">
                                <Toggle
                                    checked={isActive}
                                    onChange={setIsActive}
                                />
                                <span
                                    className="text-sm"
                                    style={{ color: "var(--text)" }}
                                >
                                    {isActive ? "Ativa" : "Inativa"}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="cb-btn"
                        >
                            Cancelar
                        </button>
                        <button
                            type="submit"
                            className="cb-btn cb-btn-primary"
                            disabled={saving}
                        >
                            {saving
                                ? "Salvando..."
                                : isEditing
                                  ? "Salvar alterações"
                                  : "Criar tool"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ── Tool Card ────────────────────────────────────────────────────────

function ToolCard({ tool, onToggle, onEdit, onDelete, userRole }) {
    const [expanded, setExpanded] = useState(false);
    const [logs, setLogs] = useState([]);
    const [logsLoading, setLogsLoading] = useState(false);
    const [logsLoaded, setLogsLoaded] = useState(false);

    const provider = PROVIDER_CONFIG[tool.model_provider] || {
        label: tool.model_provider,
        color: "#888",
        bg: "#f0f0f0",
    };

    const triggerList = Array.isArray(tool.triggers) ? tool.triggers : [];

    async function loadLogs() {
        if (logsLoaded) return;
        setLogsLoading(true);
        try {
            const data = await getToolLogs(tool.id, 5);
            setLogs(data.logs || []);
            setLogsLoaded(true);
        } catch (err) {
            console.error("Failed to load logs:", err);
        } finally {
            setLogsLoading(false);
        }
    }

    function handleExpand() {
        const next = !expanded;
        setExpanded(next);
        if (next && !logsLoaded) {
            loadLogs();
        }
    }

    function formatDate(dateStr) {
        try {
            const d = new Date(dateStr);
            return d.toLocaleString("pt-BR", {
                day: "2-digit",
                month: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
            });
        } catch {
            return dateStr;
        }
    }

    const isAdmin = userRole === "admin";

    return (
        <div
            className="rounded-lg border p-4 transition-all"
            style={{
                borderColor: tool.is_active
                    ? "var(--card-border)"
                    : "var(--card-border)",
                backgroundColor: tool.is_active
                    ? "var(--card-bg)"
                    : "var(--bg)",
                opacity: tool.is_active ? 1 : 0.7,
            }}
        >
            {/* Header row */}
            <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                        <h4
                            className="text-sm font-semibold truncate"
                            style={{ color: "var(--text)" }}
                        >
                            {tool.name}
                        </h4>
                        <Badge
                            label={provider.label}
                            color={provider.color}
                            bg={provider.bg}
                            small
                        />
                        {tool.is_native && (
                            <Badge
                                label="Nativa"
                                color="var(--accent)"
                                bg="var(--accent-light)"
                                small
                            />
                        )}
                    </div>
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {triggerList.map((t) => (
                            <span
                                key={t}
                                className="text-[10px] px-1.5 py-0.5 rounded-full"
                                style={{
                                    color: "var(--muted-text)",
                                    backgroundColor: "var(--btn-hover-bg)",
                                    border: "1px solid var(--card-border)",
                                }}
                            >
                                {TRIGGER_LABELS[t] || t}
                            </span>
                        ))}
                        <span
                            className="text-[10px] px-1.5 py-0.5 rounded-full"
                            style={{
                                color: "var(--text-secondary)",
                                backgroundColor: "var(--btn-hover-bg)",
                                border: "1px solid var(--card-border)",
                            }}
                        >
                            →{" "}
                            {OUTPUT_TARGET_LABELS[tool.output_target] ||
                                tool.output_target}
                        </span>
                    </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                    <Toggle
                        checked={tool.is_active}
                        onChange={(val) => onToggle(tool.id, val)}
                    />
                </div>
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2 mt-3">
                <button
                    onClick={handleExpand}
                    className="cb-btn text-xs px-2 py-1"
                    title={expanded ? "Recolher" : "Expandir detalhes"}
                >
                    <svg
                        className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 9l-7 7-7-7"
                        />
                    </svg>
                    {expanded ? "Recolher" : "Detalhes"}
                </button>
                {isAdmin && (
                    <button
                        onClick={() => onEdit(tool)}
                        className="cb-btn text-xs px-2 py-1"
                        title="Editar tool"
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
                                d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                            />
                        </svg>
                        Editar
                    </button>
                )}
                {isAdmin && (
                    <button
                        onClick={() => onDelete(tool)}
                        disabled={tool.is_native}
                        className="cb-btn text-xs px-2 py-1 disabled:opacity-40 disabled:cursor-not-allowed"
                        title={
                            tool.is_native
                                ? "Tools nativas não podem ser excluídas"
                                : "Excluir tool"
                        }
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
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                        </svg>
                        Excluir
                    </button>
                )}
            </div>

            {/* Expanded section: description + prompt + logs */}
            {expanded && (
                <div
                    className="mt-3 pt-3 space-y-3"
                    style={{ borderTop: "1px solid var(--card-border)" }}
                >
                    <div>
                        <div
                            className="text-xs font-medium mb-1"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Descrição
                        </div>
                        <p
                            className="text-sm"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            {tool.description}
                        </p>
                    </div>

                    <div>
                        <div
                            className="text-xs font-medium mb-1"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Prompt (resumo)
                        </div>
                        <pre
                            className="text-xs p-2 rounded overflow-auto max-h-32 whitespace-pre-wrap break-words"
                            style={{
                                backgroundColor: "var(--bg)",
                                color: "var(--text-secondary)",
                                border: "1px solid var(--card-border)",
                            }}
                        >
                            {tool.prompt.length > 500
                                ? tool.prompt.slice(0, 500) + "…"
                                : tool.prompt}
                        </pre>
                    </div>

                    <div>
                        <div
                            className="text-xs font-medium mb-1"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Modelo
                        </div>
                        <p
                            className="text-xs font-mono"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            {tool.model_name}
                        </p>
                    </div>

                    {/* Logs */}
                    <div>
                        <div
                            className="text-xs font-medium mb-2"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Últimas execuções
                        </div>
                        {logsLoading ? (
                            <div
                                className="text-xs py-2 flex items-center gap-2"
                                style={{ color: "var(--muted-text)" }}
                            >
                                <svg
                                    className="h-3 w-3 animate-spin"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                >
                                    <circle
                                        cx="12"
                                        cy="12"
                                        r="10"
                                        strokeWidth={2}
                                        strokeDasharray="31.4"
                                        strokeDashoffset="10"
                                    />
                                </svg>
                                Carregando…
                            </div>
                        ) : logs.length === 0 ? (
                            <p
                                className="text-xs"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Nenhuma execução registrada.
                            </p>
                        ) : (
                            <div className="space-y-1">
                                {logs.map((log) => (
                                    <div
                                        key={log.id}
                                        className="flex items-center gap-3 text-xs py-1.5 px-2 rounded"
                                        style={{ backgroundColor: "var(--bg)" }}
                                    >
                                        <StatusIcon status={log.status} />
                                        <span
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            {formatDate(log.created_at)}
                                        </span>
                                        <span
                                            style={{
                                                color: "var(--text-secondary)",
                                            }}
                                        >
                                            {TRIGGER_LABELS[log.trigger] ||
                                                log.trigger}
                                        </span>
                                        {log.duration_ms != null && (
                                            <span
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                {log.duration_ms}ms
                                            </span>
                                        )}
                                        {log.status === "error" &&
                                            log.error_message && (
                                                <span
                                                    className="truncate flex-1"
                                                    style={{
                                                        color: "var(--danger)",
                                                    }}
                                                    title={log.error_message}
                                                >
                                                    {log.error_message.slice(
                                                        0,
                                                        80,
                                                    )}
                                                </span>
                                            )}
                                        {log.status === "success" &&
                                            log.output && (
                                                <span
                                                    className="truncate flex-1"
                                                    style={{
                                                        color: "var(--text-secondary)",
                                                    }}
                                                    title={log.output}
                                                >
                                                    {log.output.slice(0, 80)}
                                                </span>
                                            )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Confirm Delete Modal ─────────────────────────────────────────────

function ConfirmDeleteModal({ open, tool, onConfirm, onCancel, deleting }) {
    if (!open || !tool) return null;

    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4"
            style={{ backgroundColor: "var(--modal-overlay)" }}
        >
            <div className="cb-modal w-full max-w-md">
                <div className="cb-modal-body text-center py-6 space-y-4">
                    <div
                        className="mx-auto w-12 h-12 rounded-full flex items-center justify-center"
                        style={{ backgroundColor: "var(--danger-bg)" }}
                    >
                        <svg
                            className="h-6 w-6"
                            fill="none"
                            stroke="var(--danger)"
                            viewBox="0 0 24 24"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                        </svg>
                    </div>
                    <div>
                        <h3
                            className="text-base font-semibold"
                            style={{ color: "var(--text)" }}
                        >
                            Excluir tool?
                        </h3>
                        <p
                            className="text-sm mt-1"
                            style={{ color: "var(--muted-text)" }}
                        >
                            A tool <strong>"{tool.name}"</strong> e todos os
                            seus logs serão removidos permanentemente.
                        </p>
                    </div>
                    <div className="flex justify-center gap-3">
                        <button
                            onClick={onCancel}
                            className="cb-btn"
                            disabled={deleting}
                        >
                            Cancelar
                        </button>
                        <button
                            onClick={onConfirm}
                            className="cb-btn"
                            disabled={deleting}
                            style={{
                                backgroundColor: "var(--danger)",
                                color: "#fff",
                                border: "1px solid var(--danger)",
                            }}
                        >
                            {deleting ? "Excluindo..." : "Excluir"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ── Main ToolsManager component ──────────────────────────────────────

export default function ToolsManager({ userRole }) {
    const [tools, setTools] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    // Form modal state
    const [formOpen, setFormOpen] = useState(false);
    const [editingTool, setEditingTool] = useState(null);
    const [saving, setSaving] = useState(false);

    // Delete modal state
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [deleting, setDeleting] = useState(false);

    const isAdmin = userRole === "admin";

    // ── Load tools ──────────────────────────────────────────────────────

    const fetchTools = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const data = await listTools();
            setTools(data.tools || []);
        } catch (err) {
            const detail = err?.response?.data?.detail || err.message;
            setError(`Falha ao carregar tools: ${detail}`);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchTools();
    }, [fetchTools]);

    // ── Toggle ──────────────────────────────────────────────────────────

    async function handleToggle(toolId, isActive) {
        try {
            const updated = await toggleTool(toolId, isActive);
            setTools((prev) =>
                prev.map((t) =>
                    t.id === toolId
                        ? { ...t, is_active: updated.is_active }
                        : t,
                ),
            );
        } catch (err) {
            const detail = err?.response?.data?.detail || err.message;
            setError(`Falha ao alternar tool: ${detail}`);
        }
    }

    // ── Create / Edit ───────────────────────────────────────────────────

    function handleOpenCreate() {
        setEditingTool(null);
        setFormOpen(true);
    }

    function handleOpenEdit(tool) {
        setEditingTool(tool);
        setFormOpen(true);
    }

    async function handleSave(data) {
        setSaving(true);
        setError("");
        try {
            if (editingTool) {
                const updated = await updateTool(editingTool.id, data);
                setTools((prev) =>
                    prev.map((t) => (t.id === updated.id ? updated : t)),
                );
            } else {
                const created = await createTool(data);
                setTools((prev) => [created, ...prev]);
            }
            setFormOpen(false);
            setEditingTool(null);
        } catch (err) {
            const detail = err?.response?.data?.detail || err.message;
            setError(`Falha ao salvar tool: ${detail}`);
        } finally {
            setSaving(false);
        }
    }

    // ── Delete ──────────────────────────────────────────────────────────

    function handleOpenDelete(tool) {
        if (tool.is_native) return;
        setDeleteTarget(tool);
    }

    async function handleConfirmDelete() {
        if (!deleteTarget) return;
        setDeleting(true);
        setError("");
        try {
            await deleteTool(deleteTarget.id);
            setTools((prev) => prev.filter((t) => t.id !== deleteTarget.id));
            setDeleteTarget(null);
        } catch (err) {
            const detail = err?.response?.data?.detail || err.message;
            setError(`Falha ao excluir tool: ${detail}`);
        } finally {
            setDeleting(false);
        }
    }

    // ── Separate active vs inactive ─────────────────────────────────────

    const activeTools = tools.filter((t) => t.is_active);
    const inactiveTools = tools.filter((t) => !t.is_active);

    // ── Render ──────────────────────────────────────────────────────────

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h3
                        className="text-sm font-semibold"
                        style={{ color: "var(--text)" }}
                    >
                        Tools & Agentes
                    </h3>
                    <p
                        className="text-xs mt-0.5"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Ferramentas de IA que executam automaticamente em
                        diferentes etapas do pipeline.
                    </p>
                </div>
                {isAdmin && (
                    <button
                        onClick={handleOpenCreate}
                        className="cb-btn cb-btn-primary text-sm px-3 py-1.5"
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
                                d="M12 4v16m8-8H4"
                            />
                        </svg>
                        Nova Tool
                    </button>
                )}
            </div>

            {/* Error */}
            {error && (
                <div
                    className="rounded-lg border p-3 text-sm flex items-start gap-2"
                    style={{
                        borderColor: "var(--danger)",
                        backgroundColor: "var(--danger-bg)",
                        color: "var(--danger)",
                    }}
                >
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
                    <button
                        onClick={() => setError("")}
                        className="ml-auto text-xs underline flex-shrink-0"
                        style={{ color: "var(--danger)" }}
                    >
                        Fechar
                    </button>
                </div>
            )}

            {/* Loading */}
            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <svg
                        className="h-6 w-6 animate-spin"
                        style={{ color: "var(--spinner)" }}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                    >
                        <circle
                            cx="12"
                            cy="12"
                            r="10"
                            strokeWidth={2}
                            strokeDasharray="31.4"
                            strokeDashoffset="10"
                        />
                    </svg>
                    <span
                        className="ml-2 text-sm"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Carregando tools…
                    </span>
                </div>
            ) : tools.length === 0 ? (
                <div className="text-center py-12">
                    <div className="text-4xl mb-3">🤖</div>
                    <div
                        className="text-sm font-medium"
                        style={{ color: "var(--text-secondary)" }}
                    >
                        Nenhuma tool configurada
                    </div>
                    <p
                        className="text-xs mt-1"
                        style={{ color: "var(--muted-text)" }}
                    >
                        {isAdmin
                            ? 'Clique em "Nova Tool" para criar sua primeira ferramenta de IA.'
                            : "O administrador ainda não configurou ferramentas de IA."}
                    </p>
                </div>
            ) : (
                <div className="space-y-5">
                    {/* Active tools */}
                    {activeTools.length > 0 && (
                        <div>
                            <div
                                className="text-xs font-medium mb-2 flex items-center gap-1.5"
                                style={{ color: "var(--success)" }}
                            >
                                <span
                                    className="w-2 h-2 rounded-full"
                                    style={{
                                        backgroundColor: "var(--success)",
                                    }}
                                />
                                Ativas ({activeTools.length})
                            </div>
                            <div className="space-y-3">
                                {activeTools.map((tool) => (
                                    <ToolCard
                                        key={tool.id}
                                        tool={tool}
                                        onToggle={handleToggle}
                                        onEdit={handleOpenEdit}
                                        onDelete={handleOpenDelete}
                                        userRole={userRole}
                                    />
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Inactive tools */}
                    {inactiveTools.length > 0 && (
                        <div>
                            <div
                                className="text-xs font-medium mb-2 flex items-center gap-1.5"
                                style={{ color: "var(--muted-text)" }}
                            >
                                <span
                                    className="w-2 h-2 rounded-full"
                                    style={{
                                        backgroundColor: "var(--card-border)",
                                    }}
                                />
                                Inativas ({inactiveTools.length})
                            </div>
                            <div className="space-y-3">
                                {inactiveTools.map((tool) => (
                                    <ToolCard
                                        key={tool.id}
                                        tool={tool}
                                        onToggle={handleToggle}
                                        onEdit={handleOpenEdit}
                                        onDelete={handleOpenDelete}
                                        userRole={userRole}
                                    />
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Form modal */}
            <ToolFormModal
                open={formOpen}
                onClose={() => {
                    setFormOpen(false);
                    setEditingTool(null);
                }}
                onSave={handleSave}
                tool={editingTool}
                saving={saving}
            />

            {/* Confirm delete modal */}
            <ConfirmDeleteModal
                open={!!deleteTarget}
                tool={deleteTarget}
                onConfirm={handleConfirmDelete}
                onCancel={() => setDeleteTarget(null)}
                deleting={deleting}
            />
        </div>
    );
}
