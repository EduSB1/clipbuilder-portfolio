import React from 'react'

export default class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props)
        this.state = { hasError: false, error: null }
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error }
    }

    componentDidCatch(error, errorInfo) {
        console.error('[ErrorBoundary] Erro capturado:', error, errorInfo)
    }

    render() {
        if (this.state.hasError) {
            return (
                <div style={{
                    minHeight: '100vh',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: '#0f172a',
                    color: '#e2e8f0',
                    fontFamily: 'system-ui, -apple-system, sans-serif',
                }}>
                    <div style={{
                        textAlign: 'center',
                        maxWidth: 420,
                        padding: '2rem',
                    }}>
                        <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>⚠️</div>
                        <h1 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                            Algo deu errado
                        </h1>
                        <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginBottom: '2rem' }}>
                            Ocorreu um erro inesperado. Clique abaixo para recarregar a página.
                        </p>

                        <div style={{ display: 'flex', justifyContent: 'center' }}>
                            <button
                                onClick={() => window.location.reload()}
                                style={{
                                    padding: '0.625rem 1.5rem',
                                    borderRadius: '0.5rem',
                                    border: 'none',
                                    background: '#3b82f6',
                                    color: '#fff',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    fontSize: '0.875rem',
                                }}
                            >
                                Recarregar Página
                            </button>
                        </div>
                    </div>
                </div>
            )
        }

        return this.props.children
    }
}
