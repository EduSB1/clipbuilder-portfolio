import { useEffect, useRef, useState } from "react";
import { useSignIn, useSignUp, useAuth, useClerk } from "@clerk/clerk-react";
import { Turnstile } from "@marsidev/react-turnstile";
import { useLocation, useNavigate } from "react-router-dom";
import styles from "./login.module.css";

const MAX_TILT = 11;

const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

function getClerkError(err) {
    return (
        err?.errors?.[0]?.longMessage ||
        err?.errors?.[0]?.message ||
        err?.message ||
        "Erro ao fazer login"
    );
}

export default function LoginForm() {
    const navigate = useNavigate();
    const location = useLocation();
    
    const { isLoaded: isSignInLoaded, signIn, setActive: setSignInActive } = useSignIn();
    const { isLoaded: isSignUpLoaded, signUp, setActive: setSignUpActive } = useSignUp();
    const { isSignedIn: clerkSignedIn } = useAuth();
    const { signOut: clerkSignOut } = useClerk();
    const isLoaded = isSignInLoaded && isSignUpLoaded;

    const redirectTo = location.state?.from?.pathname || "/";
    const [captchaToken, setCaptchaToken] = useState("");
    const turnstileRef = useRef(null);

    useEffect(() => {
        if (clerkSignedIn) {
            navigate(redirectTo, { replace: true });
        }
    }, [clerkSignedIn, navigate, redirectTo]);

    const cardRef = useRef(null);
    const rippleTimerRef = useRef(new Set());

    const [isSignUpMode, setIsSignUpMode] = useState(false);
    const [pendingVerification, setPendingVerification] = useState(false);
    const [code, setCode] = useState("");
    
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    
    // Reset password states
    const [isResettingPassword, setIsResettingPassword] = useState(false);
    const [resetStep, setResetStep] = useState(""); // "request" | "verify"
    const [newPassword, setNewPassword] = useState("");
    
    const [loading, setLoading] = useState(false);
    const [googleLoading, setGoogleLoading] = useState(false);
    const [error, setError] = useState("");
    const [ripples, setRipples] = useState([]);

    useEffect(() => {
        const card = cardRef.current;
        if (!card) return undefined;

        const target = { x: 0, y: 0, mx: 50, my: 50 };
        const current = { x: 0, y: 0, mx: 50, my: 50 };
        let rafId = 0;

        const onMove = (event) => {
            const nx = event.clientX / window.innerWidth - 0.5;
            const ny = event.clientY / window.innerHeight - 0.5;
            target.x = clamp(-ny * MAX_TILT, -MAX_TILT, MAX_TILT);
            target.y = clamp(nx * MAX_TILT, -MAX_TILT, MAX_TILT);

            const rect = card.getBoundingClientRect();
            target.mx = clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100);
            target.my = clamp(((event.clientY - rect.top) / rect.height) * 100, 0, 100);
        };

        const reset = () => {
            target.x = 0;
            target.y = 0;
            target.mx = 50;
            target.my = 50;
        };

        const frame = () => {
            current.x += (target.x - current.x) * 0.07;
            current.y += (target.y - current.y) * 0.07;
            current.mx += (target.mx - current.mx) * 0.11;
            current.my += (target.my - current.my) * 0.11;
            const magnitude = Math.hypot(current.x, current.y) / MAX_TILT;
            const glowAlpha = 0.18 + magnitude * 0.22;
            const glowSize = 24 + magnitude * 24;

            card.style.transform = `rotateX(${current.x.toFixed(3)}deg) rotateY(${current.y.toFixed(3)}deg)`;
            card.style.boxShadow = `0 30px 70px rgba(2, 8, 14, 0.74), 0 0 ${glowSize.toFixed(2)}px rgba(15, 184, 216, ${glowAlpha.toFixed(3)})`;
            card.style.setProperty("--mx", `${current.mx.toFixed(2)}%`);
            card.style.setProperty("--my", `${current.my.toFixed(2)}%`);

            rafId = requestAnimationFrame(frame);
        };

        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseleave", reset);
        rafId = requestAnimationFrame(frame);

        return () => {
            cancelAnimationFrame(rafId);
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseleave", reset);
        };
    }, []);

    useEffect(
        () => () => {
            rippleTimerRef.current.forEach((timerId) => clearTimeout(timerId));
            rippleTimerRef.current.clear();
        },
        [],
    );
    
    useEffect(() => {
        const mode = isResettingPassword ? "reset" : pendingVerification ? "verify" : isSignUpMode ? "signup" : "login";
        document.body.setAttribute("data-auth-mode", mode);
        return () => document.body.removeAttribute("data-auth-mode");
    }, [isSignUpMode, pendingVerification, isResettingPassword]);

    const spawnRipple = (event) => {
        const buttonRect = event.currentTarget.getBoundingClientRect();
        const size = Math.max(buttonRect.width, buttonRect.height) * 1.24;
        const cx =
            typeof event.clientX === "number"
                ? event.clientX - buttonRect.left
                : buttonRect.width / 2;
        const cy =
            typeof event.clientY === "number"
                ? event.clientY - buttonRect.top
                : buttonRect.height / 2;
        const ripple = {
            id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
            x: cx - size / 2,
            y: cy - size / 2,
            size,
        };
        setRipples((prev) => [...prev, ripple]);

        const timeout = setTimeout(() => {
            setRipples((prev) => prev.filter((item) => item.id !== ripple.id));
            rippleTimerRef.current.delete(timeout);
        }, 680);
        rippleTimerRef.current.add(timeout);
    };

    async function handleSubmit(event) {
        event.preventDefault();
        if (!isLoaded) return;

        setLoading(true);
        setError("");

        try {
            if (isSignUpMode) {
                await signUp.create({
                    emailAddress: email.trim(),
                    password,
                    captchaToken: captchaToken || undefined,
                });

                await signUp.prepareEmailAddressVerification({ strategy: "email_code" });
                setPendingVerification(true);
            } else {
                const result = await signIn.create({
                    identifier: email.trim(),
                    password,
                });

                if (result.status === "complete" && result.createdSessionId) {
                    await setSignInActive({ session: result.createdSessionId });
                    navigate(redirectTo, { replace: true });
                    return;
                }
                setError("A autenticacao requer passos adicionais. Tente novamente.");
            }
        } catch (err) {
            const errorMsg = getClerkError(err);
            if (err?.errors?.[0]?.code === "identifier_already_signed_in" || errorMsg.toLowerCase().includes("already signed in")) {
                await clerkSignOut();
                setError("Sessão anterior limpa. Por favor, clique em Entrar novamente.");
                return;
            }
            setError(errorMsg);
        } finally {
            setLoading(false);
        }
    }

    async function handleVerify(event) {
        event.preventDefault();
        if (!isLoaded) return;

        setLoading(true);
        setError("");

        try {
            const completeSignUp = await signUp.attemptEmailAddressVerification({
                code,
            });
            if (completeSignUp.status === "complete") {
                await setSignUpActive({ session: completeSignUp.createdSessionId });
                navigate(redirectTo, { replace: true });
            } else {
                setError("Falha na verificação. Verifique o código e tente novamente.");
            }
        } catch (err) {
            setError(getClerkError(err));
        } finally {
            setLoading(false);
        }
    }

    async function handleGoogleLogin(event) {
        if (!isLoaded || !signIn) return;
        spawnRipple(event);
        setGoogleLoading(true);
        setError("");

        try {
            await signIn.authenticateWithRedirect({
                strategy: "oauth_google",
                redirectUrl: "/sso-callback",
                redirectUrlComplete: redirectTo,
            });
        } catch (err) {
            setError(getClerkError(err));
            setGoogleLoading(false);
        }
    }

    // --- Reset Password Flow ---
    async function startPasswordReset(event) {
        event.preventDefault();
        if (!isLoaded || !email) {
            setError("Por favor, informe seu email primeiro.");
            return;
        }
        setLoading(true);
        setError("");
        try {
            await signIn.create({
                strategy: "reset_password_email_code",
                identifier: email.trim(),
            });
            setIsResettingPassword(true);
            setResetStep("verify");
        } catch (err) {
            setError(getClerkError(err));
        } finally {
            setLoading(false);
        }
    }

    async function handleVerifyReset(event) {
        event.preventDefault();
        if (!isLoaded) return;
        setLoading(true);
        setError("");
        try {
            const result = await signIn.attemptFirstFactor({
                strategy: "reset_password_email_code",
                code,
                password: newPassword,
            });
            if (result.status === "complete") {
                await setSignInActive({ session: result.createdSessionId });
                navigate(redirectTo, { replace: true });
            } else {
                setError("Falha ao resetar senha. Verifique o código.");
            }
        } catch (err) {
            setError(getClerkError(err));
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className={styles.cardPerspective}>
            <section ref={cardRef} className={styles.card}>
                <div className={styles.logoWrap}>
                    <img src="/icon.png" alt="ClipBuilder" className={styles.brandIcon} />
                    <p className={styles.kicker}>
                        {isResettingPassword 
                            ? "Segurança da Conta" 
                            : pendingVerification 
                                ? "Quase lá" 
                                : isSignUpMode 
                                    ? "Comece sua jornada" 
                                    : "Portal Corporativo"}
                    </p>
                    <h1 className={styles.title}>
                        {isResettingPassword 
                            ? "Nova Senha" 
                            : pendingVerification 
                                ? "Verifique seu Email" 
                                : isSignUpMode 
                                    ? "Criar conta" 
                                    : "Entrar no ClipBuilder"}
                    </h1>
                </div>

                {error ? (
                    <div className={styles.errorBanner} role="alert" aria-live="polite">
                        {error}
                    </div>
                ) : null}

                {isResettingPassword ? (
                    <form className={styles.form} onSubmit={handleVerifyReset}>
                        <p className="mb-4 text-sm" style={{ color: "var(--text-secondary)" }}>
                            Enviamos um código para <strong>{email}</strong>. Escolha sua nova senha.
                        </p>
                        <label className={styles.field}>
                            <span>Código de Verificação</span>
                            <input
                                type="text"
                                required
                                value={code}
                                onChange={(event) => setCode(event.target.value)}
                                placeholder="Digite o código"
                            />
                        </label>
                        <label className={styles.field}>
                            <span>Nova Senha</span>
                            <input
                                type="password"
                                required
                                value={newPassword}
                                onChange={(event) => setNewPassword(event.target.value)}
                                placeholder="********"
                            />
                        </label>
                        <button
                            type="submit"
                            className={styles.submitButton}
                            disabled={loading || !isLoaded}
                        >
                            <span className={loading ? styles.hiddenText : ""}>Atualizar Senha</span>
                            {loading ? <span className={styles.spinner} aria-hidden="true" /> : null}
                        </button>
                        <button
                            type="button"
                            onClick={() => {
                                setIsResettingPassword(false);
                                setError("");
                            }}
                            className="mt-4 text-sm font-medium hover:underline transition-all w-full text-center"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            Voltar
                        </button>
                    </form>
                ) : !pendingVerification ? (
                    <>
                        <button
                            type="button"
                            className={`${styles.googleButton} ${styles.btnGoogle}`}
                            onClick={handleGoogleLogin}
                            disabled={loading || googleLoading}
                        >
                            {ripples.map((ripple) => (
                                <span
                                    key={ripple.id}
                                    className={styles.ripple}
                                    style={{
                                        left: ripple.x,
                                        top: ripple.y,
                                        width: ripple.size,
                                        height: ripple.size,
                                    }}
                                />
                            ))}
                            <span className={styles.googleIcon} aria-hidden="true">
                                G
                            </span>
                            <span>{googleLoading ? "A redirecionar..." : "Continuar com Google"}</span>
                        </button>

                        <div className={`${styles.divider} ${styles.dividerWrap}`}>
                            <span>ou use o seu email</span>
                        </div>

                        <form className={styles.form} onSubmit={handleSubmit}>
                            <label className={styles.field}>
                                <span>Email</span>
                                <input
                                    type="email"
                                    autoComplete="email"
                                    required
                                    value={email}
                                    onChange={(event) => setEmail(event.target.value)}
                                    placeholder="voce@clipbuilder.com.br"
                                />
                            </label>

                            <label className={styles.field}>
                                <div className="flex justify-between items-center mb-1">
                                    <span>Senha</span>
                                    {!isSignUpMode && (
                                        <button 
                                            type="button"
                                            onClick={startPasswordReset}
                                            className="text-xs font-medium hover:underline"
                                            style={{ color: "var(--accent)" }}
                                        >
                                            Esqueci a senha
                                        </button>
                                    )}
                                </div>
                                <div className={styles.passwordWrap}>
                                    <input
                                        type={showPassword ? "text" : "password"}
                                        autoComplete={isSignUpMode ? "new-password" : "current-password"}
                                        required
                                        value={password}
                                        onChange={(event) => setPassword(event.target.value)}
                                        placeholder="********"
                                        className={styles.passwordInput}
                                    />
                                    <button
                                        type="button"
                                        className={styles.passwordToggle}
                                        aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                                        onClick={() => setShowPassword((prev) => !prev)}
                                    >
                                        <svg
                                            viewBox="0 0 24 24"
                                            className={`${styles.eyeIcon} ${showPassword ? styles.eyeOn : ""}`}
                                            aria-hidden="true"
                                        >
                                            <path d="M2.25 12s3.5-6.75 9.75-6.75S21.75 12 21.75 12 18.25 18.75 12 18.75 2.25 12 2.25 12Z" />
                                            <circle cx="12" cy="12" r="3.15" />
                                            <path d="M4 20 20 4" className={styles.eyeStrike} />
                                        </svg>
                                    </button>
                                </div>
                            </label>
                            
                            {isSignUpMode && import.meta.env.VITE_TURNSTILE_SITE_KEY && (
                                <div className="flex justify-center mb-4">
                                    <Turnstile
                                        ref={turnstileRef}
                                        siteKey={import.meta.env.VITE_TURNSTILE_SITE_KEY}
                                        onSuccess={(token) => setCaptchaToken(token)}
                                        onExpire={() => setCaptchaToken("")}
                                        onError={() => setCaptchaToken("")}
                                        options={{
                                            theme: "dark",
                                        }}
                                    />
                                </div>
                            )}

                            <button
                                type="submit"
                                className={styles.submitButton}
                                disabled={loading || googleLoading || !isLoaded}
                            >
                                <span className={loading ? styles.hiddenText : ""}>
                                    {isSignUpMode ? "Criar Conta" : "Continuar"}
                                </span>
                                <svg
                                    viewBox="0 0 24 24"
                                    aria-hidden="true"
                                    className={`${styles.arrowIcon} ${loading ? styles.hiddenIcon : ""}`}
                                >
                                    <path d="M5 12h14M13 6l6 6-6 6" />
                                </svg>
                                {loading ? <span className={styles.spinner} aria-hidden="true" /> : null}
                            </button>
                        </form>
                        
                        <div className="mt-6 text-center text-sm" style={{ color: "var(--text-secondary)" }}>
                            {isSignUpMode ? (
                                <>
                                    Já tem uma conta?{" "}
                                    <button 
                                        type="button"
                                        onClick={() => { setIsSignUpMode(false); setError(""); }}
                                        className="font-medium hover:underline transition-all"
                                        style={{ color: "var(--accent)" }}
                                    >
                                        Entrar
                                    </button>
                                </>
                            ) : (
                                <>
                                    Ainda não tem conta?{" "}
                                    <button 
                                        type="button"
                                        onClick={() => { setIsSignUpMode(true); setError(""); }}
                                        className="font-medium hover:underline transition-all"
                                        style={{ color: "var(--accent)" }}
                                    >
                                        Criar agora
                                    </button>
                                </>
                            )}
                        </div>
                        
                        <div className="mt-4 text-center">
                            <button
                                type="button"
                                onClick={async () => {
                                    setLoading(true);
                                    try {
                                        await clerkSignOut();
                                        setError("Sessões limpas com sucesso. Tente novamente.");
                                        window.location.reload();
                                    } catch (err) {
                                        setError("Erro ao limpar: " + String(err));
                                    } finally {
                                        setLoading(false);
                                    }
                                }}
                                className="text-xs font-medium hover:underline transition-all"
                                style={{ color: "var(--danger, #f43f5e)", opacity: 0.8 }}
                                title="Se você estiver preso num loop ou recebendo erros de sessão, clique aqui para resetar o Clerk."
                            >
                                Limpar Sessões Travadas
                            </button>
                        </div>
                    </>
                ) : (
                    <form className={styles.form} onSubmit={handleVerify}>
                        <p className="mb-4 text-sm" style={{ color: "var(--text-secondary)" }}>
                            Enviamos um código de verificação para <strong>{email}</strong>.
                        </p>
                        <label className={styles.field}>
                            <span>Código de Verificação</span>
                            <input
                                type="text"
                                required
                                value={code}
                                onChange={(event) => setCode(event.target.value)}
                                placeholder="Digite o código"
                            />
                        </label>
                        <button
                            type="submit"
                            className={styles.submitButton}
                            disabled={loading || !isLoaded || !code}
                        >
                            <span className={loading ? styles.hiddenText : ""}>Verificar</span>
                            {loading ? <span className={styles.spinner} aria-hidden="true" /> : null}
                        </button>
                        <button
                            type="button"
                            onClick={() => {
                                setPendingVerification(false);
                                setError("");
                            }}
                            className="mt-4 text-sm font-medium hover:underline transition-all w-full text-center"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            Voltar
                        </button>
                    </form>
                )}
            </section>
        </div>
    );
}

