import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAppAuth } from "../utils/AuthContext";
import { api } from "../utils/api";
import LoginPage from "./login/LoginPage";
import PendingApproval from "./login/PendingApproval";
import AuthLoading from "../components/shared/AuthLoading";

export default function SysLogin() {
    const { mode, isSignedIn, authError, refreshProfile } = useAppAuth();
    const navigate = useNavigate();

    // JWT-only mode state (used only when Clerk is NOT configured)
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (isSignedIn) {
            if (mode === "jwt") navigate("/admin");
            else navigate("/");
        }
    }, [isSignedIn, mode, navigate]);

    if (authError?.isPendingApproval) {
        return <PendingApproval />;
    }
    if (authError) {
        return <AuthLoading error={authError} onRetry={refreshProfile} />;
    }

    // JWT-only mode: local admin form (used only when VITE_CLERK_PUBLISHABLE_KEY is NOT set)
    async function handleSubmit(e) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            const res = await api.post("/sys/token", { email, password });
            const token = res.data?.access_token;
            if (!token) throw new Error("Token não recebido");

            sessionStorage.setItem("__sys_token", token);
            api.defaults.headers.common["Authorization"] = "Bearer " + token;
            navigate("/admin");
        } catch (err) {
            const detail =
                err?.response?.data?.detail ||
                err.message ||
                "Erro desconhecido";
            setError(detail);
        } finally {
            setLoading(false);
        }
    }

    // ── Clerk mode: custom headless Clerk login page ──
    if (mode === "clerk") {
        return <LoginPage />;
    }

    // ── JWT-only mode: local admin form (no Clerk configured) ──
    return (
        <div
            className="cb-app-shell"
            style={{
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: "var(--bg)",
                padding: "1rem",
            }}
        >
            <form
                onSubmit={handleSubmit}
                style={{
                    backgroundColor: "var(--panel)",
                    border: "1px solid var(--border)",
                    borderRadius: "16px",
                    padding: "2rem",
                    width: "100%",
                    maxWidth: "360px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "1rem",
                    backdropFilter: "blur(16px)",
                    boxShadow: "0 20px 42px rgba(2, 8, 14, 0.48)",
                }}
            >
                <div style={{ marginBottom: "0.5rem" }}>
                    <div
                        style={{
                            width: "32px",
                            height: "32px",
                            borderRadius: "50%",
                            backgroundColor: "rgba(10, 93, 115, 0.12)",
                            border: "1px solid var(--border-hi)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            marginBottom: "0.75rem",
                        }}
                    >
                        <svg
                            width="16"
                            height="16"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="var(--text-secondary)"
                            strokeWidth="2"
                        >
                            <rect
                                x="3"
                                y="11"
                                width="18"
                                height="11"
                                rx="2"
                                ry="2"
                            />
                            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                        </svg>
                    </div>
                    <p style={{ color: "var(--muted-text)", fontSize: "11px", margin: 0 }}>
                        Acesso restrito
                    </p>
                </div>

                <div
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "4px",
                    }}
                >
                    <label style={{ color: "var(--muted-text)", fontSize: "11px" }}>
                        Email
                    </label>
                    <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        autoComplete="email"
                        style={{
                            backgroundColor: "rgba(6, 12, 18, 0.8)",
                            border: "1px solid var(--border)",
                            borderRadius: "10px",
                            padding: "8px 10px",
                            color: "var(--text)",
                            fontSize: "13px",
                            outline: "none",
                        }}
                    />
                </div>

                <div
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "4px",
                    }}
                >
                    <label style={{ color: "var(--muted-text)", fontSize: "11px" }}>
                        Senha
                    </label>
                    <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        autoComplete="current-password"
                        style={{
                            backgroundColor: "rgba(6, 12, 18, 0.8)",
                            border: "1px solid var(--border)",
                            borderRadius: "10px",
                            padding: "8px 10px",
                            color: "var(--text)",
                            fontSize: "13px",
                            outline: "none",
                        }}
                    />
                </div>

                {error && (
                    <p
                        style={{
                            color: "var(--danger)",
                            fontSize: "12px",
                            margin: 0,
                        }}
                    >
                        {error}
                    </p>
                )}

                <button
                    type="submit"
                    disabled={loading}
                    className="cb-btn cb-btn-primary"
                    style={{
                        padding: "9px",
                        fontSize: "12px",
                        cursor: loading ? "not-allowed" : "pointer",
                        marginTop: "0.25rem",
                    }}
                >
                    {loading ? "..." : "Entrar"}
                </button>
            </form>
        </div>
    );
}
