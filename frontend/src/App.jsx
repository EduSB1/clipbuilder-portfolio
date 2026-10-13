import { lazy, Suspense, useState, useEffect, useCallback } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAppAuth } from "./utils/AuthContext.jsx";
import { onInsufficientCredits } from "./utils/api";
import AuthLoading from "./components/shared/AuthLoading";
import PendingApproval from "./pages/login/PendingApproval";
import InsufficientCreditsModal from "./components/modals/InsufficientCreditsModal";
import ErrorBoundary from "./components/shared/ErrorBoundary";
import AppBackground from "./components/shared/AppBackground";

// Reexportado por compatibilidade com quem já importava `{ AuthLoading }` daqui.
export { default as AuthLoading } from "./components/shared/AuthLoading";

// ── Rotas carregadas sob demanda ─────────────────────────────────────────────
// Cada página vira um chunk separado. Sem isso, o painel administrativo (o
// maior arquivo do projeto) e as bibliotecas do editor de imagem eram baixados
// por todo usuário no primeiro acesso, inclusive por quem nunca abre o /admin.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const AdminDashboard = lazy(() => import("./components/admin/AdminDashboard"));
const CreditsPage = lazy(() => import("./pages/CreditsPage"));
const SysLogin = lazy(() => import("./pages/SysLogin"));
const SsoCallback = lazy(() => import("./pages/SsoCallback"));

function ProtectedRoute({ children }) {
    const { isLoaded, isSignedIn, authError, refreshProfile } = useAppAuth();
    if (!isLoaded) {
        if (authError?.isPendingApproval) return <PendingApproval />;
        return <AuthLoading error={authError} onRetry={refreshProfile} />;
    }
    // Sessão carregada mas sem usuário: contas inativas recebem 403, que marca
    // `isPendingApproval` — mostramos a tela de aprovação em vez do login.
    if (!isSignedIn) {
        if (authError?.isPendingApproval) return <PendingApproval />;
        return <Navigate to="/login" replace />;
    }
    return children;
}

function AdminRoute({ children }) {
    const { isLoaded, isSignedIn, user, backendLoaded, authError, refreshProfile } =
        useAppAuth();
    if (!isLoaded)
        return (
            <AuthLoading
                message="A verificar permissões..."
                error={authError}
                onRetry={refreshProfile}
            />
        );
    if (!isSignedIn) return <Navigate to="/login" replace />;
    if (!backendLoaded)
        return (
            <AuthLoading
                message="A carregar perfil..."
                error={authError}
                onRetry={refreshProfile}
            />
        );
    if (user?.role !== "admin") return <Navigate to="/" replace />;
    return children;
}

export default function App() {
    const [creditsModalOpen, setCreditsModalOpen] = useState(false);
    const [creditsModalDetail, setCreditsModalDetail] = useState(null);

    useEffect(() => {
        const isDark = (() => {
            try {
                return localStorage.getItem("CLIPBUILDER_DARK") !== "0";
            } catch {
                return true;
            }
        })();
        document.documentElement.classList.toggle("dark", isDark);
        document.documentElement.classList.toggle("light", !isDark);
    }, []);

    const handleInsufficientCredits = useCallback((detail) => {
        setCreditsModalDetail(detail || null);
        setCreditsModalOpen(true);
    }, []);

    useEffect(() => {
        onInsufficientCredits(handleInsufficientCredits);
        return () => onInsufficientCredits(null);
    }, [handleInsufficientCredits]);

    return (
        <ErrorBoundary>
            <AppBackground />

            <InsufficientCreditsModal
                open={creditsModalOpen}
                onClose={() => setCreditsModalOpen(false)}
                detail={creditsModalDetail}
            />

            <Suspense fallback={<AuthLoading message="A carregar..." />}>
                <Routes>
                    <Route path="/login/*" element={<SysLogin />} />
                    <Route path="/sso-callback" element={<SsoCallback />} />
                    <Route path="/sys/login" element={<Navigate to="/login" replace />} />

                    <Route
                        path="/admin"
                        element={
                            <AdminRoute>
                                <AdminDashboard />
                            </AdminRoute>
                        }
                    />

                    <Route
                        path="/credits"
                        element={
                            <ProtectedRoute>
                                <CreditsPage />
                            </ProtectedRoute>
                        }
                    />

                    <Route
                        path="/"
                        element={
                            <ProtectedRoute>
                                <Dashboard />
                            </ProtectedRoute>
                        }
                    />

                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </Suspense>
        </ErrorBoundary>
    );
}
