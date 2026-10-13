import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import { api, testApiKeys } from "../../utils/api";
import ToolsManager from "../shared/ToolsManager";
import {
    Users,
    UserPlus,
    Search,
    X,
    Shield,
    ShieldOff,
    ShieldCheck,
    BarChart3,
    ChevronLeft,
    ChevronRight,
    Loader2,
    ArrowLeft,
    Check,
    AlertTriangle,
    Save,
    Undo2,
    LayoutDashboard,
    FolderTree,
    Settings,
    Trash2,
    UserMinus,
    UserCheck,
    UserX,
    RotateCcw,
    Archive,
    CheckCircle2,
    XCircle,
    Info,
    Stethoscope,
    ExternalLink,
    Mail,
    Coins,
    Plus,
    Minus,
    DollarSign,
    History,
    Youtube,
    FileText,
    Upload,
    RefreshCw,
    Clock,
    ToggleLeft,
    ToggleRight,
    Edit3,
    Sparkles,
    Zap,
    Mic,
    Code,
    File,
    FileDown,
} from "lucide-react";
import SmtpDiagnosticModal from "./SmtpDiagnosticModal";
import TemplatesTab from "./TemplatesTab";
import LoginBackground from "../../pages/login/LoginBackground";

// ─── Helper Functions ───────────────────────────────────────────────

/**
 * Safely extract error message from various error formats
 * Handles: strings, error objects with .message, API responses with .response.data.detail
 */
function getErrorMessage(error) {
    if (!error) return "";
    if (typeof error === "string") return error;
    if (error?.message) return String(error.message);

    const detail = error?.response?.data?.detail;
    if (detail) {
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail)) {
            // Handle FastAPI validation error list
            return detail
                .map((d) => (typeof d === "string" ? d : d.msg || JSON.stringify(d)))
                .join(", ");
        }
        if (typeof detail === "object") {
            return detail.msg || JSON.stringify(detail);
        }
        return String(detail);
    }

    return String(error);
}

// ─── Toast Notification System ──────────────────────────────────────

function ToastContainer({ toasts, removeToast }) {
    return (
        <div
            className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none"
            style={{ maxWidth: "420px" }}
        >
            {toasts.map((t) => (
                <Toast key={t.id} toast={t} onClose={() => removeToast(t.id)} />
            ))}
        </div>
    );
}

function Toast({ toast, onClose }) {
    const [exiting, setExiting] = useState(false);

    useEffect(() => {
        const timer = setTimeout(() => {
            setExiting(true);
            setTimeout(onClose, 300);
        }, toast.duration || 4000);
        return () => clearTimeout(timer);
    }, [toast.duration, onClose]);

    const icons = {
        success: (
            <CheckCircle2
                className="h-5 w-5 flex-shrink-0"
                style={{ color: "#22c55e" }}
            />
        ),
        error: (
            <XCircle
                className="h-5 w-5 flex-shrink-0"
                style={{ color: "#ef4444" }}
            />
        ),
        info: (
            <Info
                className="h-5 w-5 flex-shrink-0"
                style={{ color: "#3b82f6" }}
            />
        ),
        warning: (
            <AlertTriangle
                className="h-5 w-5 flex-shrink-0"
                style={{ color: "#f59e0b" }}
            />
        ),
    };

    const borderColors = {
        success: "#22c55e",
        error: "#ef4444",
        info: "#3b82f6",
        warning: "#f59e0b",
    };

    return (
        <div
            className="pointer-events-auto rounded-lg border p-3 text-sm flex items-start gap-3 shadow-lg backdrop-blur-sm"
            style={{
                borderColor: borderColors[toast.type] || borderColors.info,
                backgroundColor: "var(--panel)",
                color: "var(--text)",
                animation: exiting
                    ? "toast-out 0.3s ease-in forwards"
                    : "toast-in 0.3s ease-out",
            }}
        >
            {icons[toast.type] || icons.info}
            <div className="flex-1 min-w-0">
                {toast.title && (
                    <p className="font-semibold text-sm mb-0.5">
                        {toast.title}
                    </p>
                )}
                <p className="text-sm" style={{ color: "var(--muted-text)" }}>
                    {toast.message}
                </p>
            </div>
            <button
                onClick={() => {
                    setExiting(true);
                    setTimeout(onClose, 300);
                }}
                className="flex-shrink-0 p-0.5 rounded hover:bg-black/10"
            >
                <X
                    className="h-3.5 w-3.5"
                    style={{ color: "var(--muted-text)" }}
                />
            </button>
            <style>{`
                @keyframes toast-in {
                    from { opacity: 0; transform: translateX(100%); }
                    to { opacity: 1; transform: translateX(0); }
                }
                @keyframes toast-out {
                    from { opacity: 1; transform: translateX(0); }
                    to { opacity: 0; transform: translateX(100%); }
                }
            `}</style>
        </div>
    );
}

function useToast() {
    const [toasts, setToasts] = useState([]);
    const idRef = useRef(0);

    const addToast = useCallback(
        (type, message, title = null, duration = 4000) => {
            const id = ++idRef.current;
            setToasts((prev) => [
                ...prev,
                { id, type, message, title, duration },
            ]);
        },
        [],
    );

    const removeToast = useCallback((id) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    return { toasts, removeToast, addToast };
}

// Wrap toast methods as a simple object builder
function buildToastMethods(addToast) {
    return {
        success: (msg, title) => addToast("success", msg, title),
        error: (msg, title) => addToast("error", msg, title || "Erro"),
        info: (msg, title) => addToast("info", msg, title),
        warning: (msg, title) => addToast("warning", msg, title),
    };
}

// ─── Tab Components (Metrics, Groups, Settings) ─────────────────────

/* ── Helper: mini bar chart (pure CSS, no lib needed) ─────────────── */
function MiniBar({ value, max, color = "var(--accent)" }) {
    const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
    return (
        <div
            className="h-2 rounded-full overflow-hidden"
            style={{ backgroundColor: "var(--border)", width: "100%" }}
        >
            <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, backgroundColor: color }}
            />
        </div>
    );
}

/* ── Provider color helper ────────────────────────────────────────── */
function providerColor(p) {
    const m = (p || "").toLowerCase();
    if (m.includes("gemini")) return "#4285f4";
    
    if (m.includes("whisper")) return "#a855f7";
    return "#6b7280";
}

function providerLabel(p) {
    const m = (p || "").toLowerCase();
    if (m.includes("gemini")) return "Gemini";
    
    if (m.includes("whisper")) return "Whisper";
    return p || "Outro";
}

/* ── Friendly endpoint label ──────────────────────────────────────── */
function endpointLabel(ep) {
    const map = {
        "/smart-text": "Smart Text",
        "/enhance-document": "Aprimorar Documento",
        "/describe-gif": "Descrever GIF",
        "/generate-documentation": "Gerar Documentação",
        "/format-and-export": "Formatar & Exportar",
        "/export-documentation": "Exportar Documentação",
    };
    return map[ep] || ep || "—";
}

/* ── Relative time helper ─────────────────────────────────────────── */
function relativeTime(isoStr) {
    if (!isoStr) return "—";
    try {
        const d = new Date(isoStr);
        const now = new Date();
        const diffMs = now - d;
        const diffMin = Math.floor(diffMs / 60000);
        if (diffMin < 1) return "agora";
        if (diffMin < 60) return `${diffMin}min atrás`;
        const diffH = Math.floor(diffMin / 60);
        if (diffH < 24) return `${diffH}h atrás`;
        const diffD = Math.floor(diffH / 24);
        return `${diffD}d atrás`;
    } catch {
        return "—";
    }
}

function MetricsTab({ StatCard }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeSection, setActiveSection] = useState("overview"); // overview | providers | endpoints | users | activity

    useEffect(() => {
        api.get("/admin/dashboard/overview")
            .then((res) => setData(res.data))
            .catch(() => setData(null))
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center py-20">
                <Loader2
                    className="h-8 w-8 animate-spin"
                    style={{ color: "var(--accent)" }}
                />
            </div>
        );
    }

    if (!data)
        return (
            <p style={{ color: "var(--muted-text)" }}>
                Não foi possível carregar métricas.
            </p>
        );

    const {
        today = {},
        month = {},
        trends = {},
        top_endpoints = [],
        top_users = [],
        recent_activity = [],
        daily_chart = [],
    } = data || {};
    const monthProviders = month.providers || [];
    const todayProviders = today.providers || [];
    const maxEndpointReqs = Math.max(
        ...((top_endpoints || []).map((e) => e?.requests || 0)),
        1,
    );
    const maxUserReqs = Math.max(
        ...((top_users || []).map((u) => u?.requests || 0)),
        1,
    );

    const sectionTabs = [
        { id: "overview", label: "Visão Geral" },
        { id: "providers", label: "Provedores" },
        { id: "endpoints", label: "Endpoints" },
        { id: "users", label: "Top Usuários" },
        { id: "activity", label: "Atividade Recente" },
    ];

    return (
        <div className="space-y-6">
            {/* ── Section Tabs ────────────────────────────────────────────── */}
            <div className="flex gap-1 flex-wrap">
                {sectionTabs.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveSection(tab.id)}
                        className="px-3 py-1.5 text-xs font-medium rounded-md transition-colors"
                        style={{
                            backgroundColor:
                                activeSection === tab.id
                                    ? "var(--accent)"
                                    : "var(--panel)",
                            color:
                                activeSection === tab.id
                                    ? "#fff"
                                    : "var(--muted-text)",
                            border: "1px solid var(--border)",
                        }}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* ═══════════════════ OVERVIEW ═══════════════════════════════ */}
            {activeSection === "overview" && (
                <div className="space-y-6">
                    <h2 className="text-lg font-semibold">Visão geral</h2>

                    {/* KPI Cards */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <StatCard
                            label="Hoje - Requisições IA"
                            value={today.ai_requests}
                            color="var(--accent)"
                        />
                        <StatCard
                            label="Hoje - Usuários ativos"
                            value={today.active_users}
                        />
                        <StatCard
                            label="Mês - Requisições IA"
                            value={month.ai_requests}
                            color="#f59e0b"
                        />
                        <StatCard
                            label="Mês - Custo (USD)"
                            value={`$${(month.total_cost_usd ?? 0).toFixed(2)}`}
                        />
                    </div>

                    {/* Trends */}
                    <div
                        className="flex gap-4 text-sm flex-wrap"
                        style={{ color: "var(--muted-text)" }}
                    >
                        <span>
                            Tendência: Requisições{" "}
                            <span
                                style={{
                                    color:
                                        trends.videos_growth_percent > 0
                                            ? "#22c55e"
                                            : trends.videos_growth_percent < 0
                                              ? "#ef4444"
                                              : "var(--muted-text)",
                                }}
                            >
                                {trends.videos_growth_percent >= 0 ? "+" : ""}
                                {trends.videos_growth_percent}%
                            </span>
                        </span>
                        <span>
                            Usuários{" "}
                            <span
                                style={{
                                    color:
                                        trends.users_growth_percent > 0
                                            ? "#22c55e"
                                            : trends.users_growth_percent < 0
                                              ? "#ef4444"
                                              : "var(--muted-text)",
                                }}
                            >
                                {trends.users_growth_percent >= 0 ? "+" : ""}
                                {trends.users_growth_percent}%
                            </span>
                        </span>
                    </div>

                    {/* Today's provider mini-summary */}
                    {todayProviders.length > 0 && (
                        <div
                            className="rounded-lg border p-4"
                            style={{
                                backgroundColor: "var(--panel)",
                                borderColor: "var(--border)",
                            }}
                        >
                            <h3
                                className="text-sm font-semibold mb-3"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Hoje por provedor
                            </h3>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                {todayProviders.map((p) => (
                                    <div
                                        key={p.provider}
                                        className="flex items-center gap-3"
                                    >
                                        <div
                                            className="w-2 h-2 rounded-full flex-shrink-0"
                                            style={{
                                                backgroundColor: providerColor(
                                                    p.provider,
                                                ),
                                            }}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <div className="text-xs font-medium">
                                                {providerLabel(p.provider)}
                                            </div>
                                            <div
                                                className="text-xs"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                {p.requests} req · $
                                                {p.cost_usd.toFixed(4)}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Daily chart (simple bar chart) */}
                    {daily_chart && daily_chart.length > 0 && (
                        <div
                            className="rounded-lg border p-4"
                            style={{
                                backgroundColor: "var(--panel)",
                                borderColor: "var(--border)",
                            }}
                        >
                            <h3
                                className="text-sm font-semibold mb-3"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Requisições por dia (últimos 30 dias)
                            </h3>
                            <div
                                className="flex items-end gap-[2px]"
                                style={{ height: "120px" }}
                            >
                                {(() => {
                                    const maxReqs = Math.max(
                                        ...((daily_chart || []).map((d) => d?.requests || 0)),
                                        1,
                                    );
                                    return daily_chart.map((d, i) => {
                                        const pct = Math.max(
                                            (d.requests / maxReqs) * 100,
                                            d.requests > 0 ? 4 : 1,
                                        );
                                        return (
                                            <div
                                                key={i}
                                                className="flex-1 rounded-t transition-all duration-300 group relative"
                                                style={{
                                                    height: `${pct}%`,
                                                    backgroundColor:
                                                        d.requests > 0
                                                            ? "var(--accent)"
                                                            : "var(--border)",
                                                    minWidth: "4px",
                                                    opacity:
                                                        d.requests > 0
                                                            ? 1
                                                            : 0.3,
                                                }}
                                                title={`${d.date}: ${d.requests} req, $${d.cost_usd.toFixed(4)}, ${d.active_users} usuários`}
                                            />
                                        );
                                    });
                                })()}
                            </div>
                            <div
                                className="flex justify-between mt-1 text-[10px]"
                                style={{ color: "var(--muted-text)" }}
                            >
                                <span>
                                    {daily_chart[0]?.date
                                        ? new Date(
                                              daily_chart[0].date + "T00:00:00",
                                          ).toLocaleDateString("pt-BR", {
                                              day: "2-digit",
                                              month: "short",
                                          })
                                        : ""}
                                </span>
                                <span>
                                    {daily_chart[daily_chart.length - 1]?.date
                                        ? new Date(
                                              daily_chart[
                                                  daily_chart.length - 1
                                              ].date + "T00:00:00",
                                          ).toLocaleDateString("pt-BR", {
                                              day: "2-digit",
                                              month: "short",
                                          })
                                        : ""}
                                </span>
                            </div>
                        </div>
                    )}

                    {/* Empty state hint */}
                    {today.ai_requests === 0 && month.ai_requests === 0 && (
                        <div
                            className="rounded-lg border p-6 text-center"
                            style={{
                                backgroundColor: "var(--panel)",
                                borderColor: "var(--border)",
                            }}
                        >
                            <BarChart3
                                className="h-10 w-10 mx-auto mb-3"
                                style={{
                                    color: "var(--muted-text)",
                                    opacity: 0.4,
                                }}
                            />
                            <p
                                className="text-sm font-medium mb-1"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Nenhuma métrica registrada ainda
                            </p>
                            <p
                                className="text-xs"
                                style={{
                                    color: "var(--muted-text)",
                                    opacity: 0.7,
                                }}
                            >
                                As métricas serão exibidas assim que requisições
                                de IA forem realizadas (Smart Text, Aprimorar
                                Documento, Descrever GIF, etc.).
                            </p>
                        </div>
                    )}
                </div>
            )}

            {/* ═══════════════════ PROVIDERS ══════════════════════════════ */}
            {activeSection === "providers" && (
                <div className="space-y-6">
                    <h2 className="text-lg font-semibold">
                        Uso por Provedor (Mês)
                    </h2>

                    {monthProviders.length === 0 ? (
                        <p
                            className="text-sm"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Nenhum uso de provedor registrado neste mês.
                        </p>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {monthProviders.map((p) => (
                                <div
                                    key={p.provider}
                                    className="rounded-lg border p-4"
                                    style={{
                                        backgroundColor: "var(--panel)",
                                        borderColor: "var(--border)",
                                    }}
                                >
                                    <div className="flex items-center gap-2 mb-3">
                                        <div
                                            className="w-3 h-3 rounded-full"
                                            style={{
                                                backgroundColor: providerColor(
                                                    p.provider,
                                                ),
                                            }}
                                        />
                                        <span className="font-semibold text-sm">
                                            {providerLabel(p.provider)}
                                        </span>
                                    </div>
                                    <div className="grid grid-cols-3 gap-2 text-center">
                                        <div>
                                            <div
                                                className="text-xl font-bold"
                                                style={{
                                                    color: providerColor(
                                                        p.provider,
                                                    ),
                                                }}
                                            >
                                                {p.requests}
                                            </div>
                                            <div
                                                className="text-[10px] uppercase tracking-wider"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                Requisições
                                            </div>
                                        </div>
                                        <div>
                                            <div className="text-xl font-bold">
                                                {p.tokens_used.toLocaleString()}
                                            </div>
                                            <div
                                                className="text-[10px] uppercase tracking-wider"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                Tokens
                                            </div>
                                        </div>
                                        <div>
                                            <div className="text-xl font-bold">
                                                ${p.cost_usd.toFixed(4)}
                                            </div>
                                            <div
                                                className="text-[10px] uppercase tracking-wider"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                Custo
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Today breakdown */}
                    {todayProviders.length > 0 && (
                        <>
                            <h3
                                className="text-sm font-semibold"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Hoje
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                {todayProviders.map((p) => (
                                    <div
                                        key={p.provider}
                                        className="rounded-lg border p-3 flex items-center gap-3"
                                        style={{
                                            backgroundColor: "var(--panel)",
                                            borderColor: "var(--border)",
                                        }}
                                    >
                                        <div
                                            className="w-2 h-2 rounded-full flex-shrink-0"
                                            style={{
                                                backgroundColor: providerColor(
                                                    p.provider,
                                                ),
                                            }}
                                        />
                                        <div className="flex-1">
                                            <span className="text-sm font-medium">
                                                {providerLabel(p.provider)}
                                            </span>
                                        </div>
                                        <span className="text-sm font-bold">
                                            {p.requests}
                                        </span>
                                        <span
                                            className="text-xs"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            ${p.cost_usd.toFixed(4)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </div>
            )}

            {/* ═══════════════════ ENDPOINTS ══════════════════════════════ */}
            {activeSection === "endpoints" && (
                <div className="space-y-4">
                    <h2 className="text-lg font-semibold">
                        Top Endpoints (Mês)
                    </h2>

                    {!top_endpoints || top_endpoints.length === 0 ? (
                        <p
                            className="text-sm"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Nenhum endpoint utilizado neste mês.
                        </p>
                    ) : (
                        <div
                            className="rounded-lg border overflow-hidden"
                            style={{
                                backgroundColor: "var(--panel)",
                                borderColor: "var(--border)",
                            }}
                        >
                            <table className="admin-table w-full text-sm">
                                <thead>
                                    <tr
                                        style={{
                                            borderBottom:
                                                "1px solid var(--border)",
                                        }}
                                    >
                                        <th
                                            className="text-left px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Endpoint
                                        </th>
                                        <th
                                            className="text-right px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Requisições
                                        </th>
                                        <th
                                            className="text-right px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Custo
                                        </th>
                                        <th
                                            className="px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                                            style={{
                                                color: "var(--muted-text)",
                                                width: "30%",
                                            }}
                                        >
                                            &nbsp;
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(top_endpoints || []).map((ep, idx) => (
                                        <tr
                                            key={ep?.endpoint || idx}
                                            style={{
                                                borderBottom:
                                                    idx <
                                                    (top_endpoints?.length || 0) - 1
                                                        ? "1px solid var(--border)"
                                                        : "none",
                                            }}
                                        >
                                            <td className="px-4 py-2.5 font-medium">
                                                {endpointLabel(ep?.endpoint)}
                                            </td>
                                            <td className="px-4 py-2.5 text-right font-bold">
                                                {ep?.requests || 0}
                                            </td>
                                            <td
                                                className="px-4 py-2.5 text-right"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                ${(ep?.cost_usd || 0).toFixed(4)}
                                            </td>
                                            <td className="px-4 py-2.5">
                                                <MiniBar
                                                    value={ep?.requests || 0}
                                                    max={maxEndpointReqs}
                                                    color="var(--accent)"
                                                />
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* ═══════════════════ TOP USERS ══════════════════════════════ */}
            {activeSection === "users" && (
                <div className="space-y-4">
                    <h2 className="text-lg font-semibold">
                        Top Usuários (Mês)
                    </h2>

                    {!top_users || top_users.length === 0 ? (
                        <p
                            className="text-sm"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Nenhum uso registrado neste mês.
                        </p>
                    ) : (
                        <div
                            className="rounded-lg border overflow-hidden"
                            style={{
                                backgroundColor: "var(--panel)",
                                borderColor: "var(--border)",
                            }}
                        >
                            <table className="admin-table w-full text-sm">
                                <thead>
                                    <tr
                                        style={{
                                            borderBottom:
                                                "1px solid var(--border)",
                                        }}
                                    >
                                        <th
                                            className="text-left px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Usuário
                                        </th>
                                        <th
                                            className="text-right px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Requisições
                                        </th>
                                        <th
                                            className="text-right px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Custo
                                        </th>
                                        <th
                                            className="px-4 py-2 text-xs font-semibold uppercase tracking-wider"
                                            style={{
                                                color: "var(--muted-text)",
                                                width: "30%",
                                            }}
                                        >
                                            &nbsp;
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(top_users || []).map((u, idx) => (
                                        <tr
                                            key={u?.user_id || idx}
                                            style={{
                                                borderBottom:
                                                    idx < (top_users?.length || 0) - 1
                                                        ? "1px solid var(--border)"
                                                        : "none",
                                            }}
                                        >
                                            <td className="px-4 py-2.5">
                                                <div className="font-medium truncate max-w-[200px]">
                                                    {u?.name || "Anônimo"}
                                                </div>
                                            </td>
                                            <td className="px-4 py-2.5 text-right font-bold">
                                                {u?.requests || 0}
                                            </td>
                                            <td
                                                className="px-4 py-2.5 text-right"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                ${(u?.cost_usd || 0).toFixed(4)}
                                            </td>
                                            <td className="px-4 py-2.5">
                                                <MiniBar
                                                    value={u?.requests || 0}
                                                    max={maxUserReqs}
                                                    color="#f59e0b"
                                                />
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {/* ═══════════════════ RECENT ACTIVITY ════════════════════════ */}
            {activeSection === "activity" && (
                <div className="space-y-4">
                    <h2 className="text-lg font-semibold">Atividade Recente</h2>

                    {!recent_activity || recent_activity.length === 0 ? (
                        <p
                            className="text-sm"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Nenhuma atividade recente registrada.
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {(recent_activity || []).map((a, idx) => (
                                <div
                                    key={a?.id || idx}
                                    className="rounded-lg border p-3 flex items-center gap-3"
                                    style={{
                                        backgroundColor: "var(--panel)",
                                        borderColor: "var(--border)",
                                    }}
                                >
                                    {/* Provider dot */}
                                    <div
                                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                                        style={{
                                            backgroundColor: providerColor(
                                                a?.ai_provider,
                                            ),
                                        }}
                                    />

                                    {/* Info */}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="text-sm font-medium truncate max-w-[150px]">
                                                {a?.user_name || "Anônimo"}
                                            </span>
                                            <span
                                                className="text-xs px-1.5 py-0.5 rounded"
                                                style={{
                                                    backgroundColor:
                                                        providerColor(
                                                            a?.ai_provider,
                                                        ) + "22",
                                                    color: providerColor(
                                                        a?.ai_provider,
                                                    ),
                                                }}
                                            >
                                                {providerLabel(a?.ai_provider)}
                                            </span>
                                            <span
                                                className="text-xs"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                {endpointLabel(a.endpoint)}
                                            </span>
                                        </div>
                                    </div>

                                    {/* Cost & time */}
                                    <div className="text-right flex-shrink-0">
                                        <div className="text-xs font-medium">
                                            ${a.cost_usd.toFixed(4)}
                                        </div>
                                        <div
                                            className="text-[10px]"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            {relativeTime(a.timestamp)}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function GroupsTab({ setError, setSuccessMsg }) {
    const [groups, setGroups] = useState([]);
    const [loading, setLoading] = useState(true);
    const [createOpen, setCreateOpen] = useState(false);
    const [createForm, setCreateForm] = useState({
        name: "",
        description: "",
        parent_group_id: null,
        max_storage_gb: 100,
        max_monthly_ai_requests: 1000,
        can_use_gemini: true,
        
        can_use_whisper: true,
    });
    const [createLoading, setCreateLoading] = useState(false);

    const [editGroup, setEditGroup] = useState(null);
    const [editForm, setEditForm] = useState({
        name: "",
        description: "",
        parent_group_id: null,
        max_storage_gb: 100,
        max_monthly_ai_requests: 1000,
        can_use_gemini: true,
        
        can_use_whisper: true,
        can_export_html: true,
        can_export_docx: true,
        can_export_md: true,
        can_export_pdf: true,
    });
    const [editLoading, setEditLoading] = useState(false);

    const [detailGroup, setDetailGroup] = useState(null);
    const [members, setMembers] = useState([]);
    const [membersLoading, setMembersLoading] = useState(false);
    const [usage, setUsage] = useState(null);
    const [usageLoading, setUsageLoading] = useState(false);
    const [addMemberOpen, setAddMemberOpen] = useState(false);
    const [usersForAdd, setUsersForAdd] = useState([]);
    const [usersForAddLoading, setUsersForAddLoading] = useState(false);
    const [addMemberUserId, setAddMemberUserId] = useState("");
    const [addMemberRole, setAddMemberRole] = useState("member");
    const [addMemberSubmitting, setAddMemberSubmitting] = useState(false);
    const [removeMemberLoading, setRemoveMemberLoading] = useState(null);
    const [deleteGroupConfirm, setDeleteGroupConfirm] = useState(false);
    const [deleteGroupLoading, setDeleteGroupLoading] = useState(false);

    const fetchGroups = useCallback(() => {
        setLoading(true);
        api.get("/admin/groups")
            .then((res) => setGroups(res.data || []))
            .catch(() => setGroups([]))
            .finally(() => setLoading(false));
    }, []);
    useEffect(() => {
        fetchGroups();
    }, [fetchGroups]);
    async function handleCreateGroup(e) {
        e.preventDefault();
        setCreateLoading(true);
        setError?.("");
        try {
            const body = {
                name: createForm.name.trim(),
                description: createForm.description?.trim() || null,
                parent_group_id: createForm.parent_group_id || null,
                max_storage_gb: Number(createForm.max_storage_gb) || 100,
                max_monthly_ai_requests:
                    Number(createForm.max_monthly_ai_requests) || 1000,
                can_use_gemini: !!createForm.can_use_gemini,
                
                can_use_whisper: !!createForm.can_use_whisper,
            };
            await api.post("/admin/groups", body);
            setCreateOpen(false);
            setCreateForm({
                name: "",
                description: "",
                parent_group_id: null,
                max_storage_gb: 100,
                max_monthly_ai_requests: 1000,
                can_use_gemini: true,
                
                can_use_whisper: true,
            });
            setSuccessMsg?.("Grupo criado com sucesso!");
            fetchGroups();
        } catch (e) {
            setError?.(getErrorMessage(e) || "Falha ao criar grupo");
        } finally {
            setCreateLoading(false);
        }
    }

    function openEditGroup(g) {
        setEditGroup(g);
        setEditForm({
            name: g.name,
            description: g.description ?? "",
            parent_group_id: g.parent_group_id ?? null,
            max_storage_gb: g.max_storage_gb ?? 100,
            max_monthly_ai_requests: g.max_monthly_ai_requests ?? 1000,
            can_use_gemini: !!g.can_use_gemini,
            
            can_use_whisper: !!g.can_use_whisper,
        });
    }

    async function handleSaveEditGroup(e) {
        e.preventDefault();
        if (!editGroup) return;
        setEditLoading(true);
        setError?.("");
        try {
            const body = {
                name: editForm.name.trim(),
                description: editForm.description?.trim() || null,
                parent_group_id: editForm.parent_group_id || null,
                max_storage_gb: Number(editForm.max_storage_gb) || 100,
                max_monthly_ai_requests:
                    Number(editForm.max_monthly_ai_requests) || 1000,
                can_use_gemini: !!editForm.can_use_gemini,
                
                can_use_whisper: !!editForm.can_use_whisper,
            };
            await api.put(`/admin/groups/${editGroup.id}`, body);
            setEditGroup(null);
            setSuccessMsg?.("Grupo atualizado com sucesso!");
            fetchGroups();
            if (detailGroup?.id === editGroup.id) {
                setDetailGroup((prev) => (prev ? { ...prev, ...body } : null));
            }
        } catch (e) {
            setError?.(getErrorMessage(e) || "Falha ao atualizar grupo");
        } finally {
            setEditLoading(false);
        }
    }

    function openDetailGroup(g) {
        setDetailGroup(g);
        setMembers([]);
        setUsage(null);
        setAddMemberOpen(false);
        setAddMemberUserId("");
        setAddMemberRole("member");
        setDeleteGroupConfirm(false);
        setMembersLoading(true);
        setUsageLoading(true);
        api.get(`/admin/groups/${g.id}/members`)
            .then((res) => setMembers(res.data || []))
            .catch(() => setMembers([]))
            .finally(() => setMembersLoading(false));
        api.get(`/admin/groups/${g.id}/usage`)
            .then((res) => setUsage(res.data))
            .catch(() => setUsage(null))
            .finally(() => setUsageLoading(false));
    }

    function closeDetailGroup() {
        setDetailGroup(null);
        setMembers([]);
        setUsage(null);
        setAddMemberOpen(false);
        setUsersForAdd([]);
        setDeleteGroupConfirm(false);
    }

    function openAddMemberDropdown() {
        setAddMemberOpen(true);
        setUsersForAddLoading(true);
        setUsersForAdd([]);
        setAddMemberUserId("");
        api.get("/admin/users", { params: { page: 1, page_size: 100 } })
            .then((res) => {
                const list = res.data?.users || [];
                const memberIds = new Set(members.map((m) => m.user_id));
                setUsersForAdd(list.filter((u) => !memberIds.has(u.id)));
            })
            .catch(() => setUsersForAdd([]))
            .finally(() => setUsersForAddLoading(false));
    }

    async function handleAddMember(e) {
        e.preventDefault();
        if (!detailGroup || !addMemberUserId) return;
        setAddMemberSubmitting(true);
        setError?.("");
        try {
            await api.post(`/admin/groups/${detailGroup.id}/members`, {
                user_id: addMemberUserId,
                role: addMemberRole,
            });
            setSuccessMsg?.("Usuário adicionado ao grupo!");
            setAddMemberOpen(false);
            setAddMemberUserId("");
            api.get(`/admin/groups/${detailGroup.id}/members`)
                .then((res) => setMembers(res.data || []))
                .catch(() => {});
            fetchGroups();
        } catch (e) {
            setError?.(
                getErrorMessage(e) || "Falha ao adicionar usuário",
            );
        } finally {
            setAddMemberSubmitting(false);
        }
    }

    async function handleRemoveMember(userId) {
        if (!detailGroup) return;
        setRemoveMemberLoading(userId);
        setError?.("");
        try {
            await api.delete(
                `/admin/groups/${detailGroup.id}/members/${userId}`,
            );
            setMembers((prev) => prev.filter((m) => m.user_id !== userId));
            setSuccessMsg?.("Membro removido.");
            fetchGroups();
        } catch (e) {
            setError?.(getErrorMessage(e) || "Falha ao remover membro");
        } finally {
            setRemoveMemberLoading(null);
        }
    }

    async function handleDeleteGroup() {
        if (!detailGroup) return;
        setDeleteGroupLoading(true);
        setError?.("");
        try {
            await api.delete(`/admin/groups/${detailGroup.id}`);
            setSuccessMsg?.("Grupo removido.");
            closeDetailGroup();
            fetchGroups();
        } catch (e) {
            setError?.(getErrorMessage(e) || "Falha ao deletar grupo");
        } finally {
            setDeleteGroupLoading(false);
        }
    }

    if (loading && groups.length === 0) {
        return (
            <div className="flex items-center justify-center py-20">
                <Loader2
                    className="h-8 w-8 animate-spin"
                    style={{ color: "var(--accent)" }}
                />
            </div>
        );
    }
    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">
                    Grupos / Departamentos
                </h2>
                <button
                    onClick={() => setCreateOpen(true)}
                    className="cb-btn cb-btn-primary flex items-center gap-2"
                >
                    <UserPlus className="h-4 w-4" />
                    Novo Grupo
                </button>
            </div>
            {groups.length === 0 ? (
                <p style={{ color: "var(--muted-text)" }}>
                    Nenhum grupo cadastrado. Clique em &quot;Novo Grupo&quot;
                    para criar.
                </p>
            ) : (
                <div
                    className="rounded-xl border overflow-hidden"
                    style={{
                        borderColor: "var(--card-border)",
                        backgroundColor: "var(--card-bg)",
                    }}
                >
                    <table className="admin-table w-full text-sm">
                        <thead>
                            <tr
                                style={{
                                    backgroundColor: "var(--panel)",
                                    borderBottom:
                                        "1px solid var(--panel-border)",
                                }}
                            >
                                <th
                                    className="text-left px-4 py-3 font-medium"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Nome
                                </th>
                                <th
                                    className="text-left px-4 py-3 font-medium"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Descrição
                                </th>
                                <th
                                    className="text-right px-4 py-3 font-medium"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Membros
                                </th>
                                <th
                                    className="text-right px-4 py-3 font-medium"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Ações
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {groups.map((g) => (
                                <tr
                                    key={g.id}
                                    style={{
                                        borderBottom:
                                            "1px solid var(--panel-border)",
                                    }}
                                >
                                    <td className="px-4 py-3 font-medium">
                                        {g.name}
                                    </td>
                                    <td
                                        className="px-4 py-3"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        {g.description || "-"}
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        {g.member_count ?? 0}
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <div className="flex items-center justify-end gap-1">
                                            <button
                                                type="button"
                                                onClick={() => openEditGroup(g)}
                                                className="cb-btn p-2 transition-all duration-200 hover:scale-105 active:scale-95"
                                                title="Editar grupo"
                                            >
                                                <Edit3 className="h-4 w-4" />
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    openDetailGroup(g)
                                                }
                                                className="cb-btn p-2 transition-all duration-200 hover:scale-105 active:scale-95"
                                                title="Gerenciar membros e detalhes"
                                            >
                                                <Users className="h-4 w-4" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Modal Novo Grupo */}
            {createOpen && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
                    onClick={() => setCreateOpen(false)}
                >
                    <div
                        className="cb-panel w-full max-w-md p-6"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold flex items-center gap-2">
                                <UserPlus
                                    className="h-5 w-5"
                                    style={{ color: "var(--accent)" }}
                                />
                                Novo Grupo
                            </h2>
                            <button
                                onClick={() => setCreateOpen(false)}
                                className="cb-btn p-1"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <form
                            onSubmit={handleCreateGroup}
                            className="space-y-4"
                        >
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Nome *
                                </label>
                                <input
                                    type="text"
                                    value={createForm.name}
                                    onChange={(e) =>
                                        setCreateForm((f) => ({
                                            ...f,
                                            name: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    required
                                    placeholder="Ex: Marketing"
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Descrição
                                </label>
                                <input
                                    type="text"
                                    value={createForm.description || ""}
                                    onChange={(e) =>
                                        setCreateForm((f) => ({
                                            ...f,
                                            description: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    placeholder="Ex: Equipe de marketing"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label
                                        className="block text-sm font-medium mb-1"
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Storage (GB)
                                    </label>
                                    <input
                                        type="number"
                                        min="1"
                                        value={createForm.max_storage_gb}
                                        onChange={(e) =>
                                            setCreateForm((f) => ({
                                                ...f,
                                                max_storage_gb: e.target.value,
                                            }))
                                        }
                                        className="cb-input w-full"
                                    />
                                </div>
                                <div>
                                    <label
                                        className="block text-sm font-medium mb-1"
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Requests IA/mês
                                    </label>
                                    <input
                                        type="number"
                                        min="1"
                                        value={
                                            createForm.max_monthly_ai_requests
                                        }
                                        onChange={(e) =>
                                            setCreateForm((f) => ({
                                                ...f,
                                                max_monthly_ai_requests:
                                                    e.target.value,
                                            }))
                                        }
                                        className="cb-input w-full"
                                    />
                                </div>
                            </div>
                            <div className="flex gap-4 flex-wrap">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={createForm.can_use_gemini}
                                        onChange={(e) =>
                                            setCreateForm((prev) => ({
                                                ...prev,
                                                can_use_gemini:
                                                    e.target.checked,
                                            }))
                                        }
                                        className="rounded border-[var(--card-border)] bg-[var(--panel)]"
                                    />
                                    <span className="text-sm">Gemini</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                    <input
                                        type="checkbox"
                                        checked={createForm.can_use_whisper}
                                        onChange={(e) =>
                                            setCreateForm((f) => ({
                                                ...f,
                                                can_use_whisper:
                                                    e.target.checked,
                                            }))
                                        }
                                        className="rounded"
                                    />
                                    <span className="text-sm">Whisper</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                    <input
                                        type="checkbox"
                                        checked={createForm.can_export_html}
                                        onChange={(e) =>
                                            setCreateForm((f) => ({
                                                ...f,
                                                can_export_html: e.target.checked,
                                            }))
                                        }
                                        className="rounded"
                                    />
                                    <span className="text-sm">HTML</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                    <input
                                        type="checkbox"
                                        checked={createForm.can_export_docx}
                                        onChange={(e) =>
                                            setCreateForm((f) => ({
                                                ...f,
                                                can_export_docx: e.target.checked,
                                            }))
                                        }
                                        className="rounded"
                                    />
                                    <span className="text-sm">Word</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                    <input
                                        type="checkbox"
                                        checked={createForm.can_export_md}
                                        onChange={(e) =>
                                            setCreateForm((f) => ({
                                                ...f,
                                                can_export_md: e.target.checked,
                                            }))
                                        }
                                        className="rounded"
                                    />
                                    <span className="text-sm">Markdown</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                    <input
                                        type="checkbox"
                                        checked={createForm.can_export_pdf}
                                        onChange={(e) =>
                                            setCreateForm((f) => ({
                                                ...f,
                                                can_export_pdf: e.target.checked,
                                            }))
                                        }
                                        className="rounded"
                                    />
                                    <span className="text-sm">PDF</span>
                                </label>
                            </div>
                            <div className="flex gap-2 pt-2">
                                <button
                                    type="submit"
                                    disabled={createLoading}
                                    className="cb-btn cb-btn-primary flex-1 flex items-center justify-center gap-2"
                                >
                                    {createLoading ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <UserPlus className="h-4 w-4" />
                                    )}
                                    Criar
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setCreateOpen(false)}
                                    className="cb-btn flex-1"
                                >
                                    Cancelar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Modal Editar Grupo */}
            {editGroup && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
                    onClick={() => setEditGroup(null)}
                >
                    <div
                        className="cb-panel w-full max-w-md p-6"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold flex items-center gap-2">
                                <Edit3
                                    className="h-5 w-5"
                                    style={{ color: "var(--accent)" }}
                                />
                                Editar grupo
                            </h2>
                            <button
                                onClick={() => setEditGroup(null)}
                                className="cb-btn p-1"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <form
                            onSubmit={handleSaveEditGroup}
                            className="space-y-4"
                        >
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Nome *
                                </label>
                                <input
                                    type="text"
                                    value={editForm.name}
                                    onChange={(e) =>
                                        setEditForm((f) => ({
                                            ...f,
                                            name: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    required
                                    placeholder="Ex: Marketing"
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Descrição
                                </label>
                                <input
                                    type="text"
                                    value={editForm.description || ""}
                                    onChange={(e) =>
                                        setEditForm((f) => ({
                                            ...f,
                                            description: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    placeholder="Ex: Equipe de marketing"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label
                                        className="block text-sm font-medium mb-1"
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Storage (GB)
                                    </label>
                                    <input
                                        type="number"
                                        min="1"
                                        value={editForm.max_storage_gb}
                                        onChange={(e) =>
                                            setEditForm((f) => ({
                                                ...f,
                                                max_storage_gb: e.target.value,
                                            }))
                                        }
                                        className="cb-input w-full"
                                    />
                                </div>
                                <div>
                                    <label
                                        className="block text-sm font-medium mb-1"
                                        style={{
                                            color: "var(--text-secondary)",
                                        }}
                                    >
                                        Requests IA/mês
                                    </label>
                                    <input
                                        type="number"
                                        min="1"
                                        value={editForm.max_monthly_ai_requests}
                                        onChange={(e) =>
                                            setEditForm((f) => ({
                                                ...f,
                                                max_monthly_ai_requests:
                                                    e.target.value,
                                            }))
                                        }
                                        className="cb-input w-full"
                                    />
                                </div>
                            </div>
                            <div>
                                <span
                                    className="block text-sm font-medium mb-2"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Permissões do grupo
                                </span>
                                <div className="flex gap-4 flex-wrap">
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={editForm.can_use_gemini}
                                            onChange={(e) =>
                                                setEditForm((prev) => ({
                                                    ...prev,
                                                    can_use_gemini:
                                                        e.target.checked,
                                                }))
                                            }
                                            className="rounded border-[var(--card-border)] bg-[var(--panel)]"
                                        />
                                        <span className="text-sm">Gemini</span>
                                    </label>
                                    <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                        <input
                                            type="checkbox"
                                            checked={editForm.can_use_whisper}
                                            onChange={(e) =>
                                                setEditForm((f) => ({
                                                    ...f,
                                                    can_use_whisper:
                                                        e.target.checked,
                                                }))
                                            }
                                            className="rounded"
                                        />
                                        <span className="text-sm">Whisper</span>
                                    </label>
                                    <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                        <input
                                            type="checkbox"
                                            checked={editForm.can_export_html}
                                            onChange={(e) =>
                                                setEditForm((f) => ({
                                                    ...f,
                                                    can_export_html:
                                                        e.target.checked,
                                                }))
                                            }
                                            className="rounded"
                                        />
                                        <span className="text-sm">HTML</span>
                                    </label>
                                    <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                        <input
                                            type="checkbox"
                                            checked={editForm.can_export_docx}
                                            onChange={(e) =>
                                                setEditForm((f) => ({
                                                    ...f,
                                                    can_export_docx:
                                                        e.target.checked,
                                                }))
                                            }
                                            className="rounded"
                                        />
                                        <span className="text-sm">Word</span>
                                    </label>
                                    <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                        <input
                                            type="checkbox"
                                            checked={editForm.can_export_md}
                                            onChange={(e) =>
                                                setEditForm((f) => ({
                                                    ...f,
                                                    can_export_md:
                                                        e.target.checked,
                                                }))
                                            }
                                            className="rounded"
                                        />
                                        <span className="text-sm">Markdown</span>
                                    </label>
                                    <label className="flex items-center gap-2 cursor-pointer cb-no-select">
                                        <input
                                            type="checkbox"
                                            checked={editForm.can_export_pdf}
                                            onChange={(e) =>
                                                setEditForm((f) => ({
                                                    ...f,
                                                    can_export_pdf:
                                                        e.target.checked,
                                                }))
                                            }
                                            className="rounded"
                                        />
                                        <span className="text-sm">PDF</span>
                                    </label>
                                </div>
                            </div>
                            <div className="flex gap-2 pt-2">
                                <button
                                    type="submit"
                                    disabled={editLoading}
                                    className="cb-btn cb-btn-primary flex-1 flex items-center justify-center gap-2"
                                >
                                    {editLoading ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Save className="h-4 w-4" />
                                    )}
                                    Salvar
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setEditGroup(null)}
                                    className="cb-btn flex-1"
                                >
                                    Cancelar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Modal Detalhes do Grupo (membros + uso + deletar) */}
            {detailGroup && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 py-6 overflow-y-auto"
                    onClick={closeDetailGroup}
                >
                    <div
                        className="cb-panel w-full max-w-2xl p-6 my-4"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-6">
                            <div>
                                <h2 className="text-lg font-semibold flex items-center gap-2">
                                    <FolderTree
                                        className="h-5 w-5"
                                        style={{ color: "var(--accent)" }}
                                    />
                                    {detailGroup.name}
                                </h2>
                                <p
                                    className="text-sm mt-1"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    {detailGroup.description || "Sem descrição"}
                                </p>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setEditGroup(detailGroup);
                                        openEditGroup(detailGroup);
                                    }}
                                    className="cb-btn flex items-center gap-2"
                                >
                                    <Edit3 className="h-4 w-4" />
                                    Editar grupo
                                </button>
                                <button
                                    onClick={closeDetailGroup}
                                    className="cb-btn p-1"
                                >
                                    <X className="h-4 w-4" />
                                </button>
                            </div>
                        </div>

                        {/* Uso */}
                        <section className="mb-6">
                            <h3
                                className="text-sm font-semibold mb-3"
                                style={{ color: "var(--text-secondary)" }}
                            >
                                Uso
                            </h3>
                            {usageLoading ? (
                                <div
                                    className="flex items-center gap-2 py-4"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    <span className="text-sm">
                                        Carregando...
                                    </span>
                                </div>
                            ) : usage ? (
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                    <div
                                        className="rounded-lg border p-3"
                                        style={{
                                            borderColor: "var(--card-border)",
                                            backgroundColor: "var(--panel)",
                                        }}
                                    >
                                        <p
                                            className="text-xs font-medium"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Storage
                                        </p>
                                        <p className="text-sm font-semibold">
                                            {usage.current_storage_gb ?? 0} /{" "}
                                            {usage.max_storage_gb} GB
                                        </p>
                                    </div>
                                    <div
                                        className="rounded-lg border p-3"
                                        style={{
                                            borderColor: "var(--card-border)",
                                            backgroundColor: "var(--panel)",
                                        }}
                                    >
                                        <p
                                            className="text-xs font-medium"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Requests IA (mês)
                                        </p>
                                        <p className="text-sm font-semibold">
                                            {usage.monthly_ai_requests ?? 0} /{" "}
                                            {usage.max_monthly_ai_requests}
                                        </p>
                                    </div>
                                    <div
                                        className="rounded-lg border p-3"
                                        style={{
                                            borderColor: "var(--card-border)",
                                            backgroundColor: "var(--panel)",
                                        }}
                                    >
                                        <p
                                            className="text-xs font-medium"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Custo (mês)
                                        </p>
                                        <p className="text-sm font-semibold">
                                            $
                                            {(
                                                usage.cost_this_month_usd ?? 0
                                            ).toFixed(2)}
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <p
                                    className="text-sm py-2"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Nenhum uso registrado.
                                </p>
                            )}
                        </section>

                        {/* Membros */}
                        <section className="mb-6">
                            <div className="flex items-center justify-between mb-3">
                                <h3
                                    className="text-sm font-semibold"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Membros
                                </h3>
                                <button
                                    type="button"
                                    onClick={openAddMemberDropdown}
                                    className="cb-btn cb-btn-primary flex items-center gap-2 text-sm"
                                >
                                    <UserPlus className="h-4 w-4" />
                                    Adicionar usuário
                                </button>
                            </div>
                            {addMemberOpen && (
                                <div
                                    className="rounded-lg border p-4 mb-4"
                                    style={{
                                        borderColor: "var(--card-border)",
                                        backgroundColor: "var(--panel)",
                                    }}
                                >
                                    <form
                                        onSubmit={handleAddMember}
                                        className="space-y-3"
                                    >
                                        <div>
                                            <label
                                                className="block text-sm font-medium mb-1"
                                                style={{
                                                    color: "var(--text-secondary)",
                                                }}
                                            >
                                                Usuário
                                            </label>
                                            <select
                                                value={addMemberUserId}
                                                onChange={(e) =>
                                                    setAddMemberUserId(
                                                        e.target.value,
                                                    )
                                                }
                                                className="cb-input w-full"
                                                required
                                                disabled={usersForAddLoading}
                                            >
                                                <option value="">
                                                    Selecione...
                                                </option>
                                                {usersForAdd.map((u) => (
                                                    <option
                                                        key={u.id}
                                                        value={u.id}
                                                    >
                                                        {u.email}{" "}
                                                        {u.full_name
                                                            ? `(${u.full_name})`
                                                            : ""}
                                                    </option>
                                                ))}
                                            </select>
                                            {usersForAdd.length === 0 &&
                                                !usersForAddLoading && (
                                                    <p
                                                        className="text-xs mt-1"
                                                        style={{
                                                            color: "var(--muted-text)",
                                                        }}
                                                    >
                                                        Todos os usuários já
                                                        estão no grupo.
                                                    </p>
                                                )}
                                        </div>
                                        <div>
                                            <label
                                                className="block text-sm font-medium mb-1"
                                                style={{
                                                    color: "var(--text-secondary)",
                                                }}
                                            >
                                                Função
                                            </label>
                                            <select
                                                value={addMemberRole}
                                                onChange={(e) =>
                                                    setAddMemberRole(
                                                        e.target.value,
                                                    )
                                                }
                                                className="cb-input w-full"
                                            >
                                                <option value="member">
                                                    Membro
                                                </option>
                                                <option value="admin">
                                                    Admin
                                                </option>
                                            </select>
                                        </div>
                                        <div className="flex gap-2">
                                            <button
                                                type="submit"
                                                disabled={
                                                    addMemberSubmitting ||
                                                    !addMemberUserId
                                                }
                                                className="cb-btn cb-btn-primary flex items-center gap-2"
                                            >
                                                {addMemberSubmitting ? (
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                ) : (
                                                    <UserPlus className="h-4 w-4" />
                                                )}
                                                Adicionar
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    setAddMemberOpen(false)
                                                }
                                                className="cb-btn"
                                            >
                                                Cancelar
                                            </button>
                                        </div>
                                    </form>
                                </div>
                            )}
                            {membersLoading ? (
                                <div
                                    className="flex items-center gap-2 py-6"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    <span className="text-sm">
                                        Carregando membros...
                                    </span>
                                </div>
                            ) : members.length === 0 ? (
                                <div
                                    className="rounded-lg border border-dashed py-8 text-center"
                                    style={{
                                        borderColor: "var(--card-border)",
                                    }}
                                >
                                    <Users
                                        className="h-10 w-10 mx-auto mb-2 opacity-50"
                                        style={{ color: "var(--muted-text)" }}
                                    />
                                    <p
                                        className="text-sm"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        Nenhum membro neste grupo.
                                    </p>
                                    <p
                                        className="text-xs mt-1"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        Clique em &quot;Adicionar usuário&quot;
                                        para incluir.
                                    </p>
                                </div>
                            ) : (
                                <div
                                    className="rounded-xl border overflow-hidden"
                                    style={{
                                        borderColor: "var(--card-border)",
                                        backgroundColor: "var(--card-bg)",
                                    }}
                                >
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr
                                                style={{
                                                    backgroundColor:
                                                        "var(--panel)",
                                                    borderBottom:
                                                        "1px solid var(--panel-border)",
                                                }}
                                            >
                                                <th
                                                    className="text-left px-4 py-3 font-medium"
                                                    style={{
                                                        color: "var(--muted-text)",
                                                    }}
                                                >
                                                    Usuário
                                                </th>
                                                <th
                                                    className="text-left px-4 py-3 font-medium"
                                                    style={{
                                                        color: "var(--muted-text)",
                                                    }}
                                                >
                                                    Função
                                                </th>
                                                <th className="w-24"></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {members.map((m) => (
                                                <tr
                                                    key={m.user_id}
                                                    style={{
                                                        borderBottom:
                                                            "1px solid var(--panel-border)",
                                                    }}
                                                >
                                                    <td className="px-4 py-3">
                                                        <span className="font-medium">
                                                            {m.user_email ??
                                                                m.user_id}
                                                        </span>
                                                        {m.user_full_name && (
                                                            <span
                                                                className="block text-xs"
                                                                style={{
                                                                    color: "var(--muted-text)",
                                                                }}
                                                            >
                                                                {
                                                                    m.user_full_name
                                                                }
                                                            </span>
                                                        )}
                                                    </td>
                                                    <td
                                                        className="px-4 py-3"
                                                        style={{
                                                            color: "var(--muted-text)",
                                                        }}
                                                    >
                                                        {m.role || "member"}
                                                    </td>
                                                    <td className="px-4 py-3 text-right">
                                                        <button
                                                            type="button"
                                                            onClick={() =>
                                                                handleRemoveMember(
                                                                    m.user_id,
                                                                )
                                                            }
                                                            disabled={
                                                                removeMemberLoading ===
                                                                m.user_id
                                                            }
                                                            className="cb-btn p-2 transition-all duration-200 hover:scale-105 active:scale-95"
                                                            title="Remover do grupo"
                                                        >
                                                            {removeMemberLoading ===
                                                            m.user_id ? (
                                                                <Loader2 className="h-4 w-4 animate-spin" />
                                                            ) : (
                                                                <UserMinus className="h-4 w-4" />
                                                            )}
                                                        </button>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </section>

                        {/* Deletar grupo */}
                        <section
                            className="pt-4 border-t"
                            style={{ borderColor: "var(--panel-border)" }}
                        >
                            {!deleteGroupConfirm ? (
                                <button
                                    type="button"
                                    onClick={() => setDeleteGroupConfirm(true)}
                                    className="cb-btn flex items-center gap-2"
                                    style={{
                                        color: "var(--destructive, #dc2626)",
                                    }}
                                >
                                    <Trash2 className="h-4 w-4" />
                                    Deletar grupo
                                </button>
                            ) : (
                                <div
                                    className="rounded-lg border p-4"
                                    style={{
                                        borderColor: "var(--card-border)",
                                        backgroundColor: "var(--panel)",
                                    }}
                                >
                                    <p className="text-sm font-medium mb-2">
                                        Tem certeza? O grupo e suas associações
                                        serão removidos.
                                    </p>
                                    <div className="flex gap-2">
                                        <button
                                            type="button"
                                            onClick={handleDeleteGroup}
                                            disabled={deleteGroupLoading}
                                            className="cb-btn flex items-center gap-2"
                                            style={{
                                                backgroundColor:
                                                    "var(--destructive, #dc2626)",
                                                color: "#fff",
                                            }}
                                        >
                                            {deleteGroupLoading ? (
                                                <Loader2 className="h-4 w-4 animate-spin" />
                                            ) : (
                                                <Trash2 className="h-4 w-4" />
                                            )}
                                            Sim, deletar
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() =>
                                                setDeleteGroupConfirm(false)
                                            }
                                            className="cb-btn"
                                        >
                                            Cancelar
                                        </button>
                                    </div>
                                </div>
                            )}
                        </section>
                    </div>
                </div>
            )}
        </div>
    );
}

// ─── API Key Test Section (used inside SettingsTab > AI category) ────

function ApiKeyTestSection() {
    const [testing, setTesting] = useState(false);
    const [result, setResult] = useState(null);

    async function handleTest() {
        setTesting(true);
        setResult(null);
        try {
            // Uses server-side keys (configured in the backend's .env or database)
            const res = await testApiKeys();
            setResult(res);
        } catch {
            setResult({
                gemini: false,
                
                geminiError: "Erro ao testar",
                
            });
        } finally {
            setTesting(false);
        }
    }

    return (
        <div
            className="rounded-xl border p-5 space-y-4"
            style={{
                borderColor: "var(--card-border)",
                backgroundColor: "var(--card-bg)",
            }}
        >
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <h3
                        className="text-sm font-semibold"
                        style={{ color: "var(--text)" }}
                    >
                        Testar Chaves de API
                    </h3>
                    <p
                        className="text-xs mt-0.5"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Verifica a conectividade com o Gemini usando as
                        chaves configuradas no servidor.
                    </p>
                </div>
                <button
                    onClick={handleTest}
                    disabled={testing}
                    className="cb-btn cb-btn-primary flex items-center gap-2 text-sm"
                    style={{ opacity: testing ? 0.7 : 1 }}
                >
                    {testing ? (
                        <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Testando...
                        </>
                    ) : (
                        <>
                            <Stethoscope className="h-4 w-4" />
                            Testar API
                        </>
                    )}
                </button>
            </div>

            {result && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {/* Gemini */}
                    <div
                        className="rounded-lg border p-3 flex items-start gap-3"
                        style={{
                            borderColor: result.gemini
                                ? "rgba(34,197,94,0.4)"
                                : "rgba(239,68,68,0.4)",
                            backgroundColor: result.gemini
                                ? "rgba(34,197,94,0.06)"
                                : "rgba(239,68,68,0.06)",
                        }}
                    >
                        {result.gemini ? (
                            <CheckCircle2
                                className="h-5 w-5 flex-shrink-0 mt-0.5"
                                style={{ color: "#22c55e" }}
                            />
                        ) : (
                            <XCircle
                                className="h-5 w-5 flex-shrink-0 mt-0.5"
                                style={{ color: "#ef4444" }}
                            />
                        )}
                        <div className="min-w-0">
                            <p
                                className="text-sm font-semibold"
                                style={{
                                    color: result.gemini
                                        ? "#22c55e"
                                        : "#ef4444",
                                }}
                            >
                                Gemini{" "}
                                {result.gemini ? "✓ Conectado" : "✗ Falhou"}
                            </p>
                            {!result.gemini && result.geminiError && (
                                <p
                                    className="text-xs mt-0.5 break-words"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    {result.geminiError}
                                </p>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function YoutubeAuthSection({ addToast }) {
    const [diag, setDiag] = useState(null);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef(null);

    const fetchDiag = useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.get("/admin/youtube-diagnostic");
            setDiag(res.data);
        } catch (err) {
            console.error("Failed to fetch YouTube diagnostic:", err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchDiag();
    }, [fetchDiag]);

    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        if (!file.name.endsWith(".txt")) {
            addToast("error", "O arquivo deve ser um .txt (formato Netscape)");
            return;
        }

        setUploading(true);
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await api.post("/admin/youtube-cookies", formData);
            addToast("success", res.data.message);
            fetchDiag();
        } catch (err) {
            addToast(
                "error",
                getErrorMessage(err) || "Falha ao enviar cookies.",
            );
        } finally {
            setUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = "";
        }
    };

    return (
        <div
            className="mt-10 rounded-xl border p-6"
            style={{
                borderColor: "var(--card-border)",
                backgroundColor: "var(--card-bg)",
            }}
        >
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div
                        className="p-2.5 rounded-lg"
                        style={{ backgroundColor: "#ff000020" }}
                    >
                        <Youtube
                            className="h-6 w-6"
                            style={{ color: "#ff0000" }}
                        />
                    </div>
                    <div>
                        <h3 className="text-lg font-semibold">
                            Autenticação YouTube
                        </h3>
                        <p
                            className="text-sm"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Gerencie cookies e diagnóstico do yt-dlp
                        </p>
                    </div>
                </div>
                <button
                    onClick={fetchDiag}
                    disabled={loading}
                    className="cb-btn text-xs flex items-center gap-2"
                >
                    {loading ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                        <RotateCcw className="h-3 w-3" />
                    )}
                    Atualizar Diagnóstico
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                    <div className="space-y-3">
                        <h4
                            className="text-xs font-bold uppercase tracking-wider"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Status Atual
                        </h4>

                        {loading && !diag ? (
                            <div className="animate-pulse space-y-2">
                                <div
                                    className="h-4 w-3/4 rounded"
                                    style={{ backgroundColor: "var(--border)" }}
                                ></div>
                                <div
                                    className="h-4 w-1/2 rounded"
                                    style={{ backgroundColor: "var(--border)" }}
                                ></div>
                            </div>
                        ) : diag ? (
                            <div className="space-y-2.5">
                                <StatusRow
                                    label="yt-dlp instalado"
                                    status={
                                        diag.ytdlp_installed ? "ok" : "error"
                                    }
                                    value={
                                        diag.ytdlp_version || "Não instalado"
                                    }
                                />
                                <StatusRow
                                    label="Arquivo cookies.txt"
                                    status={
                                        diag.cookies_file_exists
                                            ? "ok"
                                            : "warning"
                                    }
                                    value={
                                        diag.cookies_file_exists
                                            ? `Ativo (${diag.cookies_file_lines} linhas)`
                                            : "Ausente"
                                    }
                                />
                                <StatusRow
                                    label="Proxy Residencial"
                                    status={
                                        diag.proxy_configured ? "ok" : "warning"
                                    }
                                    value={
                                        diag.proxy_configured
                                            ? "Configurado"
                                            : "Ausente"
                                    }
                                />
                                <StatusRow
                                    label="Plugin PO Token"
                                    status={
                                        diag.po_token_plugin_installed
                                            ? "ok"
                                            : "warning"
                                    }
                                    value={
                                        diag.po_token_plugin_installed
                                            ? "Instalado"
                                            : "Ausente"
                                    }
                                />
                            </div>
                        ) : null}
                    </div>

                    {diag?.recommended_action && (
                        <div
                            className="p-4 rounded-lg border text-sm"
                            style={{
                                backgroundColor: "#f59e0b10",
                                borderColor: "#f59e0b40",
                                color: "#f59e0b",
                            }}
                        >
                            <div className="flex gap-2 font-semibold mb-1">
                                <AlertTriangle className="h-4 w-4" />
                                Ação Recomendada
                            </div>
                            <p className="text-xs leading-relaxed opacity-90">
                                {diag.recommended_action}
                            </p>
                        </div>
                    )}
                </div>

                <div className="space-y-4">
                    <h4
                        className="text-xs font-bold uppercase tracking-wider"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Upload de cookies.txt
                    </h4>

                    <div
                        className="relative border-2 border-dashed rounded-xl p-8 text-center transition-colors group cursor-pointer"
                        onClick={() => fileInputRef.current?.click()}
                        style={{
                            borderColor: uploading
                                ? "var(--accent)"
                                : "var(--border)",
                            backgroundColor: "var(--panel)",
                        }}
                    >
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleFileUpload}
                            className="hidden"
                            accept=".txt"
                        />
                        {uploading ? (
                            <div className="space-y-2">
                                <Loader2 className="h-10 w-10 animate-spin mx-auto text-blue-500" />
                                <p className="text-sm font-medium">
                                    Instalando cookies...
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                <div
                                    className="w-12 h-12 rounded-full mx-auto flex items-center justify-center transition-transform group-hover:scale-110"
                                    style={{ backgroundColor: "var(--border)" }}
                                >
                                    <Upload className="h-6 w-6" />
                                </div>
                                <div>
                                    <p className="text-sm font-semibold">
                                        Selecione o novo cookies.txt
                                    </p>
                                    <p
                                        className="text-xs mt-1"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        Arraste ou clique para enviar (Formato
                                        Netscape)
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>

                    <div
                        className="p-4 rounded-lg text-xs space-y-2"
                        style={{
                            backgroundColor: "var(--panel)",
                            color: "var(--muted-text)",
                        }}
                    >
                        <p className="flex items-center gap-2">
                            <Info className="h-3.5 w-3.5" />
                            Use extensões como "Get cookies.txt LOCALLY" para
                            exportar.
                        </p>
                        <p className="flex items-center gap-2">
                            <Check className="h-3.5 w-3.5 text-green-500" />
                            Os cookies permitem o download de vídeos bloqueados
                            para bots.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

function StatusRow({ label, status, value }) {
    const isOk = status === "ok";
    const isError = status === "error";

    return (
        <div
            className="flex items-center justify-between py-1 border-b last:border-0"
            style={{ borderColor: "var(--border)" }}
        >
            <span className="text-sm" style={{ color: "var(--muted-text)" }}>
                {label}
            </span>
            <div className="flex items-center gap-2">
                <span
                    className="text-xs font-mono"
                    style={{ color: "var(--text)" }}
                >
                    {value}
                </span>
                {isOk ? (
                    <CheckCircle2 className="h-4 w-4 text-green-500" />
                ) : isError ? (
                    <XCircle className="h-4 w-4 text-red-500" />
                ) : (
                    <AlertTriangle className="h-4 w-4 text-yellow-500" />
                )}
            </div>
        </div>
    );
}

function SettingsTab({ setError, setSuccessMsg }) {
    const [settings, setSettings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [category, setCategory] = useState("smtp");
    const [edited, setEdited] = useState({});
    const [diagnosticOpen, setDiagnosticOpen] = useState(false);

    const fetchSettings = useCallback(() => {
        setLoading(true);
        api.get("/admin/settings", { params: { category } })
            .then((res) => setSettings(res.data || []))
            .catch(() => setSettings([]))
            .finally(() => setLoading(false));
    }, [category]);

    useEffect(() => {
        fetchSettings();
        setEdited({});
    }, [category, fetchSettings]);

    const getValue = (s) => {
        const k = `${category}:${s.key}`;
        return edited[k] !== undefined ? edited[k] : (s.value ?? "");
    };
    const setValue = (s, val) => {
        const k = `${category}:${s.key}`;
        setEdited((prev) => ({ ...prev, [k]: val }));
    };
    const hasChanges = Object.keys(edited).length > 0;

    const handleSave = async () => {
        if (!hasChanges) return;

        // Validate SMTP username must be a full email address
        if (category === "smtp") {
            const usernameKey = `smtp:username`;
            const usernameVal =
                edited[usernameKey] !== undefined
                    ? edited[usernameKey]
                    : (settings.find((s) => s.key === "username")?.value ?? "");
            if (usernameVal && !usernameVal.includes("@")) {
                setError?.(
                    "O usuário SMTP deve ser o seu e-mail completo (ex: your-address@gmail.com). " +
                        "O Gmail rejeita envios quando o usuário não é um endereço de e-mail válido.",
                );
                return;
            }
        }

        setSaving(true);
        setError?.("");
        try {
            const payload = Object.entries(edited).map(([k, v]) => {
                const [, key] = k.split(":");
                return { category, key, value: v };
            });
            await api.put("/admin/settings", { settings: payload });
            setEdited({});
            setSuccessMsg?.("Configurações salvas com sucesso!");
            fetchSettings();
        } catch (e) {
            setError?.(
                getErrorMessage(e) || "Falha ao salvar configurações",
            );
        } finally {
            setSaving(false);
        }
    };

    // Build current SMTP config from saved + edited values for the diagnostic modal
    const smtpConfig = useMemo(() => {
        if (category !== "smtp") return {};
        const cfg = {};
        for (const s of settings) {
            const k = `${category}:${s.key}`;
            const val = edited[k] !== undefined ? edited[k] : (s.value ?? "");
            cfg[s.key] = val;
        }
        return cfg;
    }, [category, settings, edited]);

    // Detect Gmail host from current (possibly edited) SMTP settings
    const isSmtpCategory = category === "smtp";
    const smtpHost = useMemo(() => {
        if (!isSmtpCategory) return "";
        const hostSetting = settings.find((s) => s.key === "host");
        if (!hostSetting) return "";
        const k = `smtp:host`;
        const val =
            edited[k] !== undefined ? edited[k] : (hostSetting.value ?? "");
        return (val || "").toLowerCase();
    }, [isSmtpCategory, settings, edited]);

    const isGmail =
        smtpHost.includes("smtp.gmail.com") || smtpHost.includes("gmail");

    const categories = ["smtp", "ai", "storage", "security", "features"];
    const CATEGORY_LABELS = {
        smtp: "SMTP",
        ai: "IA",
        storage: "Storage",
        security: "Segurança",
        features: "Recursos",
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
                <h2 className="text-lg font-semibold">
                    Configurações do Sistema
                </h2>
                <div className="flex items-center gap-2">
                    {/* Testar Conexão – only visible on SMTP tab */}
                    {isSmtpCategory && (
                        <button
                            onClick={() => setDiagnosticOpen(true)}
                            className="cb-btn flex items-center gap-2 text-sm"
                            style={{
                                borderColor: "var(--accent)",
                                color: "var(--accent)",
                            }}
                        >
                            <Stethoscope className="h-4 w-4" />
                            Testar Conexão
                        </button>
                    )}
                    {hasChanges && (
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="cb-btn cb-btn-primary flex items-center gap-2"
                        >
                            {saving ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <Check className="h-4 w-4" />
                            )}
                            Salvar alterações
                        </button>
                    )}
                </div>
            </div>

            {/* Category tabs */}
            <div className="flex gap-2 flex-wrap">
                {categories.map((c) => (
                    <button
                        key={c}
                        onClick={() => setCategory(c)}
                        className="cb-btn px-3 py-1.5 text-sm"
                        style={
                            category === c
                                ? {
                                      backgroundColor: "var(--accent)",
                                      color: "#fff",
                                  }
                                : {}
                        }
                    >
                        {CATEGORY_LABELS[c] || c}
                    </button>
                ))}
            </div>

            {/* Settings table */}
            {loading ? (
                <div className="flex items-center justify-center py-10">
                    <Loader2
                        className="h-6 w-6 animate-spin"
                        style={{ color: "var(--accent)" }}
                    />
                </div>
            ) : category === "ai" ? (
                <div className="space-y-6">
                    <ApiKeyTestSection />
                </div>
            ) : settings.length === 0 ? (
                <p style={{ color: "var(--muted-text)" }}>
                    Nenhuma configuração nesta categoria.
                </p>
            ) : (
                <div
                    className="rounded-xl border overflow-hidden"
                    style={{
                        borderColor: "var(--card-border)",
                        backgroundColor: "var(--card-bg)",
                    }}
                >
                    <table className="w-full text-sm">
                        <thead>
                            <tr
                                style={{
                                    backgroundColor: "var(--panel)",
                                    borderBottom:
                                        "1px solid var(--panel-border)",
                                }}
                            >
                                <th
                                    className="text-left px-4 py-3 font-medium"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Chave
                                </th>
                                <th
                                    className="text-left px-4 py-3 font-medium"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Valor
                                </th>
                                <th
                                    className="text-left px-4 py-3 font-medium"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Descrição
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {settings.map((s, i) => {
                                const val = getValue(s);
                                const isBool = s.value_type === "boolean";
                                const isSensitive =
                                    s.key?.toLowerCase().includes("password") ||
                                    s.key?.toLowerCase().includes("api_key") ||
                                    s.key?.toLowerCase().includes("key");
                                return (
                                    <tr
                                        key={i}
                                        style={{
                                            borderBottom:
                                                "1px solid var(--panel-border)",
                                        }}
                                    >
                                        <td className="px-4 py-3 font-medium">
                                            {s.key}
                                        </td>
                                        <td className="px-4 py-3">
                                            {isBool ? (
                                                <label className="flex items-center gap-2 cursor-pointer">
                                                    <input
                                                        type="checkbox"
                                                        checked={
                                                            val === "true" ||
                                                            val === true
                                                        }
                                                        onChange={(e) =>
                                                            setValue(
                                                                s,
                                                                e.target.checked
                                                                    ? "true"
                                                                    : "false",
                                                            )
                                                        }
                                                        className="rounded"
                                                    />
                                                    <span
                                                        style={{
                                                            color: "var(--muted-text)",
                                                        }}
                                                    >
                                                        {val === "true"
                                                            ? "Sim"
                                                            : "Não"}
                                                    </span>
                                                </label>
                                            ) : (
                                                <input
                                                    type={
                                                        isSensitive
                                                            ? "password"
                                                            : "text"
                                                    }
                                                    value={val}
                                                    onChange={(e) =>
                                                        setValue(
                                                            s,
                                                            e.target.value,
                                                        )
                                                    }
                                                    placeholder={
                                                        s.is_encrypted && !val
                                                            ? "••••••••"
                                                            : ""
                                                    }
                                                    className="cb-input font-mono text-xs w-full max-w-md"
                                                />
                                            )}
                                        </td>
                                        <td
                                            className="px-4 py-3"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            {s.description || "-"}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {/* API Test section – only on AI tab */}
            {/* ApiKeyTestSection is now embedded inside the notice for the 'ai' category */}

            {/* Tools & Agentes – only on AI tab */}
            {category === "ai" && !loading && (
                <div className="mt-6">
                    <hr
                        className="mb-6"
                        style={{ borderColor: "var(--card-border)" }}
                    />
                    <ToolsManager userRole="admin" />
                </div>
            )}

            {/* SMTP Diagnostic tip – only on SMTP tab, below table */}
            {isSmtpCategory && !loading && settings.length > 0 && (
                <div
                    className="rounded-lg border border-dashed p-3.5 flex items-center gap-3"
                    style={{
                        borderColor: "var(--card-border)",
                        backgroundColor: "var(--panel)",
                    }}
                >
                    <Mail
                        className="h-4 w-4 flex-shrink-0"
                        style={{ color: "var(--muted-text)" }}
                    />
                    <p
                        className="text-xs leading-relaxed"
                        style={{ color: "var(--muted-text)" }}
                    >
                        <strong>Dica:</strong> Após salvar, clique em{" "}
                        <strong>Testar Conexão</strong> para executar um
                        diagnóstico completo passo a passo e enviar um e-mail de
                        teste para validar toda a cadeia SMTP.
                    </p>
                </div>
            )}

            {/* SMTP Diagnostic Modal */}
            <SmtpDiagnosticModal
                isOpen={diagnosticOpen}
                onClose={() => setDiagnosticOpen(false)}
                smtpConfig={smtpConfig}
            />

            {/* YouTube Auth section - only on features tab (or any admin-related tab) */}
            {category === "features" && !loading && (
                <YoutubeAuthSection
                    addToast={(type, msg) => {
                        if (type === "success") setSuccessMsg?.(msg);
                        else setError?.(msg);
                    }}
                />
            )}
        </div>
    );
}

// ─── Shared UI Components ───────────────────────────────────────────

const ROLES = [
    { value: "admin", label: "Admin", icon: ShieldCheck, color: "#ef4444" },
    { value: "premium", label: "Premium", icon: Shield, color: "#f59e0b" },
    { value: "user", label: "User", icon: ShieldOff, color: "#6b7280" },
];

const PLANS = [
    { value: "free", label: "Free", color: "#6b7280" },
    { value: "starter", label: "Starter", color: "#3b82f6" },
    { value: "pro", label: "Pro", color: "#8b5cf6" },
    { value: "business", label: "Business", color: "#f59e0b" },
];

function Badge({ children, color }) {
    return (
        <span
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-full"
            style={{
                backgroundColor: `${color}20`,
                color,
                border: `1px solid ${color}40`,
            }}
        >
            {children}
        </span>
    );
}

function StatCard({ label, value, color }) {
    return (
        <div
            className="rounded-xl p-4 border"
            style={{
                backgroundColor: "var(--card-bg)",
                borderColor: "var(--card-border)",
            }}
        >
            <p
                className="text-xs font-medium mb-1"
                style={{ color: "var(--muted-text)" }}
            >
                {label}
            </p>
            <p
                className="text-2xl font-bold"
                style={{ color: color || "var(--text)" }}
            >
                {value}
            </p>
        </div>
    );
}

/**
 * Retorna o valor "efetivo" de um campo, considerando mudanças pendentes.
 * Se não houver mudança pendente, retorna o valor original.
 */
function effective(original, pending, field) {
    if (pending && field in pending) return pending[field];
    return original;
}

// ─── Status Sub-Tab Definitions ─────────────────────────────────────

const STATUS_TABS = [
    {
        id: "ativos",
        label: "Ativos",
        icon: UserCheck,
        color: "#22c55e",
        emptyIcon: Users,
        emptyText: "Nenhum usuário ativo encontrado.",
    },
    {
        id: "desativados",
        label: "Desativados",
        icon: UserX,
        color: "#f59e0b",
        emptyIcon: UserX,
        emptyText: "Nenhum usuário desativado.",
    },
    {
        id: "pendentes",
        label: "Aplicar/Adicionar",
        icon: UserPlus,
        color: "#f97316",
        emptyIcon: ShieldCheck,
        emptyText: "Nenhum usuário pendente no Clerk.",
    },
    {
        id: "templates",
        label: "Templates",
        icon: FileText,
        color: "#8b5cf6",
        emptyIcon: FileText,
        emptyText: "Nenhum template encontrado.",
    },
    {
        id: "excluidos",
        label: "Lixeira",
        icon: Trash2,
        color: "#ef4444",
        emptyIcon: Archive,
        emptyText: "A lixeira está vazia.",
    },
    {
        id: "grupos",
        label: "Grupos",
        icon: FolderTree,
        color: "#6366f1",
        emptyIcon: FolderTree,
        emptyText: "Nenhum grupo encontrado.",
    },
];

const TABS = [
    { id: "users", label: "Usuários", icon: Users },
    { id: "metrics", label: "Métricas", icon: LayoutDashboard },
    { id: "settings", label: "Configurações", icon: Settings },
];

// ─── Confirmation Dialog Component ──────────────────────────────────

function ConfirmDialog({
    open,
    title,
    message,
    confirmLabel,
    confirmColor,
    icon: Icon,
    loading: isLoading,
    onConfirm,
    onCancel,
}) {
    if (!open) return null;
    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 px-4"
            onClick={onCancel}
        >
            <div
                className="cb-panel w-full max-w-sm p-6"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center gap-3 mb-4">
                    {Icon && (
                        <Icon
                            className="h-6 w-6 flex-shrink-0"
                            style={{ color: confirmColor || "var(--accent)" }}
                        />
                    )}
                    <h3 className="text-lg font-semibold">{title}</h3>
                </div>
                <p
                    className="text-sm mb-6"
                    style={{ color: "var(--muted-text)" }}
                >
                    {message}
                </p>
                <div className="flex gap-2">
                    <button
                        onClick={onConfirm}
                        disabled={isLoading}
                        className="cb-btn flex-1 flex items-center justify-center gap-2 text-white font-medium"
                        style={{
                            backgroundColor: confirmColor || "var(--accent)",
                        }}
                    >
                        {isLoading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            Icon && <Icon className="h-4 w-4" />
                        )}
                        {confirmLabel || "Confirmar"}
                    </button>
                    <button
                        onClick={onCancel}
                        disabled={isLoading}
                        className="cb-btn flex-1"
                    >
                        Cancelar
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Main AdminDashboard Component ──────────────────────────────────

export default function AdminDashboard() {
    const [activeTab, setActiveTab] = useState("users");
    const [users, setUsers] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize] = useState(15);
    const [search, setSearch] = useState("");
    const [searchInput, setSearchInput] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [successMsg, setSuccessMsg] = useState("");
    const [isSyncing, setIsSyncing] = useState(false);

    // Status sub-tab for user management
    const [statusTab, setStatusTab] = useState("ativos");

    // Toast system
    const { toasts, removeToast, addToast } = useToast();
    const toast = buildToastMethods(addToast);

    // Mudanças pendentes: { [userId]: { role?, can_use_gemini?, , can_use_whisper? } }
    const [pending, setPending] = useState({});
    const [modelSelectionUser, setModelSelectionUser] = useState(null);
    const [savingIds, setSavingIds] = useState(new Set());

    // Action loading states for individual user actions
    const [actionLoadingIds, setActionLoadingIds] = useState(new Set());

    // Edit modal
    const [editUser, setEditUser] = useState(null);
    const [editForm, setEditForm] = useState({
        email: "",
        full_name: "",
        password: "",
    });
    const [editLoading, setEditLoading] = useState(false);

    // Create modal
    const [createOpen, setCreateOpen] = useState(false);
    const [createForm, setCreateForm] = useState({
        email: "",
        password: "",
        full_name: "",
        role: "user",
    });
    const [createLoading, setCreateLoading] = useState(false);

    // Usage stats modal
    const [statsUser, setStatsUser] = useState(null);
    const [stats, setStats] = useState(null);
    const [statsLoading, setStatsLoading] = useState(false);

    // Confirmation dialog
    const [confirmDialog, setConfirmDialog] = useState({ open: false });
    const [confirmLoading, setConfirmLoading] = useState(false);

    // Credits modals
    const [creditsUser, setCreditsUser] = useState(null);
    const [creditsInfo, setCreditsInfo] = useState(null);
    const [creditsLoading, setCreditsLoading] = useState(false);
    const [adjustOpen, setAdjustOpen] = useState(false);
    const [adjustUser, setAdjustUser] = useState(null);
    const [adjustForm, setAdjustForm] = useState({
        amount: "",
        description: "",
        type: "bonus",
    });
    const [adjustLoading, setAdjustLoading] = useState(false);
    const [templates, setTemplates] = useState([]);
    const [showTemplatesModal, setShowTemplatesModal] = useState(false);
    const [selectedUserForTemplates, setSelectedUserForTemplates] =
        useState(null);
    const [templateSaving, setTemplateSaving] = useState(false);

    // Clerk pending users (registered in Clerk but not yet imported)
    const fetchUsers = useCallback(async () => {
        if (statusTab === "grupos") return;
        setLoading(true);
        setError("");
        try {
            if (statusTab === "pendentes") {
                const res = await api.get("/admin/users/clerk-pending");
                setUsers(res.data.pending || []);
                setTotal(res.data.total || 0);
            } else {
                const params = { page, page_size: pageSize, status: statusTab };
                if (search) params.search = search;
                const res = await api.get("/admin/users", { params });
                setUsers(res.data.users || []);
                setTotal(res.data.total || 0);
            }
        } catch (e) {
            setError(getErrorMessage(e) || "Falha ao carregar usuários");
        } finally {
            setLoading(false);
        }
    }, [page, pageSize, search, statusTab]);

    useEffect(() => {
        fetchUsers();
    }, [fetchUsers]);

    // Auto-poll Clerk pending users every 30 s while on that tab
    useEffect(() => {
        if (statusTab !== "pendentes") return;
        const interval = setInterval(fetchUsers, 30000);
        return () => clearInterval(interval);
    }, [statusTab, fetchUsers]);

    useEffect(() => {
        api.get("/templates")
            .then((res) => setTemplates(res.data?.templates || []))
            .catch((e) => console.error("Erro ao carregar templates:", e));
    }, []);

    const openTemplatesModal = (user) => {
        setSelectedUserForTemplates(user);
        setShowTemplatesModal(true);
    };

    const saveUserTemplates = async (userId, allowedIds) => {
        setTemplateSaving(true);
        try {
            await api.put(`/admin/users/${userId}/permissions`, {
                allowed_templates: JSON.stringify(allowedIds),
            });
            toast.success("Permissões de templates atualizadas!");
            fetchUsers();
            setShowTemplatesModal(false);
        } catch (e) {
            toast.error(getErrorMessage(e) || "Falha ao salvar permissões");
        } finally {
            setTemplateSaving(false);
        }
    };

    // Limpar pending quando muda de página, busca ou aba de status
    useEffect(() => {
        setPending({});
    }, [page, search, statusTab]);

    // Reset page when status tab changes
    useEffect(() => {
        setPage(1);
    }, [statusTab]);

    // Auto-hide success message (legacy - kept for groups/settings tabs)
    useEffect(() => {
        if (!successMsg) return;
        const t = setTimeout(() => setSuccessMsg(""), 3000);
        return () => clearTimeout(t);
    }, [successMsg]);

    function handleSearch(e) {
        e.preventDefault();
        setPage(1);
        setSearch(searchInput.trim());
    }

    function clearSearch() {
        setSearchInput("");
        setSearch("");
        setPage(1);
    }

    // ─── Mudanças locais (pendentes) ──────────────────────────────────

    function setPendingField(userId, field, value) {
        setPending((prev) => {
            const userPending = { ...(prev[userId] || {}), [field]: value };
            return { ...prev, [userId]: userPending };
        });
    }

    function discardChanges(userId) {
        setPending((prev) => {
            const next = { ...prev };
            delete next[userId];
            return next;
        });
    }

    function hasChanges(userId) {
        return pending[userId] && Object.keys(pending[userId]).length > 0;
    }

    // ─── Salvar um usuário (role + permissions) ───────────────────────

    async function saveUser(userId) {
        const changes = pending[userId];
        if (!changes || Object.keys(changes).length === 0) return;

        setSavingIds((prev) => new Set([...prev, userId]));
        setError("");

        try {
            const promises = [];

            // Role change
            if ("role" in changes) {
                promises.push(
                    api.put(`/admin/users/${userId}/role`, {
                        role: changes.role,
                    }),
                );
            }

            // Plan change
            if ("plan" in changes) {
                promises.push(
                    api.put(`/admin/users/${userId}/plan`, {
                        plan: changes.plan,
                    }),
                );
            }

            // Permissions
            const permFields = [
                "can_use_gemini",
                "can_use_whisper",
                "can_export_html",
                "can_export_docx",
                "can_export_md",
                "can_export_pdf",
            ];
            const permChanges = {};
            permFields.forEach((f) => {
                if (f in changes) permChanges[f] = changes[f];
            });
            if (Object.keys(permChanges).length > 0) {
                promises.push(
                    api.put(`/admin/users/${userId}/permissions`, permChanges),
                );
            }

            await Promise.all(promises);

            discardChanges(userId);
            toast.success("Alterações salvas com sucesso!");
            fetchUsers();
        } catch (e) {
            toast.error(
                getErrorMessage(e) || "Falha ao salvar alterações",
            );
        } finally {
            setSavingIds((prev) => {
                const next = new Set(prev);
                next.delete(userId);
                return next;
            });
        }
    }

    // ─── User Status Actions ──────────────────────────────────────────

    function setActionLoading(userId, val) {
        setActionLoadingIds((prev) => {
            const next = new Set(prev);
            if (val) next.add(userId);
            else next.delete(userId);
            return next;
        });
    }

    async function handleDeactivateUser(user) {
        setConfirmDialog({
            open: true,
            title: "Desativar Usuário",
            message: `Tem certeza que deseja desativar "${user.full_name || user.email}"? O usuário não conseguirá fazer login.`,
            confirmLabel: "Desativar",
            confirmColor: "#f59e0b",
            icon: UserX,
            onConfirm: async () => {
                setConfirmLoading(true);
                try {
                    await api.post(`/admin/users/${user.id}/deactivate`);
                    toast.success(
                        `Usuário "${user.full_name || user.email}" desativado.`,
                        "Usuário Desativado",
                    );
                    setConfirmDialog({ open: false });
                    fetchUsers();
                } catch (e) {
                    toast.error(
                        getErrorMessage(e) ||
                            "Falha ao desativar usuário",
                    );
                } finally {
                    setConfirmLoading(false);
                }
            },
        });
    }

    async function handleReactivateUser(user) {
        setActionLoading(user.id, true);
        try {
            await api.post(`/admin/users/${user.id}/reactivate`);
            toast.success(
                `Usuário "${user.full_name || user.email}" reativado com sucesso!`,
                "Usuário Reativado",
            );
            fetchUsers();
        } catch (e) {
            toast.error(
                getErrorMessage(e) || "Falha ao reativar usuário",
            );
        } finally {
            setActionLoading(user.id, false);
        }
    }

    async function handleSoftDeleteUser(user) {
        setConfirmDialog({
            open: true,
            title: "Mover para Lixeira",
            message: `Tem certeza que deseja remover "${user.full_name || user.email}"? O usuário será movido para a lixeira e não aparecerá mais nas listagens.`,
            confirmLabel: "Mover para Lixeira",
            confirmColor: "#ef4444",
            icon: Trash2,
            onConfirm: async () => {
                setConfirmLoading(true);
                try {
                    await api.delete(`/admin/users/${user.id}`);
                    toast.success(
                        `Usuário "${user.full_name || user.email}" movido para a lixeira.`,
                        "Usuário Removido",
                    );
                    setConfirmDialog({ open: false });
                    fetchUsers();
                } catch (e) {
                    toast.error(
                        getErrorMessage(e) || "Falha ao remover usuário",
                    );
                } finally {
                    setConfirmLoading(false);
                }
            },
        });
    }

    async function handleRestoreUser(user) {
        setActionLoading(user.id, true);
        try {
            await api.post(`/admin/users/${user.id}/restore`);
            toast.success(
                `Usuário "${user.full_name || user.email}" restaurado com sucesso!`,
                "Usuário Restaurado",
            );
            fetchUsers();
        } catch (e) {
            toast.error(
                getErrorMessage(e) || "Falha ao restaurar usuário",
            );
        } finally {
            setActionLoading(user.id, false);
        }
    }

    // ─── Credits Management ──────────────────────────────────────────

    async function openCreditsDetail(user) {
        setCreditsUser(user);
        setCreditsLoading(true);
        try {
            const res = await api.get(`/admin/users/${user.id}/credits`);
            setCreditsInfo(res.data);
        } catch (e) {
            toast.error(getErrorMessage(e) || "Falha ao carregar créditos");
            setCreditsUser(null);
        } finally {
            setCreditsLoading(false);
        }
    }

    function openAdjustCredits(user) {
        setAdjustUser(user);
        setAdjustForm({ amount: "", description: "", type: "bonus" });
        setAdjustOpen(true);
    }

    async function submitAdjustCredits(e) {
        e.preventDefault();
        if (!adjustUser) return;
        const amount = parseInt(adjustForm.amount, 10);
        if (isNaN(amount) || amount === 0) {
            toast.error("Informe um valor válido (diferente de zero)");
            return;
        }
        if (!adjustForm.description.trim()) {
            toast.error("Informe uma descrição");
            return;
        }
        setAdjustLoading(true);
        try {
            await api.post(`/admin/users/${adjustUser.id}/credits`, {
                amount,
                description: adjustForm.description.trim(),
                type: adjustForm.type,
            });
            toast.success(
                `Créditos ajustados para "${adjustUser.full_name || adjustUser.email}"`,
            );
            setAdjustOpen(false);
            setAdjustUser(null);
            fetchUsers();
            // Refresh credits detail if open
            if (creditsUser && creditsUser.id === adjustUser.id) {
                openCreditsDetail(adjustUser);
            }
        } catch (e) {
            toast.error(getErrorMessage(e) || "Falha ao ajustar créditos");
        } finally {
            setAdjustLoading(false);
        }
    }

    // ─── Edit User (modal)───────────────────────────────────────────

    function openEdit(user) {
        setEditUser(user);
        setEditForm({
            email: user.email,
            full_name: user.full_name || "",
            password: "",
        });
    }

    async function saveEdit(e) {
        e.preventDefault();
        setEditLoading(true);
        setError("");
        try {
            const body = {};
            if (editForm.email && editForm.email !== editUser.email)
                body.email = editForm.email;
            if (editForm.full_name !== (editUser.full_name || ""))
                body.full_name = editForm.full_name;
            if (editForm.password) body.password = editForm.password;
            if (Object.keys(body).length > 0) {
                await api.put(`/admin/users/${editUser.id}`, body);
            }
            setEditUser(null);
            toast.success("Usuário atualizado com sucesso!");
            fetchUsers();
        } catch (e) {
            toast.error(getErrorMessage(e) || "Falha ao salvar");
        } finally {
            setEditLoading(false);
        }
    }

    // ─── Create User ──────────────────────────────────────────────────

    async function handleCreate(e) {
        e.preventDefault();
        setCreateLoading(true);
        setError("");
        try {
            await api.post("/admin/users", createForm);
            setCreateOpen(false);
            setCreateForm({
                email: "",
                password: "",
                full_name: "",
                role: "user",
            });
            toast.success("Usuário criado com sucesso!", "Novo Usuário");
            fetchUsers();
        } catch (e) {
            toast.error(getErrorMessage(e) || "Falha ao criar usuário");
        } finally {
            setCreateLoading(false);
        }
    }
    async function handleSyncClerk() {
        if (isSyncing) return;
        setIsSyncing(true);
        try {
            const response = await api.post("/admin/users/sync");
            toast.success(
                `Sincronização concluída: ${response.data.synced} usuários importados e ${response.data.linked} vinculados.`,
                "Clerk Sync",
            );
            fetchUsers();
        } catch (err) {
            toast.error(
                "Erro na sincronização: " +
                    (getErrorMessage(err) || err.message),
            );
        } finally {
            setIsSyncing(false);
        }
    }

    async function handleApproveClerkUser(user) {
        setActionLoadingIds((prev) => new Set([...prev, user.clerk_id]));
        setError("");
        try {
            // Register user in local DB (backend will auto-link via Clerk ID/email)
            await api.post("/admin/users", {
                email: user.email,
                full_name: user.full_name,
                password:
                    "clerk_managed_" + Math.random().toString(36).substring(7),
                role: "user",
            });
            toast.success(
                `${user.full_name || user.email} validado e adicionado.`,
                "Sucesso",
            );
            fetchUsers();
        } catch (e) {
            toast.error(
                getErrorMessage(e) || "Falha ao validar usuário",
            );
        } finally {
            setActionLoadingIds((prev) => {
                const next = new Set(prev);
                next.delete(user.clerk_id);
                return next;
            });
        }
    }

    // ─── Usage Stats ──────────────────────────────────────────────────

    async function openStats(user) {
        setStatsUser(user);
        setStatsLoading(true);
        setStats(null);
        try {
            const res = await api.get(`/admin/users/${user.id}/usage-stats`);
            setStats(res.data);
        } catch (e) {
            toast.error(
                getErrorMessage(e) || "Falha ao carregar estatísticas",
            );
        } finally {
            setStatsLoading(false);
        }
    }

    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const hasPendingChanges = Object.keys(pending).length > 0;
    const currentStatusTab =
        STATUS_TABS.find((t) => t.id === statusTab) || STATUS_TABS[0];

    // ─── Render Helper: Status Badge ─────────────────────────────────

    function renderStatusBadge(user) {
        const status =
            user.status ||
            (user.deleted_at
                ? "excluido"
                : user.is_active
                  ? "ativo"
                  : "desativado");
        const config = {
            ativo: { color: "#22c55e", label: "Ativo" },
            desativado: { color: "#f59e0b", label: "Desativado" },
            excluido: { color: "#ef4444", label: "Excluído" },
        };
        const c = config[status] || config.ativo;
        return <Badge color={c.color}>{c.label}</Badge>;
    }

    // ─── Render Helper: Action Buttons per Status Tab ────────────────

    function renderUserActions(user) {
        const isActionLoading = actionLoadingIds.has(user.id);
        const dirty = hasChanges(user.id);
        const saving = savingIds.has(user.id);

        if (statusTab === "ativos") {
            return (
                <div className="flex items-center justify-end gap-1">
                    {dirty && (
                        <>
                            <button
                                onClick={() => saveUser(user.id)}
                                disabled={saving}
                                className="cb-btn cb-btn-primary p-1.5 flex items-center gap-1"
                                title="Salvar alterações"
                            >
                                {saving ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <Save className="h-4 w-4" />
                                )}
                                <span className="text-xs hidden sm:inline">
                                    Salvar
                                </span>
                            </button>
                            <button
                                onClick={() => discardChanges(user.id)}
                                className="cb-btn p-1.5"
                                title="Descartar alterações"
                            >
                                <Undo2 className="h-4 w-4" />
                            </button>
                        </>
                    )}
                    <button
                        onClick={() => openEdit(user)}
                        className="cb-btn p-1.5"
                        title="Editar"
                    >
                        <Edit3 className="h-4 w-4" />
                    </button>
                    <button
                        onClick={() => openStats(user)}
                        className="cb-btn p-1.5"
                        title="Estatísticas de uso"
                    >
                        <BarChart3 className="h-4 w-4" />
                    </button>
                    <button
                        onClick={() => handleDeactivateUser(user)}
                        className="cb-btn p-1.5"
                        title="Desativar usuário"
                        style={{ color: "#f59e0b" }}
                    >
                        <UserX className="h-4 w-4" />
                    </button>
                    <button
                        onClick={() => handleSoftDeleteUser(user)}
                        className="cb-btn p-1.5"
                        title="Mover para lixeira"
                        style={{ color: "#ef4444" }}
                    >
                        <Trash2 className="h-4 w-4" />
                    </button>
                </div>
            );
        }

        if (statusTab === "desativados") {
            return (
                <div className="flex items-center justify-end gap-1">
                    <button
                        onClick={() => handleReactivateUser(user)}
                        disabled={isActionLoading}
                        className="cb-btn p-1.5 flex items-center gap-1"
                        title="Reativar usuário"
                        style={{ color: "#22c55e" }}
                    >
                        {isActionLoading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <UserCheck className="h-4 w-4" />
                        )}
                        <span className="text-xs hidden sm:inline">
                            Reativar
                        </span>
                    </button>
                    <button
                        onClick={() => openEdit(user)}
                        className="cb-btn p-1.5"
                        title="Editar"
                    >
                        <Edit3 className="h-4 w-4" />
                    </button>
                    <button
                        onClick={() => openStats(user)}
                        className="cb-btn p-1.5"
                        title="Estatísticas"
                    >
                        <BarChart3 className="h-4 w-4" />
                    </button>
                    <button
                        onClick={() => handleSoftDeleteUser(user)}
                        className="cb-btn p-1.5"
                        title="Mover para lixeira"
                        style={{ color: "#ef4444" }}
                    >
                        <Trash2 className="h-4 w-4" />
                    </button>
                </div>
            );
        }

        if (statusTab === "excluidos") {
            return (
                <div className="flex items-center justify-end gap-1">
                    <button
                        onClick={() => handleRestoreUser(user)}
                        disabled={isActionLoading}
                        className="cb-btn p-1.5 flex items-center gap-1"
                        title="Restaurar usuário"
                        style={{ color: "#22c55e" }}
                    >
                        {isActionLoading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <RotateCcw className="h-4 w-4" />
                        )}
                        <span className="text-xs hidden sm:inline">
                            Restaurar
                        </span>
                    </button>
                    <button
                        onClick={() => openStats(user)}
                        className="cb-btn p-1.5"
                        title="Estatísticas"
                    >
                        <BarChart3 className="h-4 w-4" />
                    </button>
                </div>
            );
        }

        return null;
    }

    // ─── Render Helper: Table Columns per Status Tab ─────────────────

    function renderTableHeaders() {
        if (statusTab === "pendentes") {
            return (
                <tr
                    style={{
                        backgroundColor: "var(--panel)",
                        borderBottom: "1px solid var(--panel-border)",
                    }}
                >
                    <th
                        className="text-left px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Usuário (Clerk)
                    </th>
                    <th
                        className="text-left px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Username
                    </th>
                    <th
                        className="text-center px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Criado em
                    </th>
                    <th
                        className="text-center px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Último Login
                    </th>
                    <th
                        className="text-right px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Ações
                    </th>
                </tr>
            );
        }

        if (statusTab === "excluidos") {
            return (
                <tr
                    style={{
                        backgroundColor: "var(--panel)",
                        borderBottom: "1px solid var(--panel-border)",
                    }}
                >
                    <th
                        className="text-left px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Usuário
                    </th>
                    <th
                        className="text-left px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Role
                    </th>
                    <th
                        className="text-center px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Status
                    </th>
                    <th
                        className="text-center px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Excluído em
                    </th>
                    <th
                        className="text-right px-4 py-3 font-medium"
                        style={{ color: "var(--muted-text)" }}
                    >
                        Ações
                    </th>
                </tr>
            );
        }

        return (
            <tr
                style={{
                    backgroundColor: "var(--panel)",
                    borderBottom: "1px solid var(--panel-border)",
                }}
            >
                <th
                    className="text-left px-4 py-3 font-medium"
                    style={{ color: "var(--muted-text)" }}
                >
                    Usuário
                </th>
                <th
                    className="text-left px-4 py-3 font-medium"
                    style={{ color: "var(--muted-text)" }}
                >
                    Role
                </th>
                <th
                    className="text-left px-4 py-3 font-medium"
                    style={{ color: "var(--muted-text)" }}
                >
                    Plano
                </th>
                <th
                    className="text-center px-4 py-3 font-medium"
                    style={{ color: "var(--muted-text)" }}
                >
                    Créditos
                </th>
                <th
                    className="text-center px-4 py-3 font-medium"
                    style={{ color: "var(--muted-text)" }}
                >
                    Modelos IA
                </th>
                <th
                    className="text-center px-4 py-3 font-medium"
                    style={{ color: "var(--muted-text)" }}
                >
                    Status
                </th>
                <th
                    className="text-right px-4 py-3 font-medium"
                    style={{ color: "var(--muted-text)" }}
                >
                    Ações
                </th>
            </tr>
        );
    }

    function renderUserRow(u) {
        const p = pending[u.id] || {};
        const dirty = hasChanges(u.id);
        const perms = u.permissions || {};

        if (statusTab === "pendentes") {
            return (
                <tr
                    key={u.clerk_id}
                    className="transition-all"
                    style={{
                        borderBottom: "1px solid var(--panel-border)",
                    }}
                >
                    <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                            {u.image_url ? (
                                <img
                                    src={u.image_url}
                                    alt={u.full_name}
                                    className="h-8 w-8 rounded-full border"
                                    style={{
                                        borderColor: "var(--panel-border)",
                                    }}
                                />
                            ) : (
                                <div
                                    className="h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold"
                                    style={{
                                        backgroundColor: "rgba(0,210,180,0.1)",
                                        color: "var(--accent)",
                                    }}
                                >
                                    {(u.full_name || u.email || "?")
                                        .charAt(0)
                                        .toUpperCase()}
                                </div>
                            )}
                            <div className="cb-no-select">
                                <p
                                    className="font-medium"
                                    style={{ color: "var(--text)" }}
                                >
                                    {u.full_name || "-"}
                                </p>
                                <p
                                    className="text-xs"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    {u.email}
                                </p>
                            </div>
                        </div>
                    </td>
                    <td
                        className="px-4 py-3 text-sm"
                        style={{ color: "var(--muted-text)" }}
                    >
                        {u.username || "-"}
                    </td>
                    <td
                        className="px-4 py-3 text-center text-xs"
                        style={{ color: "var(--muted-text)" }}
                    >
                        {relativeTime(u.created_at)}
                    </td>
                    <td
                        className="px-4 py-3 text-center text-xs"
                        style={{ color: "var(--muted-text)" }}
                    >
                        {relativeTime(u.last_sign_in_at)}
                    </td>
                    <td className="px-4 py-3">{renderUserActions(u)}</td>
                </tr>
            );
        }

        if (statusTab === "excluidos") {
            return (
                <tr
                    key={u.id}
                    className="transition-all"
                    style={{
                        borderBottom: "1px solid var(--panel-border)",
                        opacity: 0.7,
                    }}
                >
                    <td className="px-4 py-3">
                        <div className="cb-no-select">
                            <p
                                className="font-medium"
                                style={{ color: "var(--text)" }}
                            >
                                {u.full_name || "-"}
                            </p>
                            <p
                                className="text-xs"
                                style={{ color: "var(--muted-text)" }}
                            >
                                {u.email}
                            </p>
                        </div>
                    </td>
                    <td className="px-4 py-3">
                        {(() => {
                            const roleInfo = ROLES.find(
                                (r) => r.value === u.role,
                            );
                            return (
                                <Badge color={roleInfo?.color || "#6b7280"}>
                                    {roleInfo?.label || u.role}
                                </Badge>
                            );
                        })()}
                    </td>
                    <td className="px-4 py-3 text-center">
                        {renderStatusBadge(u)}
                    </td>
                    <td className="px-4 py-3 text-center">
                        <span
                            className="text-xs"
                            style={{ color: "var(--muted-text)" }}
                        >
                            {u.deleted_at
                                ? new Date(u.deleted_at).toLocaleString(
                                      "pt-BR",
                                      {
                                          day: "2-digit",
                                          month: "2-digit",
                                          year: "numeric",
                                          hour: "2-digit",
                                          minute: "2-digit",
                                      },
                                  )
                                : "-"}
                        </span>
                    </td>
                    <td className="px-4 py-3">{renderUserActions(u)}</td>
                </tr>
            );
        }

        // Active and Deactivated tabs have the full row with editable fields
        const effRole = effective(u.role, p, "role");
        const effGemini = effective(perms.can_use_gemini, p, "can_use_gemini");
        const effWhisper = effective(
            perms.can_use_whisper,
            p,
            "can_use_whisper",
        );
        const isActive = statusTab === "ativos";

        return (
            <tr
                key={u.id}
                className="transition-all"
                style={{
                    borderBottom: "1px solid var(--panel-border)",
                    opacity: isActive ? 1 : 0.65,
                    backgroundColor: dirty
                        ? "var(--accent-bg, rgba(0,200,150,0.04))"
                        : "transparent",
                }}
            >
                {/* User info */}
                <td className="px-4 py-3">
                    <div className="cb-no-select">
                        <p
                            className="font-medium"
                            style={{ color: "var(--text)" }}
                        >
                            {u.full_name || "-"}
                        </p>
                        <p
                            className="text-xs"
                            style={{ color: "var(--muted-text)" }}
                        >
                            {u.email}
                        </p>
                    </div>
                </td>

                {/* Role dropdown (local) */}
                <td className="px-4 py-3">
                    {statusTab === "ativos" ? (
                        <select
                            value={effRole}
                            onChange={(e) => {
                                const newRole = e.target.value;
                                if (newRole === u.role) {
                                    setPending((prev) => {
                                        const next = { ...(prev[u.id] || {}) };
                                        delete next.role;
                                        if (Object.keys(next).length === 0) {
                                            const all = { ...prev };
                                            delete all[u.id];
                                            return all;
                                        }
                                        return { ...prev, [u.id]: next };
                                    });
                                } else {
                                    setPendingField(u.id, "role", newRole);
                                }
                            }}
                            className="cb-input text-xs py-1 px-2 rounded cursor-pointer"
                            style={{
                                minWidth: "100px",
                                borderColor:
                                    "role" in p ? "var(--accent)" : undefined,
                            }}
                        >
                            {ROLES.map((r) => (
                                <option key={r.value} value={r.value}>
                                    {r.label}
                                </option>
                            ))}
                        </select>
                    ) : (
                        (() => {
                            const roleInfo = ROLES.find(
                                (r) => r.value === u.role,
                            );
                            return (
                                <Badge color={roleInfo?.color || "#6b7280"}>
                                    {roleInfo?.label || u.role}
                                </Badge>
                            );
                        })()
                    )}
                </td>

                {/* Plan dropdown */}
                <td className="px-4 py-3">
                    {statusTab === "ativos" ? (
                        <select
                            value={effective(u.plan || "free", p, "plan")}
                            onChange={(e) => {
                                const newPlan = e.target.value;
                                if (newPlan === (u.plan || "free")) {
                                    setPending((prev) => {
                                        const next = { ...(prev[u.id] || {}) };
                                        delete next.plan;
                                        if (Object.keys(next).length === 0) {
                                            const all = { ...prev };
                                            delete all[u.id];
                                            return all;
                                        }
                                        return { ...prev, [u.id]: next };
                                    });
                                } else {
                                    setPendingField(u.id, "plan", newPlan);
                                }
                            }}
                            className="cb-input text-xs py-1 px-2 rounded cursor-pointer"
                            style={{
                                minWidth: "90px",
                                borderColor:
                                    "plan" in p ? "var(--accent)" : undefined,
                            }}
                        >
                            {PLANS.map((pl) => (
                                <option key={pl.value} value={pl.value}>
                                    {pl.label}
                                </option>
                            ))}
                        </select>
                    ) : (
                        (() => {
                            const planInfo = PLANS.find(
                                (pl) => pl.value === (u.plan || "free"),
                            );
                            return (
                                <Badge color={planInfo?.color || "#6b7280"}>
                                    {planInfo?.label || u.plan || "Free"}
                                </Badge>
                            );
                        })()
                    )}
                </td>

                {/* Credits */}
                <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                        <button
                            onClick={() => openCreditsDetail(u)}
                            className="text-xs font-medium px-2 py-1 rounded hover:opacity-80 transition-opacity"
                            style={{
                                color: "#22c55e",
                                backgroundColor: "rgba(34, 197, 94, 0.1)",
                                border: "1px solid rgba(34, 197, 94, 0.2)",
                            }}
                            title="Ver detalhes de créditos"
                        >
                            {u.credit_account?.credits_balance ?? "—"}
                        </button>
                        {statusTab === "ativos" && (
                            <button
                                onClick={() => openAdjustCredits(u)}
                                className="p-1 rounded hover:opacity-80 transition-opacity"
                                style={{ color: "var(--accent)" }}
                                title="Ajustar créditos"
                            >
                                <DollarSign className="h-3.5 w-3.5" />
                            </button>
                        )}
                    </div>
                </td>

                {/* Permission toggles (consolidated) */}
                <td className="px-4 py-3 text-center">
                    <button
                        onClick={() => setModelSelectionUser(u)}
                        className="cb-btn text-xs px-2 py-1 flex items-center gap-1.5 mx-auto transition-all"
                        style={{
                            color: "var(--accent)",
                            backgroundColor: "rgba(0, 210, 180, 0.05)",
                            borderColor: "rgba(0, 210, 180, 0.2)",
                        }}
                        title="Configurar acesso aos modelos"
                    >
                        <Settings className="h-3.5 w-3.5" />
                        <span>Configurar</span>
                        {(("can_use_gemini" in p) || ("can_use_whisper" in p) || 
                          ("can_export_html" in p) || ("can_export_docx" in p) || ("can_export_md" in p) || ("can_export_pdf" in p)) && (
                            <div className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                        )}
                    </button>
                </td>


                {/* Status badge */}
                <td className="px-4 py-3 text-center">
                    {renderStatusBadge(u)}
                </td>

                {/* Actions */}
                <td className="px-4 py-3">{renderUserActions(u)}</td>
            </tr>
        );
    }

    return (
        <div className="cb-app-shell admin-shell min-h-screen" style={{ background: "transparent", color: "var(--text)", position: "relative" }}>
            <LoginBackground />

            {/* Toast Notifications */}
            <ToastContainer toasts={toasts} removeToast={removeToast} />

            {/* Model Selection Modal */}
            <ModelSelectionModal
                user={modelSelectionUser}
                onClose={() => setModelSelectionUser(null)}
                pending={pending}
                setPending={setPending}
                setPendingField={setPendingField}
            />

            {/* Confirmation Dialog */}
            <ConfirmDialog
                open={confirmDialog.open}
                title={confirmDialog.title}
                message={confirmDialog.message}
                confirmLabel={confirmDialog.confirmLabel}
                confirmColor={confirmDialog.confirmColor}
                icon={confirmDialog.icon}
                loading={confirmLoading}
                onConfirm={
                    confirmDialog.onConfirm ||
                    (() => setConfirmDialog({ open: false }))
                }
                onCancel={() => {
                    setConfirmDialog({ open: false });
                    setConfirmLoading(false);
                }}
            />

            {/* Header */}
            <header
                className="admin-header"
            >
                <div className="admin-header-inner">
                    <div className="flex items-center gap-4">
                        <Link
                            to="/"
                            className="cb-btn p-2"
                            title="Voltar ao Dashboard"
                        >
                            <ArrowLeft className="h-4 w-4" />
                        </Link>
                        <div className="flex items-center gap-2">
                            <Shield
                                className="h-5 w-5"
                                style={{ color: "var(--accent)" }}
                            />
                            <h1 className="text-xl font-semibold">
                                Painel Admin
                            </h1>
                        </div>
                        {hasPendingChanges && (
                            <span
                                className="text-xs px-2 py-0.5 rounded-full font-medium animate-pulse"
                                style={{
                                    backgroundColor: "var(--accent)",
                                    color: "#fff",
                                }}
                            >
                                Alterações pendentes
                            </span>
                        )}
                    </div>
                    {activeTab === "users" && statusTab !== "grupos" && (
                        <div className="flex gap-2">
                            <button
                                onClick={handleSyncClerk}
                                disabled={isSyncing}
                                className="cb-btn flex items-center gap-2"
                                style={{
                                    backgroundColor: "rgba(255,255,255,0.05)",
                                    borderColor: "var(--panel-border)",
                                    color: "var(--text-dim)",
                                }}
                            >
                                <RefreshCw
                                    className={`h-4 w-4 ${isSyncing ? "animate-spin" : ""}`}
                                />
                                {isSyncing
                                    ? "Sincronizando..."
                                    : "Sincronizar Clerk"}
                            </button>
                            <button
                                onClick={() => setCreateOpen(true)}
                                className="cb-btn cb-btn-primary flex items-center gap-2"
                            >
                                <UserPlus className="h-4 w-4" />
                                Novo Usuário
                            </button>
                        </div>
                    )}
                </div>
            </header>

            {/* Tab navigation */}
            <div
                className="admin-top-tabs"
            >
                {TABS.map(({ id, label, icon: Icon }) => (
                    <button
                        key={id}
                        onClick={() => setActiveTab(id)}
                        className={`admin-top-tab ${activeTab === id ? "is-active" : ""}`}
                    >
                        <Icon className="h-4 w-4" />
                        {label}
                    </button>
                ))}
            </div>

            <main className="mx-auto max-w-7xl px-6 py-8 space-y-6 min-h-[calc(100vh-120px)] rounded-3xl mt-4 mb-8" style={{ backgroundColor: "var(--glass-bg)", backdropFilter: "blur(8px)" }}>
                {/* Success message (legacy for groups/settings) */}
                {successMsg && (
                    <div
                        className="rounded-lg border p-3 text-sm flex items-center gap-2"
                        style={{
                            borderColor: "#22c55e",
                            backgroundColor: "#22c55e15",
                            color: "#22c55e",
                        }}
                    >
                        <Check className="h-4 w-4 flex-shrink-0" />
                        {successMsg}
                    </div>
                )}

                {/* Error */}
                {error && (
                    <div
                        className="rounded-lg border p-3 text-sm flex items-center gap-2"
                        style={{
                            borderColor: "var(--danger)",
                            backgroundColor: "var(--danger-bg)",
                            color: "var(--danger)",
                        }}
                    >
                        <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                        {getErrorMessage(error)}
                        <button
                            onClick={() => setError("")}
                            className="ml-auto"
                        >
                            <X className="h-4 w-4" />
                        </button>
                    </div>
                )}

                {/* Tab: Users */}
                {activeTab === "users" && (
                    <>
                        {/* ── Status Sub-Tabs ──────────────────────────────────────── */}
                        <div
                            className="flex items-center gap-1 rounded-lg p-1"
                            style={{
                                backgroundColor: "var(--glass-bg)",
                                border: "1px solid var(--panel-border)",
                                backdropFilter: "blur(4px)",
                            }}
                        >
                            {STATUS_TABS.map(
                                ({ id, label, icon: SIcon, color }) => {
                                    const isSelected = statusTab === id;
                                    return (
                                        <button
                                            key={id}
                                            onClick={() => setStatusTab(id)}
                                            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all"
                                            style={{
                                                backgroundColor: isSelected
                                                    ? `${color}18`
                                                    : "transparent",
                                                color: isSelected
                                                    ? color
                                                    : "var(--muted-text)",
                                                border: isSelected
                                                    ? `1px solid ${color}40`
                                                    : "1px solid transparent",
                                            }}
                                        >
                                            <SIcon className="h-4 w-4" />
                                            {label}
                                        </button>
                                    );
                                },
                            )}
                        </div>

                        {/* ── Groups (inline) ──────────────────────────────────────── */}
                        {statusTab === "grupos" && (
                            <GroupsTab
                                setError={setError}
                                setSuccessMsg={setSuccessMsg}
                            />
                        )}

                        {/* ── Search ───────────────────────────────────────────────── */}
                        {statusTab !== "grupos" && statusTab !== "templates" && (
                            <form
                                onSubmit={handleSearch}
                                className="flex gap-2"
                            >
                                <div className="relative flex-1">
                                    <Search
                                        className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4"
                                        style={{ color: "var(--muted-text)" }}
                                    />
                                    <input
                                        type="text"
                                        value={searchInput}
                                        onChange={(e) =>
                                            setSearchInput(e.target.value)
                                        }
                                        placeholder="Buscar por email ou nome..."
                                        className="cb-input pl-10 w-full"
                                    />
                                </div>
                                <button
                                    type="submit"
                                    className="cb-btn cb-btn-primary"
                                >
                                    Buscar
                                </button>
                                {search && (
                                    <button
                                        type="button"
                                        onClick={clearSearch}
                                        className="cb-btn flex items-center gap-1"
                                    >
                                        <X className="h-4 w-4" /> Limpar
                                    </button>
                                )}
                            </form>
                        )}

                        {/* Summary */}
                        {statusTab !== "grupos" && statusTab !== "templates" && (
                            <div
                                className="flex items-center justify-between text-sm"
                                style={{ color: "var(--muted-text)" }}
                            >
                                <span>
                                    {total} usuário{total !== 1 ? "s" : ""}{" "}
                                    {statusTab === "ativos" &&
                                        "ativo" + (total !== 1 ? "s" : "")}
                                    {statusTab === "desativados" &&
                                        "desativado" + (total !== 1 ? "s" : "")}
                                    {statusTab === "excluidos" && "na lixeira"}
                                </span>
                                <span>
                                    Página {page} de {totalPages}
                                </span>
                            </div>
                        )}

                        {/* User Table */}
                        {statusTab !== "grupos" && statusTab !== "templates" && (
                            <div
                                className="rounded-xl border overflow-hidden"
                                style={{
                                    borderColor: "var(--card-border)",
                                    backgroundColor: "var(--card-bg)",
                                }}
                            >
                                {loading ? (
                                    <div className="flex items-center justify-center py-16">
                                        <Loader2
                                            className="h-6 w-6 animate-spin"
                                            style={{ color: "var(--accent)" }}
                                        />
                                    </div>
                                ) : users.length === 0 ? (
                                    <div
                                        className="text-center py-16"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        {(() => {
                                            const EmptyIcon =
                                                currentStatusTab.emptyIcon ||
                                                Users;
                                            return (
                                                <EmptyIcon className="h-10 w-10 mx-auto mb-3 opacity-40" />
                                            );
                                        })()}
                                        <p>{currentStatusTab.emptyText}</p>
                                        {statusTab !== "ativos" && (
                                            <p className="text-xs mt-2 opacity-60">
                                                {statusTab === "desativados" &&
                                                    "Usuários desativados aparecerão aqui."}
                                                {statusTab === "excluidos" &&
                                                    "Usuários removidos aparecerão aqui e podem ser restaurados."}
                                            </p>
                                        )}
                                    </div>
                                ) : (
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm">
                                            <thead>
                                                {renderTableHeaders()}
                                            </thead>
                                            <tbody>
                                                {users.map((u) =>
                                                    renderUserRow(u),
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Pagination */}
                        {statusTab !== "grupos" && statusTab !== "templates" && totalPages > 1 && (
                            <div className="flex items-center justify-center gap-2">
                                <button
                                    onClick={() =>
                                        setPage((p) => Math.max(1, p - 1))
                                    }
                                    disabled={page <= 1}
                                    className="cb-btn p-2"
                                >
                                    <ChevronLeft className="h-4 w-4" />
                                </button>
                                {Array.from(
                                    { length: Math.min(5, totalPages) },
                                    (_, i) => {
                                        let p;
                                        if (totalPages <= 5) {
                                            p = i + 1;
                                        } else if (page <= 3) {
                                            p = i + 1;
                                        } else if (page >= totalPages - 2) {
                                            p = totalPages - 4 + i;
                                        } else {
                                            p = page - 2 + i;
                                        }
                                        return (
                                            <button
                                                key={p}
                                                onClick={() => setPage(p)}
                                                className="cb-btn px-3 py-1.5 text-sm"
                                                style={
                                                    p === page
                                                        ? {
                                                              backgroundColor:
                                                                  "var(--accent)",
                                                              color: "#fff",
                                                          }
                                                        : {}
                                                }
                                            >
                                                {p}
                                            </button>
                                        );
                                    },
                                )}
                                <button
                                    onClick={() =>
                                        setPage((p) =>
                                            Math.min(totalPages, p + 1),
                                        )
                                    }
                                    disabled={page >= totalPages}
                                    className="cb-btn p-2"
                                >
                                    <ChevronRight className="h-4 w-4" />
                                </button>
                            </div>
                        )}
                    </>
                )}

                {/* Tab: Metrics */}
                {activeTab === "metrics" && <MetricsTab StatCard={StatCard} />}

                {/* Tab: Templates */}
                {activeTab === "users" && statusTab === "templates" && (
                    <TemplatesTab
                        users={users}
                        templates={templates}
                        setTemplates={setTemplates}
                        toast={toast}
                        openTemplatesModal={openTemplatesModal}
                        saveUserTemplates={saveUserTemplates}
                        templateSaving={templateSaving}
                    />
                )}

                {/* Tab: Settings */}
                {activeTab === "settings" && (
                    <SettingsTab
                        setError={setError}
                        setSuccessMsg={setSuccessMsg}
                    />
                )}
            </main>

            {/* ── Credits Detail Modal ──────────────────────────────────── */}
            {creditsUser && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                    onClick={() => {
                        setCreditsUser(null);
                        setCreditsInfo(null);
                    }}
                >
                    <div
                        className="rounded-xl border p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto shadow-2xl"
                        style={{
                            backgroundColor: "var(--panel)",
                            borderColor: "var(--panel-border)",
                        }}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-4">
                            <h3
                                className="text-lg font-semibold flex items-center gap-2"
                                style={{ color: "var(--text)" }}
                            >
                                <Coins
                                    className="h-5 w-5"
                                    style={{ color: "#22c55e" }}
                                />
                                Créditos —{" "}
                                {creditsUser.full_name || creditsUser.email}
                            </h3>
                            <button
                                onClick={() => {
                                    setCreditsUser(null);
                                    setCreditsInfo(null);
                                }}
                                className="cb-btn p-1"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>

                        {creditsLoading ? (
                            <div className="flex justify-center py-8">
                                <Loader2
                                    className="h-6 w-6 animate-spin"
                                    style={{ color: "var(--accent)" }}
                                />
                            </div>
                        ) : creditsInfo ? (
                            <>
                                <div className="grid grid-cols-3 gap-3 mb-4">
                                    <div
                                        className="rounded-lg p-3 text-center"
                                        style={{
                                            backgroundColor: "var(--card-bg)",
                                            border: "1px solid var(--card-border)",
                                        }}
                                    >
                                        <p
                                            className="text-xs"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Saldo
                                        </p>
                                        <p
                                            className="text-xl font-bold"
                                            style={{ color: "#22c55e" }}
                                        >
                                            {creditsInfo.credits_balance}
                                        </p>
                                    </div>
                                    <div
                                        className="rounded-lg p-3 text-center"
                                        style={{
                                            backgroundColor: "var(--card-bg)",
                                            border: "1px solid var(--card-border)",
                                        }}
                                    >
                                        <p
                                            className="text-xs"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Comprados
                                        </p>
                                        <p
                                            className="text-xl font-bold"
                                            style={{ color: "#3b82f6" }}
                                        >
                                            {
                                                creditsInfo.total_credits_purchased
                                            }
                                        </p>
                                    </div>
                                    <div
                                        className="rounded-lg p-3 text-center"
                                        style={{
                                            backgroundColor: "var(--card-bg)",
                                            border: "1px solid var(--card-border)",
                                        }}
                                    >
                                        <p
                                            className="text-xs"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Usados
                                        </p>
                                        <p
                                            className="text-xl font-bold"
                                            style={{ color: "#ef4444" }}
                                        >
                                            {creditsInfo.total_credits_used}
                                        </p>
                                    </div>
                                </div>

                                <div className="flex items-center justify-between mb-2">
                                    <h4
                                        className="text-sm font-medium"
                                        style={{ color: "var(--text)" }}
                                    >
                                        <History className="h-4 w-4 inline mr-1" />
                                        Histórico
                                    </h4>
                                    <button
                                        onClick={() =>
                                            openAdjustCredits(creditsUser)
                                        }
                                        className="cb-btn cb-btn-primary text-xs py-1 px-3 flex items-center gap-1"
                                    >
                                        <DollarSign className="h-3.5 w-3.5" />{" "}
                                        Ajustar
                                    </button>
                                </div>

                                {creditsInfo.transactions?.length > 0 ? (
                                    <div className="space-y-1 max-h-60 overflow-y-auto">
                                        {creditsInfo.transactions.map((tx) => (
                                            <div
                                                key={tx.id}
                                                className="flex items-center justify-between py-2 px-3 rounded text-xs"
                                                style={{
                                                    backgroundColor:
                                                        "var(--card-bg)",
                                                    border: "1px solid var(--card-border)",
                                                }}
                                            >
                                                <div className="flex-1">
                                                    <span
                                                        style={{
                                                            color: "var(--text)",
                                                        }}
                                                    >
                                                        {tx.description ||
                                                            tx.type}
                                                    </span>
                                                    <span
                                                        className="ml-2"
                                                        style={{
                                                            color: "var(--muted-text)",
                                                        }}
                                                    >
                                                        {new Date(
                                                            tx.created_at,
                                                        ).toLocaleString(
                                                            "pt-BR",
                                                            {
                                                                day: "2-digit",
                                                                month: "2-digit",
                                                                hour: "2-digit",
                                                                minute: "2-digit",
                                                            },
                                                        )}
                                                    </span>
                                                </div>
                                                <span
                                                    className="font-bold ml-3"
                                                    style={{
                                                        color:
                                                            tx.amount > 0
                                                                ? "#22c55e"
                                                                : "#ef4444",
                                                    }}
                                                >
                                                    {tx.amount > 0 ? "+" : ""}
                                                    {tx.amount}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p
                                        className="text-center py-4 text-xs"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        Nenhuma transação encontrada.
                                    </p>
                                )}
                            </>
                        ) : null}
                    </div>
                </div>
            )}

            {/* ── Adjust Credits Modal ──────────────────────────────────── */}
            {adjustOpen && adjustUser && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                    onClick={() => {
                        setAdjustOpen(false);
                        setAdjustUser(null);
                    }}
                >
                    <div
                        className="rounded-xl border p-6 w-full max-w-md shadow-2xl"
                        style={{
                            backgroundColor: "var(--panel)",
                            borderColor: "var(--panel-border)",
                        }}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-4">
                            <h3
                                className="text-lg font-semibold flex items-center gap-2"
                                style={{ color: "var(--text)" }}
                            >
                                <DollarSign
                                    className="h-5 w-5"
                                    style={{ color: "var(--accent)" }}
                                />
                                Ajustar Créditos
                            </h3>
                            <button
                                onClick={() => {
                                    setAdjustOpen(false);
                                    setAdjustUser(null);
                                }}
                                className="cb-btn p-1"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>

                        <p
                            className="text-sm mb-4"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Usuário:{" "}
                            <strong style={{ color: "var(--text)" }}>
                                {adjustUser.full_name || adjustUser.email}
                            </strong>
                        </p>

                        <form
                            onSubmit={submitAdjustCredits}
                            className="space-y-4"
                        >
                            <div>
                                <label
                                    className="block text-xs font-medium mb-1"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Valor (positivo = adicionar, negativo =
                                    remover)
                                </label>
                                <input
                                    type="number"
                                    value={adjustForm.amount}
                                    onChange={(e) =>
                                        setAdjustForm((f) => ({
                                            ...f,
                                            amount: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    placeholder="Ex: 50 ou -10"
                                    required
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-xs font-medium mb-1"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Tipo
                                </label>
                                <select
                                    value={adjustForm.type}
                                    onChange={(e) =>
                                        setAdjustForm((f) => ({
                                            ...f,
                                            type: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                >
                                    <option value="bonus">Bônus</option>
                                    <option value="refund">Reembolso</option>
                                    <option value="adjustment">Ajuste</option>
                                </select>
                            </div>
                            <div>
                                <label
                                    className="block text-xs font-medium mb-1"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Descrição *
                                </label>
                                <input
                                    type="text"
                                    value={adjustForm.description}
                                    onChange={(e) =>
                                        setAdjustForm((f) => ({
                                            ...f,
                                            description: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    placeholder="Motivo do ajuste..."
                                    required
                                />
                            </div>
                            <div className="flex justify-end gap-2 pt-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setAdjustOpen(false);
                                        setAdjustUser(null);
                                    }}
                                    className="cb-btn"
                                >
                                    Cancelar
                                </button>
                                <button
                                    type="submit"
                                    disabled={adjustLoading}
                                    className="cb-btn cb-btn-primary flex items-center gap-2"
                                >
                                    {adjustLoading ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Check className="h-4 w-4" />
                                    )}
                                    Salvar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Edit Modal─────────────────────────────────────────────── */}
            {editUser && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
                    onClick={() => setEditUser(null)}
                >
                    <div
                        className="cb-panel w-full max-w-md p-6"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold">
                                Editar Usuário
                            </h2>
                            <button
                                onClick={() => setEditUser(null)}
                                className="cb-btn p-1"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <form onSubmit={saveEdit} className="space-y-4">
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Nome
                                </label>
                                <input
                                    type="text"
                                    value={editForm.full_name}
                                    onChange={(e) =>
                                        setEditForm((f) => ({
                                            ...f,
                                            full_name: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    placeholder="Nome completo"
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Email
                                </label>
                                <input
                                    type="email"
                                    value={editForm.email}
                                    onChange={(e) =>
                                        setEditForm((f) => ({
                                            ...f,
                                            email: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    required
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Nova Senha{" "}
                                    <span
                                        className="text-xs"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        (deixe vazio para não alterar)
                                    </span>
                                </label>
                                <input
                                    type="password"
                                    value={editForm.password}
                                    onChange={(e) =>
                                        setEditForm((f) => ({
                                            ...f,
                                            password: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    placeholder="••••••••"
                                    minLength={4}
                                />
                            </div>
                            <div className="flex gap-2 pt-2">
                                <button
                                    type="submit"
                                    disabled={editLoading}
                                    className="cb-btn cb-btn-primary flex-1 flex items-center justify-center gap-2"
                                >
                                    {editLoading ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Check className="h-4 w-4" />
                                    )}
                                    Salvar
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setEditUser(null)}
                                    className="cb-btn flex-1"
                                >
                                    Cancelar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Create Modal ───────────────────────────────────────────── */}
            {createOpen && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
                    onClick={() => setCreateOpen(false)}
                >
                    <div
                        className="cb-panel w-full max-w-md p-6"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold flex items-center gap-2">
                                <UserPlus
                                    className="h-5 w-5"
                                    style={{ color: "var(--accent)" }}
                                />
                                Novo Usuário
                            </h2>
                            <button
                                onClick={() => setCreateOpen(false)}
                                className="cb-btn p-1"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <form onSubmit={handleCreate} className="space-y-4">
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Nome
                                </label>
                                <input
                                    type="text"
                                    value={createForm.full_name}
                                    onChange={(e) =>
                                        setCreateForm((f) => ({
                                            ...f,
                                            full_name: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    placeholder="Nome completo"
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Email
                                </label>
                                <input
                                    type="email"
                                    value={createForm.email}
                                    onChange={(e) =>
                                        setCreateForm((f) => ({
                                            ...f,
                                            email: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    required
                                    placeholder="email@exemplo.com"
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Senha
                                </label>
                                <input
                                    type="password"
                                    value={createForm.password}
                                    onChange={(e) =>
                                        setCreateForm((f) => ({
                                            ...f,
                                            password: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                    required
                                    minLength={4}
                                    placeholder="Mínimo 4 caracteres"
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-sm font-medium mb-1"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Role
                                </label>
                                <select
                                    value={createForm.role}
                                    onChange={(e) =>
                                        setCreateForm((f) => ({
                                            ...f,
                                            role: e.target.value,
                                        }))
                                    }
                                    className="cb-input w-full"
                                >
                                    {ROLES.map((r) => (
                                        <option key={r.value} value={r.value}>
                                            {r.label}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex gap-2 pt-2">
                                <button
                                    type="submit"
                                    disabled={createLoading}
                                    className="cb-btn cb-btn-primary flex-1 flex items-center justify-center gap-2"
                                >
                                    {createLoading ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <UserPlus className="h-4 w-4" />
                                    )}
                                    Criar
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setCreateOpen(false)}
                                    className="cb-btn flex-1"
                                >
                                    Cancelar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Stats Modal ────────────────────────────────────────────── */}
            {statsUser && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
                    onClick={() => setStatsUser(null)}
                >
                    <div
                        className="cb-panel w-full max-w-lg p-6"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold flex items-center gap-2">
                                <BarChart3
                                    className="h-5 w-5"
                                    style={{ color: "var(--accent)" }}
                                />
                                Uso de IA —{" "}
                                {statsUser.full_name || statsUser.email}
                            </h2>
                            <button
                                onClick={() => setStatsUser(null)}
                                className="cb-btn p-1"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>

                        {statsLoading ? (
                            <div className="flex items-center justify-center py-10">
                                <Loader2
                                    className="h-6 w-6 animate-spin"
                                    style={{ color: "var(--accent)" }}
                                />
                            </div>
                        ) : stats ? (
                            <div className="space-y-4">
                                <div className="grid grid-cols-2 gap-3">
                                    <StatCard
                                        label="Total de Requests"
                                        value={stats.total_requests}
                                        color="var(--accent)"
                                    />
                                    <StatCard
                                        label="Tokens Usados"
                                        value={stats.total_tokens.toLocaleString()}
                                        color="#f59e0b"
                                    />
                                </div>
                                {Object.keys(stats.by_provider || {}).length >
                                    0 && (
                                    <div>
                                        <p
                                            className="text-xs font-medium mb-2"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Por Provider
                                        </p>
                                        <div className="flex flex-wrap gap-2">
                                            {Object.entries(
                                                stats.by_provider,
                                            ).map(([prov, count]) => (
                                                <Badge
                                                    key={prov}
                                                    color="var(--accent)"
                                                >
                                                    {prov}: {count}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {stats.recent_logs?.length > 0 && (
                                    <div>
                                        <p
                                            className="text-xs font-medium mb-2"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            Últimos requests
                                        </p>
                                        <div
                                            className="rounded-lg border overflow-y-auto max-h-48"
                                            style={{
                                                borderColor:
                                                    "var(--panel-border)",
                                                backgroundColor: "var(--panel)",
                                            }}
                                        >
                                            <table className="admin-table w-full text-xs">
                                                <thead>
                                                    <tr
                                                        style={{
                                                            borderBottom:
                                                                "1px solid var(--panel-border)",
                                                        }}
                                                    >
                                                        <th
                                                            className="text-left px-3 py-2"
                                                            style={{
                                                                color: "var(--muted-text)",
                                                            }}
                                                        >
                                                            Endpoint
                                                        </th>
                                                        <th
                                                            className="text-left px-3 py-2"
                                                            style={{
                                                                color: "var(--muted-text)",
                                                            }}
                                                        >
                                                            Provider
                                                        </th>
                                                        <th
                                                            className="text-right px-3 py-2"
                                                            style={{
                                                                color: "var(--muted-text)",
                                                            }}
                                                        >
                                                            Tokens
                                                        </th>
                                                        <th
                                                            className="text-right px-3 py-2"
                                                            style={{
                                                                color: "var(--muted-text)",
                                                            }}
                                                        >
                                                            Data
                                                        </th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {stats.recent_logs
                                                        .slice(0, 20)
                                                        .map((log, i) => (
                                                            <tr
                                                                key={i}
                                                                style={{
                                                                    borderBottom:
                                                                        "1px solid var(--panel-border)",
                                                                }}
                                                            >
                                                                <td className="px-3 py-1.5 truncate max-w-[140px]">
                                                                    {
                                                                        log.endpoint
                                                                    }
                                                                </td>
                                                                <td className="px-3 py-1.5">
                                                                    {
                                                                        log.ai_provider
                                                                    }
                                                                </td>
                                                                <td className="px-3 py-1.5 text-right">
                                                                    {
                                                                        log.tokens_used
                                                                    }
                                                                </td>
                                                                <td
                                                                    className="px-3 py-1.5 text-right"
                                                                    style={{
                                                                        color: "var(--muted-text)",
                                                                    }}
                                                                >
                                                                    {new Date(
                                                                        log.timestamp,
                                                                    ).toLocaleString(
                                                                        "pt-BR",
                                                                        {
                                                                            day: "2-digit",
                                                                            month: "2-digit",
                                                                            hour: "2-digit",
                                                                            minute: "2-digit",
                                                                        },
                                                                    )}
                                                                </td>
                                                            </tr>
                                                        ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <p style={{ color: "var(--muted-text)" }}>
                                Sem dados de uso disponíveis.
                            </p>
                        )}
                    </div>
                </div>
            )}

            {/* ── Templates Permission Modal ───────────────────────────── */}
            {showTemplatesModal && selectedUserForTemplates && (
                <TemplatesModal
                    user={selectedUserForTemplates}
                    allTemplates={templates}
                    onClose={() => {
                        setShowTemplatesModal(false);
                        setSelectedUserForTemplates(null);
                    }}
                    onSave={saveUserTemplates}
                    saving={templateSaving}
                />
            )}
        </div>
    );
}

function TemplatesModal({ user, allTemplates, onClose, onSave, saving }) {
    const [selectedIds, setSelectedIds] = useState(() => {
        try {
            const allowed = user.permissions?.allowed_templates;
            if (!allowed) return [];
            return typeof allowed === "string" ? JSON.parse(allowed) : allowed;
        } catch (e) {
            console.warn("Erro ao parsear allowed_templates:", e);
            return [];
        }
    });

    const toggleTemplate = (id) => {
        setSelectedIds((prev) =>
            prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id],
        );
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
            onClick={onClose}
        >
            <div
                className="rounded-xl border w-full max-w-lg p-6 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
                style={{
                    backgroundColor: "var(--panel)",
                    borderColor: "var(--panel-border)",
                }}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold flex items-center gap-2">
                        <LayoutDashboard
                            className="h-5 w-5"
                            style={{ color: "var(--accent)" }}
                        />
                        Templates Permitidos
                    </h2>
                    <button onClick={onClose} className="cb-btn p-1">
                        <X className="h-4 w-4" />
                    </button>
                </div>

                <div className="mb-4">
                    <p className="text-sm" style={{ color: "var(--text)" }}>
                        Usuário: <span className="font-bold">{user.full_name || user.email}</span>
                    </p>
                    <p className="text-xs mt-1" style={{ color: "var(--muted-text)" }}>
                        Selecione os templates que este usuário poderá visualizar e utilizar.
                    </p>
                </div>

                <div className="flex-1 overflow-y-auto space-y-2 pr-1 mb-6">
                    {allTemplates.length > 0 && (
                        <div className="flex gap-2 mb-3">
                            <button
                                type="button"
                                onClick={() => setSelectedIds(allTemplates.map(t => t.id))}
                                className="cb-btn text-xs px-3 py-1"
                                style={{ color: "var(--accent)", borderColor: "var(--accent)" }}
                            >
                                Selecionar Todos
                            </button>
                            <button
                                type="button"
                                onClick={() => setSelectedIds([])}
                                className="cb-btn text-xs px-3 py-1"
                            >
                                Desmarcar Todos
                            </button>
                        </div>
                    )}
                    {allTemplates.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 opacity-40">
                            <FileText className="h-10 w-10 mb-2" />
                            <p className="text-sm">Nenhum template encontrado.</p>
                        </div>
                    ) : (
                        allTemplates.map((t) => {
                            const isSelected = selectedIds.includes(t.id);
                            return (
                                <div
                                    key={t.id}
                                    onClick={() => toggleTemplate(t.id)}
                                    className="flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all"
                                    style={{
                                        backgroundColor: isSelected ? "rgba(0, 210, 180, 0.05)" : "var(--card-bg)",
                                        borderColor: isSelected ? "var(--accent)" : "var(--card-border)",
                                    }}
                                >
                                    <div className="flex items-center gap-3">
                                        <div 
                                            className="h-10 w-10 rounded flex items-center justify-center bg-black/10"
                                            style={{ color: isSelected ? "var(--accent)" : "var(--muted-text)" }}
                                        >
                                            <FileText className="h-5 w-5" />
                                        </div>
                                        <div>
                                            <p className="text-sm font-medium">{t.name}</p>
                                            <p className="text-xs opacity-60">{t.short_name || t.id}</p>
                                        </div>
                                    </div>
                                    {isSelected ? (
                                        <CheckCircle2 className="h-5 w-5" style={{ color: "var(--accent)" }} />
                                    ) : (
                                        <div className="h-5 w-5 rounded-full border-2 opacity-20" />
                                    )}
                                </div>
                            );
                        })
                    )}
                </div>

                <div className="flex gap-2 pt-2 border-t" style={{ borderColor: "var(--panel-border)" }}>
                    <button
                        onClick={() => onSave(user.id, selectedIds)}
                        disabled={saving}
                        className="cb-btn cb-btn-primary flex-1 flex items-center justify-center gap-2"
                    >
                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                        Salvar Alterações
                    </button>
                    <button
                        type="button"
                        onClick={onClose}
                        className="cb-btn flex-1"
                    >
                        Cancelar
                    </button>
                </div>
            </div>
        </div>
    );
}
    // ─── Model Selection Modal Component ──────────────────────────────

    function ModelSelectionModal({ user, onClose, pending, setPending, setPendingField }) {
        if (!user) return null;

        const p = pending[user.id] || {};
        const perms = user.permissions || {};

        const models = [
            { id: "can_use_gemini", label: "Gemini", icon: Sparkles, color: "#4285f4" },
            
            { id: "can_use_whisper", label: "Whisper", icon: Mic, color: "#a855f7" },
        ];

        const exports = [
            { id: "can_export_html", label: "Exportar HTML", icon: Code, color: "#e34c26" },
            { id: "can_export_docx", label: "Exportar Word", icon: File, color: "#2b579a" },
            { id: "can_export_md", label: "Exportar Markdown", icon: FileText, color: "#000000" },
            { id: "can_export_pdf", label: "Exportar PDF", icon: FileDown, color: "#f40f02" },
        ];

        return (
            <div
                className="fixed inset-0 z-[100] flex items-center justify-center p-4 animate-in fade-in duration-200"
                style={{ backgroundColor: "var(--modal-overlay)" }}
            >
                <div 
                    className="cb-modal w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200"
                    style={{ backgroundColor: "var(--panel)", border: "1px solid var(--panel-border)" }}
                >
                    <div className="cb-modal-header p-4 border-b border-white/5 flex items-center justify-between">
                        <div>
                            <h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
                                Permissões de IA e Exportação
                            </h2>
                            <p className="text-xs mt-1" style={{ color: "var(--muted-text)" }}>
                                {user.full_name || user.email}
                            </p>
                        </div>
                        <button onClick={onClose} className="cb-btn p-1.5 hover:bg-white/5 rounded-lg">
                            <X className="h-5 w-5" />
                        </button>
                    </div>

                    <div className="p-4 space-y-3">
                        {models.map((m) => {
                            const eff = effective(perms[m.id], p, m.id);
                            const Icon = m.icon;

                            return (
                                <div 
                                    key={m.id}
                                    className="flex items-center justify-between p-3 rounded-xl transition-all border border-transparent hover:border-white/5"
                                    style={{ 
                                        backgroundColor: eff ? "rgba(0, 210, 180, 0.05)" : "rgba(0, 0, 0, 0.1)",
                                        border: eff ? "1px solid rgba(0, 210, 180, 0.1)" : undefined
                                    }}
                                >
                                    <div className="flex items-center gap-3">
                                        <div 
                                            className="w-10 h-10 rounded-lg flex items-center justify-center"
                                            style={{ backgroundColor: `${m.color}15`, color: m.color }}
                                        >
                                            <Icon className="h-5 w-5" />
                                        </div>
                                        <div className="font-medium" style={{ color: "var(--text)" }}>
                                            {m.label}
                                        </div>
                                    </div>

                                    <button
                                        onClick={() => {
                                            const newVal = !eff;
                                            if (newVal === perms[m.id]) {
                                                setPending((prev) => {
                                                    const next = { ...(prev[user.id] || {}) };
                                                    delete next[m.id];
                                                    if (Object.keys(next).length === 0) {
                                                        const all = { ...prev };
                                                        delete all[user.id];
                                                        return all;
                                                    }
                                                    return { ...prev, [user.id]: next };
                                                });
                                            } else {
                                                setPendingField(user.id, m.id, newVal);
                                            }
                                        }}
                                        className="transition-all"
                                    >
                                        {eff ? (
                                            <ToggleRight className="h-7 w-7" style={{ color: "#22c55e" }} />
                                        ) : (
                                            <ToggleLeft className="h-7 w-7" style={{ color: "var(--muted-text)" }} />
                                        )}
                                    </button>
                                </div>
                            );
                        })}

                        <div className="pt-2 pb-1">
                            <h3 className="text-xs font-bold uppercase tracking-wider opacity-50" style={{ color: "var(--text)" }}>
                                Formatos de Exportação
                            </h3>
                        </div>

                        {exports.map((m) => {
                            const eff = effective(perms[m.id], p, m.id);
                            const Icon = m.icon;

                            return (
                                <div 
                                    key={m.id}
                                    className="flex items-center justify-between p-3 rounded-xl transition-all border border-transparent hover:border-white/5"
                                    style={{ 
                                        backgroundColor: eff ? "rgba(0, 210, 180, 0.05)" : "rgba(0, 0, 0, 0.1)",
                                        border: eff ? "1px solid rgba(0, 210, 180, 0.1)" : undefined
                                    }}
                                >
                                    <div className="flex items-center gap-3">
                                        <div 
                                            className="w-10 h-10 rounded-xl flex items-center justify-center shadow-sm"
                                            style={{ backgroundColor: "rgba(255,255,255,0.03)" }}
                                        >
                                            <Icon size={20} style={{ color: m.color }} />
                                        </div>
                                        <div>
                                            <div className="font-medium" style={{ color: "var(--text)" }}>{m.label}</div>
                                            <div className="text-[10px]" style={{ color: "var(--muted-text)" }}>
                                                {eff ? "Habilitado" : "Bloqueado"}
                                            </div>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => setPendingField(user.id, m.id, !eff)}
                                        className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none"
                                        style={{ backgroundColor: eff ? "var(--accent)" : "rgba(255,255,255,0.1)" }}
                                    >
                                        <span
                                            className={`${
                                                eff ? "translate-x-6" : "translate-x-1"
                                            } inline-block h-4 w-4 transform rounded-full bg-white transition-transform`}
                                        />
                                    </button>
                                </div>
                            );
                        })}
                    </div>

                    <div className="p-4 bg-black/10 flex justify-end">
                        <button
                            onClick={onClose}
                            className="cb-btn cb-btn-primary px-6"
                        >
                            Concluído
                        </button>
                    </div>
                </div>
            </div>
        );
    }
