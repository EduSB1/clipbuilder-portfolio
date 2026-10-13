import { useState, useRef, useEffect } from "react";
import { api } from "../../utils/api";
import {
    Loader2,
    X,
    Send,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Info,
    Mail,
    Shield,
    Wifi,
    Lock,
    ExternalLink,
    Terminal,
} from "lucide-react";

// ── Step icon mapping ────────────────────────────────────────────────

const STEP_ICONS = {
    1: Shield, // Validate config
    2: Wifi, // Connect
    3: Lock, // TLS
    4: Lock, // Auth
    5: Send, // Send email
};

const STATUS_STYLES = {
    running: {
        color: "var(--accent)",
        bg: "rgba(59,130,246,0.08)",
        border: "rgba(59,130,246,0.25)",
        icon: Loader2,
        iconClass: "animate-spin",
    },
    success: {
        color: "#22c55e",
        bg: "rgba(34,197,94,0.08)",
        border: "rgba(34,197,94,0.25)",
        icon: CheckCircle2,
        iconClass: "",
    },
    error: {
        color: "#ef4444",
        bg: "rgba(239,68,68,0.08)",
        border: "rgba(239,68,68,0.25)",
        icon: XCircle,
        iconClass: "",
    },
    warning: {
        color: "#eab308",
        bg: "rgba(234,179,8,0.08)",
        border: "rgba(234,179,8,0.25)",
        icon: AlertTriangle,
        iconClass: "",
    },
    skipped: {
        color: "var(--muted-text)",
        bg: "transparent",
        border: "var(--card-border)",
        icon: Info,
        iconClass: "",
    },
    pending: {
        color: "var(--muted-text)",
        bg: "transparent",
        border: "var(--card-border)",
        icon: null,
        iconClass: "",
    },
};

// ── Pending steps skeleton ───────────────────────────────────────────

const PENDING_STEPS = [
    { step: 1, label: "Validar configuração" },
    { step: 2, label: "Conectar ao servidor" },
    { step: 3, label: "Negociar TLS/SSL" },
    { step: 4, label: "Autenticar" },
    { step: 5, label: "Enviar e-mail de teste" },
];

// ── Component ────────────────────────────────────────────────────────

export default function SmtpDiagnosticModal({ isOpen, onClose, smtpConfig }) {
    const [toEmail, setToEmail] = useState("");
    const [running, setRunning] = useState(false);
    const [steps, setSteps] = useState([]);
    const [summary, setSummary] = useState(null);
    const [overallSuccess, setOverallSuccess] = useState(null);
    const [animatingStep, setAnimatingStep] = useState(0);
    const logEndRef = useRef(null);
    const inputRef = useRef(null);

    // Auto-focus email input on open
    useEffect(() => {
        if (isOpen) {
            setSteps([]);
            setSummary(null);
            setOverallSuccess(null);
            setAnimatingStep(0);
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    }, [isOpen]);

    // Auto-scroll log
    useEffect(() => {
        if (logEndRef.current) {
            logEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [steps, animatingStep]);

    // Detect if Gmail
    const isGmail =
        (smtpConfig?.host || "").toLowerCase().includes("smtp.gmail.com") ||
        (smtpConfig?.host || "").toLowerCase().includes("gmail");

    // Detect if Office 365 / Outlook / Microsoft
    const smtpHostLower = (smtpConfig?.host || "").toLowerCase();
    const isOffice365 =
        smtpHostLower.includes("office365") ||
        smtpHostLower.includes("outlook") ||
        smtpHostLower.includes("microsoft") ||
        smtpHostLower.includes("exchange") ||
        smtpHostLower.includes("hotmail") ||
        smtpHostLower.includes("live.com");

    async function handleRunDiagnostic() {
        if (!toEmail.trim()) return;
        setRunning(true);
        setSteps([]);
        setSummary(null);
        setOverallSuccess(null);
        setAnimatingStep(0);

        // Show pending steps with animation
        for (let i = 0; i < PENDING_STEPS.length; i++) {
            setAnimatingStep(i + 1);
            await new Promise((r) => setTimeout(r, 80));
        }

        try {
            const body = {
                to_email: toEmail.trim(),
            };
            // Pass current (possibly unsaved) config values
            if (smtpConfig) {
                if (smtpConfig.host) body.host = smtpConfig.host;
                if (smtpConfig.port)
                    body.port = parseInt(smtpConfig.port, 10) || undefined;
                if (smtpConfig.username) body.username = smtpConfig.username;
                if (smtpConfig.password) body.password = smtpConfig.password;
                if (smtpConfig.use_tls !== undefined)
                    body.use_tls =
                        smtpConfig.use_tls === "true" ||
                        smtpConfig.use_tls === true;
                if (smtpConfig.from_email)
                    body.from_email = smtpConfig.from_email;
            }

            const res = await api.post("/admin/settings/smtp-diagnostic", body);
            const data = res.data;

            // Animate steps appearing one by one
            const resultSteps = data.steps || [];
            setSteps([]);
            for (let i = 0; i < resultSteps.length; i++) {
                await new Promise((r) => setTimeout(r, 350));
                setSteps((prev) => [...prev, resultSteps[i]]);
            }

            await new Promise((r) => setTimeout(r, 300));
            setSummary(data.summary);
            setOverallSuccess(data.success);
        } catch (err) {
            const detail =
                err?.response?.data?.detail ||
                err.message ||
                "Erro desconhecido";
            setSteps([
                {
                    step: 1,
                    label: "Erro na requisição",
                    status: "error",
                    message:
                        typeof detail === "string"
                            ? detail
                            : JSON.stringify(detail),
                    duration_ms: 0,
                },
            ]);
            setSummary("Falha ao executar diagnóstico.");
            setOverallSuccess(false);
        } finally {
            setRunning(false);
            setAnimatingStep(0);
        }
    }

    function handleKeyDown(e) {
        if (e.key === "Enter" && !running && toEmail.trim()) {
            handleRunDiagnostic();
        }
    }

    if (!isOpen) return null;

    const hasResult = steps.length > 0 || summary;

    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4"
            style={{ backgroundColor: "rgba(0,0,0,0.6)" }}
            onClick={(e) => {
                if (e.target === e.currentTarget && !running) onClose();
            }}
        >
            <div
                className="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-xl overflow-hidden shadow-2xl"
                style={{
                    backgroundColor: "var(--card-bg)",
                    border: "1px solid var(--card-border)",
                }}
            >
                {/* ── Header ────────────────────────────────────────────── */}
                <div
                    className="flex items-center justify-between px-5 py-4 flex-shrink-0"
                    style={{
                        borderBottom: "1px solid var(--card-border)",
                        background:
                            "linear-gradient(135deg, var(--panel) 0%, var(--card-bg) 100%)",
                    }}
                >
                    <div className="flex items-center gap-3">
                        <div
                            className="p-2 rounded-lg"
                            style={{ backgroundColor: "rgba(59,130,246,0.1)" }}
                        >
                            <Terminal
                                className="h-5 w-5"
                                style={{ color: "var(--accent)" }}
                            />
                        </div>
                        <div>
                            <h2
                                className="text-base font-semibold"
                                style={{ color: "var(--text)" }}
                            >
                                Diagnóstico SMTP
                            </h2>
                            <p
                                className="text-xs mt-0.5"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Teste passo a passo da configuração de e-mail
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        disabled={running}
                        className="p-1.5 rounded-lg transition-colors hover:bg-black/10"
                        style={{ color: "var(--muted-text)" }}
                        aria-label="Fechar"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>

                {/* ── Body (scrollable) ─────────────────────────────────── */}
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
                    {/* Gmail Banner */}
                    {isGmail && (
                        <div
                            className="rounded-lg border p-3.5 text-sm flex items-start gap-3"
                            style={{
                                borderColor: "#eab30840",
                                backgroundColor: "#eab30810",
                            }}
                        >
                            <AlertTriangle
                                className="h-5 w-5 flex-shrink-0 mt-0.5"
                                style={{ color: "#eab308" }}
                            />
                            <div>
                                <p
                                    className="font-semibold mb-1"
                                    style={{ color: "#eab308" }}
                                >
                                    Gmail detectado
                                </p>
                                <p
                                    className="text-xs leading-relaxed"
                                    style={{ color: "var(--text)" }}
                                >
                                    Para Gmail, você <strong>DEVE</strong> usar
                                    uma{" "}
                                    <strong>Senha de App de 16 dígitos</strong>.
                                    Sua senha padrão será bloqueada pelo Google.
                                    A Verificação em 2 Etapas precisa estar
                                    ativada.
                                </p>
                                <a
                                    href="https://myaccount.google.com/apppasswords"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1.5 text-xs font-medium mt-2 underline underline-offset-2"
                                    style={{ color: "#eab308" }}
                                >
                                    <ExternalLink className="h-3 w-3" />
                                    Gerar Senha de App no Google
                                </a>
                                <span
                                    className="mx-2 text-xs"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    |
                                </span>
                                <a
                                    href="https://myaccount.google.com/security"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1.5 text-xs font-medium mt-2 underline underline-offset-2"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    <Shield className="h-3 w-3" />
                                    Segurança da Conta Google
                                </a>
                            </div>
                        </div>
                    )}

                    {/* Office 365 / Microsoft Banner */}
                    {isOffice365 && (
                        <div
                            className="rounded-lg border p-3.5 text-sm flex items-start gap-3"
                            style={{
                                borderColor: "#3b82f640",
                                backgroundColor: "#3b82f610",
                            }}
                        >
                            <AlertTriangle
                                className="h-5 w-5 flex-shrink-0 mt-0.5"
                                style={{ color: "#60a5fa" }}
                            />
                            <div>
                                <p
                                    className="font-semibold mb-1"
                                    style={{ color: "#60a5fa" }}
                                >
                                    Microsoft 365 / Office 365 detectado
                                </p>
                                <p
                                    className="text-xs leading-relaxed mb-1.5"
                                    style={{ color: "var(--text)" }}
                                >
                                    Para autenticação SMTP com Office 365,
                                    verifique:
                                </p>
                                <ul
                                    className="text-xs leading-relaxed space-y-1 list-none"
                                    style={{ color: "var(--text)" }}
                                >
                                    <li>
                                        <strong>1.</strong>{" "}
                                        <strong>Authenticated SMTP</strong> deve
                                        estar habilitado no Admin Center →
                                        Usuários → Mail → Manage email apps.
                                    </li>
                                    <li>
                                        <strong>2.</strong>{" "}
                                        <strong>Security Defaults</strong> devem
                                        estar <strong>desativados</strong> no
                                        Azure AD / Entra ID (bloqueiam
                                        autenticação básica SMTP).
                                    </li>
                                    <li>
                                        <strong>3.</strong> Se o usuário tem{" "}
                                        <strong>MFA ativo</strong>, crie uma{" "}
                                        <strong>App Password</strong> dedicada.
                                    </li>
                                    <li>
                                        <strong>4.</strong> Após redefinir a
                                        senha, aguarde{" "}
                                        <strong>1–2 minutos</strong> para a
                                        propagação no Microsoft 365.
                                    </li>
                                    <li>
                                        <strong>5.</strong> Verifique se não há
                                        política de{" "}
                                        <strong>Acesso Condicional</strong>{" "}
                                        bloqueando Legacy Authentication.
                                    </li>
                                </ul>
                                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2">
                                    <a
                                        href="https://admin.microsoft.com/#/users"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1.5 text-xs font-medium underline underline-offset-2"
                                        style={{ color: "#60a5fa" }}
                                    >
                                        <ExternalLink className="h-3 w-3" />
                                        Admin Center (Usuários)
                                    </a>
                                    <a
                                        href="https://entra.microsoft.com/#view/Microsoft_AAD_IAM/SecurityDefaultsBlade"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1.5 text-xs font-medium underline underline-offset-2"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        <Shield className="h-3 w-3" />
                                        Security Defaults (Entra ID)
                                    </a>
                                    <a
                                        href="https://mysignins.microsoft.com/security-info"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1.5 text-xs font-medium underline underline-offset-2"
                                        style={{ color: "var(--muted-text)" }}
                                    >
                                        <Lock className="h-3 w-3" />
                                        Criar App Password
                                    </a>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Email input */}
                    <div>
                        <label
                            className="block text-sm font-medium mb-1.5"
                            style={{ color: "var(--text)" }}
                        >
                            E-mail de destino
                        </label>
                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <Mail
                                    className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4"
                                    style={{ color: "var(--muted-text)" }}
                                />
                                <input
                                    ref={inputRef}
                                    type="email"
                                    value={toEmail}
                                    onChange={(e) => setToEmail(e.target.value)}
                                    onKeyDown={handleKeyDown}
                                    disabled={running}
                                    placeholder="Digite o e-mail para receber o teste..."
                                    className="cb-input w-full pl-9 pr-3"
                                    autoComplete="email"
                                />
                            </div>
                            <button
                                onClick={handleRunDiagnostic}
                                disabled={running || !toEmail.trim()}
                                className="cb-btn cb-btn-primary flex items-center gap-2 px-4 whitespace-nowrap"
                                style={{
                                    opacity:
                                        running || !toEmail.trim() ? 0.6 : 1,
                                }}
                            >
                                {running ? (
                                    <>
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        Testando...
                                    </>
                                ) : (
                                    <>
                                        <Send className="h-4 w-4" />
                                        Executar Diagnóstico
                                    </>
                                )}
                            </button>
                        </div>
                        <p
                            className="text-xs mt-1.5"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Um e-mail de teste será enviado para este endereço
                            se todas as etapas passarem.
                        </p>
                    </div>

                    {/* ── Terminal Log ─────────────────────────────────────── */}
                    {(running || hasResult) && (
                        <div
                            className="rounded-lg border overflow-hidden"
                            style={{
                                borderColor: "var(--card-border)",
                                backgroundColor: "#0d1117",
                            }}
                        >
                            {/* Terminal header bar */}
                            <div
                                className="flex items-center gap-2 px-4 py-2"
                                style={{
                                    backgroundColor: "#161b22",
                                    borderBottom: "1px solid #30363d",
                                }}
                            >
                                <div className="flex gap-1.5">
                                    <div
                                        className="w-3 h-3 rounded-full"
                                        style={{ backgroundColor: "#ff5f57" }}
                                    />
                                    <div
                                        className="w-3 h-3 rounded-full"
                                        style={{ backgroundColor: "#febc2e" }}
                                    />
                                    <div
                                        className="w-3 h-3 rounded-full"
                                        style={{ backgroundColor: "#28c840" }}
                                    />
                                </div>
                                <span
                                    className="text-xs font-mono ml-2"
                                    style={{ color: "#8b949e" }}
                                >
                                    smtp-diagnostic
                                </span>
                            </div>

                            {/* Log entries */}
                            <div
                                className="p-4 space-y-2 font-mono text-xs max-h-[340px] overflow-y-auto"
                                style={{ color: "#c9d1d9" }}
                            >
                                {/* Show pending skeleton while running */}
                                {running && steps.length === 0 && (
                                    <>
                                        {PENDING_STEPS.map((ps) => {
                                            const isVisible =
                                                ps.step <= animatingStep;
                                            if (!isVisible) return null;
                                            const isActive =
                                                ps.step === animatingStep;
                                            return (
                                                <div
                                                    key={ps.step}
                                                    className="flex items-start gap-2.5 py-1.5 transition-all duration-300"
                                                    style={{
                                                        opacity: isActive
                                                            ? 1
                                                            : 0.4,
                                                    }}
                                                >
                                                    <span
                                                        className="flex-shrink-0 w-5 text-right"
                                                        style={{
                                                            color: "#484f58",
                                                        }}
                                                    >
                                                        {ps.step}.
                                                    </span>
                                                    {isActive ? (
                                                        <Loader2
                                                            className="h-3.5 w-3.5 flex-shrink-0 mt-0.5 animate-spin"
                                                            style={{
                                                                color: "var(--accent)",
                                                            }}
                                                        />
                                                    ) : (
                                                        <div
                                                            className="h-3.5 w-3.5 flex-shrink-0 mt-0.5 rounded-full"
                                                            style={{
                                                                border: "1px dashed #30363d",
                                                            }}
                                                        />
                                                    )}
                                                    <span
                                                        style={{
                                                            color: isActive
                                                                ? "#c9d1d9"
                                                                : "#484f58",
                                                        }}
                                                    >
                                                        {ps.label}
                                                        {isActive && (
                                                            <span className="animate-pulse ml-1">
                                                                ...
                                                            </span>
                                                        )}
                                                    </span>
                                                </div>
                                            );
                                        })}
                                    </>
                                )}

                                {/* Actual result steps */}
                                {steps.map((s, idx) => {
                                    const style =
                                        STATUS_STYLES[s.status] ||
                                        STATUS_STYLES.pending;
                                    const StepIcon = STEP_ICONS[s.step] || Info;
                                    const StatusIcon = style.icon;

                                    return (
                                        <div
                                            key={idx}
                                            className="rounded-md px-3 py-2.5 transition-all duration-300"
                                            style={{
                                                backgroundColor: style.bg,
                                                border: `1px solid ${style.border}`,
                                                animation:
                                                    "fadeSlideIn 0.3s ease-out",
                                            }}
                                        >
                                            <div className="flex items-center gap-2 mb-1">
                                                <span
                                                    className="flex-shrink-0 text-xs font-bold"
                                                    style={{
                                                        color: "#484f58",
                                                        minWidth: "18px",
                                                    }}
                                                >
                                                    {s.step}.
                                                </span>
                                                <StepIcon
                                                    className="h-3.5 w-3.5 flex-shrink-0"
                                                    style={{
                                                        color: style.color,
                                                    }}
                                                />
                                                <span
                                                    className="font-semibold text-xs"
                                                    style={{
                                                        color: style.color,
                                                    }}
                                                >
                                                    {s.label}
                                                </span>
                                                {StatusIcon && (
                                                    <StatusIcon
                                                        className={`h-3.5 w-3.5 flex-shrink-0 ml-auto ${style.iconClass}`}
                                                        style={{
                                                            color: style.color,
                                                        }}
                                                    />
                                                )}
                                                {s.duration_ms != null &&
                                                    s.duration_ms > 0 && (
                                                        <span
                                                            className="text-[10px] ml-1"
                                                            style={{
                                                                color: "#484f58",
                                                            }}
                                                        >
                                                            {s.duration_ms}ms
                                                        </span>
                                                    )}
                                            </div>
                                            <p
                                                className="text-[11px] leading-relaxed ml-[26px] break-words"
                                                style={{
                                                    color:
                                                        s.status === "error"
                                                            ? "#fca5a5"
                                                            : s.status ===
                                                                "warning"
                                                              ? "#fde68a"
                                                              : "#8b949e",
                                                }}
                                            >
                                                {s.message}
                                            </p>
                                        </div>
                                    );
                                })}

                                {/* Summary */}
                                {summary && (
                                    <div
                                        className="mt-3 pt-3 flex items-start gap-2"
                                        style={{
                                            borderTop: "1px solid #21262d",
                                        }}
                                    >
                                        {overallSuccess ? (
                                            <CheckCircle2
                                                className="h-4 w-4 flex-shrink-0 mt-0.5"
                                                style={{ color: "#22c55e" }}
                                            />
                                        ) : (
                                            <XCircle
                                                className="h-4 w-4 flex-shrink-0 mt-0.5"
                                                style={{ color: "#ef4444" }}
                                            />
                                        )}
                                        <span
                                            className="text-xs font-semibold"
                                            style={{
                                                color: overallSuccess
                                                    ? "#22c55e"
                                                    : "#ef4444",
                                            }}
                                        >
                                            {summary}
                                        </span>
                                    </div>
                                )}

                                <div ref={logEndRef} />
                            </div>
                        </div>
                    )}

                    {/* Empty state hint */}
                    {!running && !hasResult && (
                        <div
                            className="rounded-lg border border-dashed p-8 text-center"
                            style={{ borderColor: "var(--card-border)" }}
                        >
                            <Terminal
                                className="h-8 w-8 mx-auto mb-3"
                                style={{
                                    color: "var(--muted-text)",
                                    opacity: 0.4,
                                }}
                            />
                            <p
                                className="text-sm font-medium"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Pronto para diagnosticar
                            </p>
                            <p
                                className="text-xs mt-1"
                                style={{
                                    color: "var(--muted-text)",
                                    opacity: 0.7,
                                }}
                            >
                                Informe um e-mail de destino e clique em{" "}
                                <strong>Executar Diagnóstico</strong> para
                                testar cada etapa da conexão SMTP.
                            </p>
                        </div>
                    )}
                </div>

                {/* ── Footer ────────────────────────────────────────────── */}
                <div
                    className="flex items-center justify-end gap-3 px-5 py-3.5 flex-shrink-0"
                    style={{
                        borderTop: "1px solid var(--card-border)",
                        backgroundColor: "var(--panel)",
                    }}
                >
                    {overallSuccess === true && (
                        <span
                            className="text-xs font-medium flex items-center gap-1.5 mr-auto"
                            style={{ color: "#22c55e" }}
                        >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            SMTP configurado corretamente!
                        </span>
                    )}
                    {overallSuccess === false && (
                        <span
                            className="text-xs font-medium flex items-center gap-1.5 mr-auto"
                            style={{ color: "#ef4444" }}
                        >
                            <XCircle className="h-3.5 w-3.5" />
                            Corrija os erros e tente novamente.
                        </span>
                    )}
                    <button
                        onClick={onClose}
                        disabled={running}
                        className="cb-btn px-4"
                    >
                        Fechar
                    </button>
                    {hasResult && !running && (
                        <button
                            onClick={handleRunDiagnostic}
                            disabled={!toEmail.trim()}
                            className="cb-btn cb-btn-primary flex items-center gap-2 px-4"
                        >
                            <Send className="h-3.5 w-3.5" />
                            Testar Novamente
                        </button>
                    )}
                </div>
            </div>

            {/* Inline keyframe animation */}
            <style>{`
        @keyframes fadeSlideIn {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
        </div>
    );
}
