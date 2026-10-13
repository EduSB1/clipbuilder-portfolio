import React from "react";
import { useNavigate } from "react-router-dom";
import { Zap, ShoppingCart, X } from "lucide-react";

/**
 * Modal displayed when an API call returns HTTP 402 (insufficient credits).
 *
 * Props:
 *   - open: boolean — whether the modal is visible
 *   - onClose: () => void — called when the user dismisses the modal
 *   - detail: string | null — optional detail message from the API response
 */
export default function InsufficientCreditsModal({ open, onClose, detail }) {
  const navigate = useNavigate();

  if (!open) return null;

  function handleBuyCredits() {
    onClose();
    navigate("/credits");
  }

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0, 0, 0, 0.6)", backdropFilter: "blur(4px)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="relative w-full max-w-md rounded-2xl border shadow-2xl"
        style={{
          backgroundColor: "var(--card-bg, #111)",
          borderColor: "var(--card-border, #222)",
        }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="credits-modal-title"
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded-lg transition-colors hover:opacity-80"
          style={{ color: "var(--muted-text, #666)" }}
          aria-label="Fechar"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="px-6 pt-8 pb-6 text-center">
          {/* Icon */}
          <div
            className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full"
            style={{
              background: "linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(239, 68, 68, 0.15))",
            }}
          >
            <Zap className="h-8 w-8" style={{ color: "#f59e0b" }} />
          </div>

          {/* Title */}
          <h2
            id="credits-modal-title"
            className="text-xl font-semibold mb-2"
            style={{ color: "var(--text, #f1f5f9)" }}
          >
            Seus créditos acabaram{" "}
            <span role="img" aria-label="triste">
              😕
            </span>
          </h2>

          {/* Description */}
          <p
            className="text-sm mb-6 leading-relaxed"
            style={{ color: "var(--text-secondary, #94a3b8)" }}
          >
            {detail ||
              "Adquira mais créditos para continuar gerando tutoriais e usando as funcionalidades de IA."}
          </p>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={handleBuyCredits}
              className="flex-1 flex items-center justify-center gap-2 py-3 px-5 rounded-xl text-sm font-semibold transition-all duration-150"
              style={{
                backgroundColor: "var(--accent, #0d9488)",
                color: "#fff",
              }}
            >
              <ShoppingCart className="h-4 w-4" />
              Comprar Créditos
            </button>
            <button
              onClick={onClose}
              className="flex-1 py-3 px-5 rounded-xl text-sm font-medium border transition-all duration-150"
              style={{
                backgroundColor: "transparent",
                borderColor: "var(--panel-border, #252525)",
                color: "var(--text-secondary, #94a3b8)",
              }}
            >
              Cancelar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
