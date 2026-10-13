import React from 'react'
import { X, Download, Plus } from 'lucide-react'
import GifStepPreview from '../video/GifStepPreview'

export default function GifPreviewModal({
    isOpen,
    onClose,
    gifUrl,
    gifBlob,
    onAddToDoc,
    onDownload,
    isGenerating,
    progress,
    gifDescribeLoading = false,
    onGenerateDoc = null,
    isGeneratingDoc = false,
    generationStage = ''
}) {
    if (!isOpen) return null

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="gif-preview-title"
                className="relative w-full max-w-2xl mx-4 rounded-xl border shadow-2xl"
                style={{
                    backgroundColor: 'var(--card-bg)',
                    borderColor: 'var(--panel-border)'
                }}
            >
                {/* Header */}
                <div
                    className="flex items-center justify-between gap-3 px-5 py-4 border-b"
                    style={{ borderColor: 'var(--panel-border)' }}
                >
                    <h2 id="gif-preview-title" className="text-lg font-semibold" style={{ color: 'var(--text)' }}>
                        {isGenerating ? 'Montando seu GIF…' : 'Seu GIF está pronto'}
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-1.5 rounded-lg transition-colors hover:bg-[var(--accent-light)]"
                        style={{ color: 'var(--text-secondary)' }}
                        disabled={isGenerating}
                        aria-label="Fechar"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-5">
                    {isGenerating ? (
                        <div className="flex flex-col items-center justify-center py-12">
                            <div className="relative mb-4">
                                <svg className="h-16 w-16 animate-spin" style={{ color: 'var(--accent)' }} viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
                                </svg>
                            </div>
                            <div className="text-base font-medium mb-2" style={{ color: 'var(--text)' }}>
                                Montando os frames…
                            </div>
                            <div className="w-64 h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--panel-border)' }}>
                                <div
                                    className="h-full transition-all duration-300 rounded-full"
                                    style={{
                                        width: `${Math.round(progress * 100)}%`,
                                        backgroundColor: 'var(--accent)'
                                    }}
                                />
                            </div>
                            <div className="text-sm mt-2" style={{ color: 'var(--text-secondary)' }}>
                                {Math.round(progress * 100)}%
                            </div>
                            <div className="text-xs mt-1" style={{ color: 'var(--muted-text)' }}>
                                Isso pode levar alguns segundos
                            </div>
                        </div>
                    ) : gifUrl ? (
                        <div className="flex flex-col items-center">
                            <div
                                className="rounded-lg overflow-hidden border mb-4 w-full flex justify-center"
                                style={{ borderColor: 'var(--panel-border)', backgroundColor: '#000' }}
                            >
                                <GifStepPreview
                                    gifUrl={gifUrl}
                                    alt="GIF Preview"
                                    className="max-w-full max-h-[400px]"
                                    imgClassName="max-w-full max-h-[400px] object-contain"
                                />
                            </div>
                            {gifBlob && (
                                <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                                    Tamanho: {(gifBlob.size / 1024).toFixed(1)} KB
                                </div>
                            )}
                        </div>
                    ) : null}
                </div>

                {/* Footer */}
                {!isGenerating && gifUrl && (
                    <div
                        className="flex items-center justify-end gap-3 px-5 py-4 border-t"
                        style={{ borderColor: 'var(--panel-border)' }}
                    >
                        <button
                            onClick={onClose}
                            className="cb-btn cb-btn-secondary"
                        >
                            Cancelar
                        </button>
                        <button
                            onClick={onDownload}
                            className="cb-btn cb-btn-secondary flex items-center gap-2"
                        >
                            <Download className="h-4 w-4" />
                            Baixar
                        </button>
                        <button
                            onClick={onAddToDoc}
                            disabled={gifDescribeLoading || isGeneratingDoc}
                            className="cb-btn cb-btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <Plus className="h-4 w-4" />
                            {gifDescribeLoading ? 'Criando descrição…' : 'Incluir nos passos'}
                        </button>

                    </div>
                )}
            </div>
        </div>
    )
}
