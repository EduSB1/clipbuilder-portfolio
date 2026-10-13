import React, { useState, useEffect } from "react";
import { X, User, Save, ExternalLink } from "lucide-react";
import { useAppAuth } from "../../utils/AuthContext";

export default function EditAccountModal({ open, onClose }) {
    const { user, updateProfile, openExternalProfile, mode } = useAppAuth();
    
    const [fullName, setFullName] = useState("");
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState({ type: "", text: "" });

    useEffect(() => {
        if (open && user) {
            setFullName(user.full_name || "");
            setMessage({ type: "", text: "" });
        }
    }, [open, user]);

    if (!open) return null;

    const handleSave = async (e) => {
        e.preventDefault();
        setLoading(true);
        setMessage({ type: "", text: "" });

        const res = await updateProfile({ full_name: fullName });
        
        if (res.success) {
            setMessage({ type: "success", text: "Perfil atualizado com sucesso!" });
            setTimeout(() => {
                onClose();
            }, 1500);
        } else {
            setMessage({ type: "error", text: res.error });
        }
        setLoading(false);
    };

    return (
        <div 
            className="cb-modal-overlay fixed inset-0 z-[1000] flex items-center justify-center p-4" 
            onClick={onClose}
        >
            <div 
                className="cb-modal w-full max-w-md animate-scale-in" 
                onClick={(e) => e.stopPropagation()}
            >
                <div className="cb-modal-header flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <User size={18} className="text-accent" />
                        <h2 className="cb-modal-title">Editar Conta</h2>
                    </div>
                    <button onClick={onClose} className="p-1.5 hover:bg-white/10 rounded-lg transition-colors text-muted">
                        <X size={18} />
                    </button>
                </div>

                <form onSubmit={handleSave} className="cb-modal-body space-y-5">
                    {message.text && (
                        <div className={`p-3 rounded-lg text-sm border ${
                            message.type === "success" 
                            ? "bg-green-500/10 text-green-400 border-green-500/20" 
                            : "bg-red-500/10 text-red-400 border-red-500/20"
                        }`}>
                            {message.text}
                        </div>
                    )}

                    <div className="space-y-4">
                        <div className="space-y-1.5">
                            <label className="text-xs font-semibold uppercase tracking-wider text-muted px-1">Email</label>
                            <input 
                                type="text" 
                                value={user?.email || ""} 
                                disabled
                                className="cb-input w-full opacity-60 cursor-not-allowed"
                                style={{ background: "rgba(0,0,0,0.1)" }}
                            />
                            <p className="text-[10px] px-1 italic" style={{ color: "var(--text-muted)" }}>* O email não pode ser alterado por segurança.</p>
                        </div>

                        <div className="space-y-1.5">
                            <label className="text-xs font-semibold uppercase tracking-wider text-primary px-1">Nome Completo</label>
                            <input 
                                type="text" 
                                value={fullName}
                                onChange={(e) => setFullName(e.target.value)}
                                placeholder="Seu nome completo"
                                className="cb-input w-full"
                                required
                                autoFocus
                            />
                        </div>
                    </div>

                    {mode === "clerk" && (
                        <div className="pt-2">
                            <button
                                type="button"
                                onClick={() => {
                                    onClose();
                                    openExternalProfile?.();
                                }}
                                className="cb-btn w-full text-xs"
                            >
                                <ExternalLink size={14} />
                                Gerenciar via Clerk (Foto, Segurança)
                            </button>
                        </div>
                    )}

                    <div className="cb-modal-footer pt-2">
                        <button 
                            type="button" 
                            onClick={onClose}
                            className="cb-btn px-6"
                        >
                            Cancelar
                        </button>
                        <button 
                            type="submit"
                            disabled={loading}
                            className="cb-btn-primary px-8"
                        >
                            {loading ? (
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    <Save size={16} />
                                    Salvar Alterações
                                </>
                            )}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
