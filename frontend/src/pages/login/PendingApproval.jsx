import React from "react";
import { useAppAuth } from "../../utils/AuthContext";

export default function PendingApproval() {
    const { signOut } = useAppAuth();

    return (
        <div
            className="cb-app-shell min-h-screen flex items-center justify-center p-4"
            style={{ backgroundColor: "var(--bg)", color: "var(--text)" }}
        >
            <div className="text-center max-w-md animate-in fade-in zoom-in duration-500">
                <div className="mb-6">
                    <div className="mx-auto w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: "rgba(15, 184, 216, 0.1)" }}>
                        <svg className="w-8 h-8" style={{ color: "var(--accent)" }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                    </div>
                </div>
                <h2 className="text-2xl font-bold mb-3 tracking-tight">Aguardando Aprovação</h2>
                <p
                    className="mb-8 leading-relaxed"
                    style={{ color: "var(--text-secondary)" }}
                >
                    A sua conta foi criada com sucesso, mas precisa ser aprovada por um administrador antes de poder acessar a plataforma.
                </p>

                <div className="flex flex-col gap-3">
                    <button
                        onClick={signOut}
                        className="cb-btn px-6 py-2.5 rounded-lg font-medium transition-all"
                        style={{ backgroundColor: "var(--surface)", border: "1px solid var(--border)" }}
                    >
                        Sair
                    </button>
                </div>
            </div>
        </div>
    );
}
