/**
 * Tela de carregamento/erro usada enquanto a sessão é verificada.
 *
 * Vive num módulo próprio (e não dentro de App.jsx) para que as páginas possam
 * importá-la sem criar um ciclo de importação com o roteador.
 */
export default function AuthLoading({
    message = "A verificar sessão...",
    error = null,
    onRetry = null,
}) {
    return (
        <div
            className="cb-app-shell min-h-screen flex items-center justify-center p-4 transition-colors duration-300"
            style={{ backgroundColor: "var(--bg)", color: "var(--text)" }}
        >
            <div className="text-center max-w-sm animate-in fade-in zoom-in duration-500">
                {error ? (
                    <>
                        <div className="mb-6 text-4xl animate-bounce">⚠️</div>
                        <h2 className="text-xl font-semibold mb-2">Erro de Ligação</h2>
                        <p
                            className="text-sm mb-8 leading-relaxed"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            {error.message || "Ocorreu um erro ao contactar o servidor."}
                        </p>

                        <div className="flex flex-col gap-3">
                            {onRetry && (
                                <button
                                    onClick={onRetry}
                                    className="cb-btn cb-btn-primary px-6 py-2.5 rounded-lg font-medium transition-all hover:scale-105 active:scale-95"
                                >
                                    Tentar Novamente
                                </button>
                            )}

                            <a
                                href="/login"
                                className="text-xs font-medium opacity-50 hover:opacity-100 transition-opacity"
                                style={{ color: "var(--text-secondary)" }}
                            >
                                Voltar ao Login
                            </a>
                        </div>
                    </>
                ) : (
                    <>
                        <div
                            className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-current border-r-transparent align-[-0.125em] motion-reduce:animate-[spin_1.5s_linear_infinite]"
                            style={{
                                borderColor: "var(--accent)",
                                borderRightColor: "transparent",
                            }}
                        />
                        <p
                            className="mt-6 text-sm font-medium tracking-wide animate-pulse"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            {message}
                        </p>
                    </>
                )}
            </div>
        </div>
    );
}
