import React from 'react'
import GifStepPreview from './GifStepPreview'

export default function StepCard({ s, idx, updateDescription, generateWithAI, removeStep, aiStepBusyId, darkMode, videoId, aiStatus }) {
  const hasTimestamp = Boolean((s?.timestamp || '').trim())

  return (
    <div className={`rounded-md border p-12 cb-panel`} style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--card-border)', color: 'var(--text)' }}>
      <div className="flex flex-col items-start gap-6">
        {s?.url ? (
          s.is_gif ? (
            <div className="w-full h-96 rounded overflow-hidden">
              <GifStepPreview
                gifUrl={s.url}
                thumbnailUrl={s.thumbnailUrl}
                alt={`Passo ${idx + 1}`}
                className="w-full h-full"
                imgClassName="w-full h-96 object-cover rounded"
              />
            </div>
          ) : (
            <img src={s.url} alt={`Passo ${idx + 1}`} className="w-full h-96 rounded object-cover" />
          )
        ) : (
          <div className="w-full h-96 rounded border flex items-center justify-center" style={{ borderColor: 'var(--card-border)', color: 'var(--muted-text)' }}>
            Passo sem imagem
          </div>
        )}
        <div className="min-w-0 flex-1 w-full">
          <div className="mb-4 text-3xl font-bold">Passo {idx + 1}{hasTimestamp ? ` • ${s.timestamp}` : ''}</div>
          <textarea
            className={`w-full resize-none rounded-md border px-6 py-5 text-xl outline-none focus:ring-2 ${darkMode ? 'focus:ring-gray-600 text-slate-100' : 'focus:ring-slate-200'}`}
            style={{ backgroundColor: 'var(--card-bg)', borderColor: 'var(--card-border)', color: 'var(--text)' }}
            rows={12}
            placeholder="Descreva o passo..."
            value={s.description}
            onChange={(e) => updateDescription(s.id, e.target.value)}
          />
          <div className="mt-6 flex gap-4">
            <button
              className="cb-btn cb-btn-primary px-6 py-4 text-xl"
              onClick={() => generateWithAI(s.id)}
              type="button"
              disabled={!videoId || (!hasTimestamp && !s.is_gif) || aiStatus !== 'ready' || aiStepBusyId === s.id}
            >
              {aiStepBusyId === s.id ? 'Gerando...' : 'Gerar com IA'}
            </button>
            <button
              className="cb-btn cb-btn-danger px-6 py-4 text-xl"
              onClick={() => removeStep(s.id)}
              type="button"
            >
              Excluir
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
