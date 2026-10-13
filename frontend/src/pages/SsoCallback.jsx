import { AuthenticateWithRedirectCallback } from "@clerk/clerk-react";

export default function SsoCallback() {
    return (
        <div
            className="cb-app-shell"
            style={{
                minHeight: "100vh",
                display: "grid",
                placeItems: "center",
                background: "var(--bg)",
                color: "var(--text)",
                fontFamily: "'DM Sans', sans-serif",
            }}
        >
            <div style={{ textAlign: "center" }}>
                <div
                    style={{
                        width: 28,
                        height: 28,
                        borderRadius: "50%",
                        border: "2px solid rgba(221, 234, 244, 0.28)",
                        borderTopColor: "var(--accent)",
                        margin: "0 auto 10px",
                        animation: "spin 0.8s linear infinite",
                    }}
                />
                <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 14 }}>A concluir login...</p>
                <AuthenticateWithRedirectCallback signInForceRedirectUrl="/" signUpForceRedirectUrl="/" />
            </div>
            <style>{`
                @keyframes spin {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
}
