import React, { useState, useRef, useEffect } from "react";
import { Shield, LogOut, Zap, ChevronDown, User, Settings } from "lucide-react";
import { Link } from "react-router-dom";
import useCredits from "../../hooks/useCredits";
import Logo from "./Logo";
import ThemeToggle from "./ThemeToggle";
import EditAccountModal from "../modals/EditAccountModal";

export default function Header({ user, onLogout }) {
    const { credits, loading: creditsLoading } = useCredits();
    const [menuOpen, setMenuOpen] = useState(false);
    const [editAccountOpen, setEditAccountOpen] = useState(false);
    const menuRef = useRef(null);

    const userEmail = user?.email || "";
    const displayName = user?.full_name?.trim() || userEmail.split("@")[0] || "";
    const userInitials = (displayName || userEmail || "U").trim().slice(0, 2).toUpperCase();

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (menuRef.current && !menuRef.current.contains(event.target)) {
                setMenuOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    return (
        <header className="cb-header animate-fade-in">
            <div className="cb-header-inner">
                <div className="flex items-center gap-3">
                    <Logo size={30} showText />
                </div>

                <div className="flex items-center gap-3">
                    {user?.role === "admin" && (
                        <Link to="/admin" className="cb-pill-link hidden sm:flex" title="Painel Admin">
                            <Shield size={14} style={{ color: "var(--accent)" }} />
                            <span className="text-xs font-medium">Admin</span>
                        </Link>
                    )}

                    {userEmail && user?.role !== "admin" && (
                        <Link to="/credits" className="cb-pill-link credits-pill" title="Gerenciar créditos">
                            <Zap size={12} />
                            <span className="text-xs font-semibold">{creditsLoading ? "…" : (credits ?? 0)}</span>
                        </Link>
                    )}

                    {userEmail ? (
                        <div className="user-menu-container" ref={menuRef}>
                            <button 
                                type="button"
                                className="user-menu-trigger" 
                                onClick={() => setMenuOpen(!menuOpen)}
                                aria-expanded={menuOpen}
                                aria-haspopup="true"
                            >
                                <div className="user-avatar" aria-hidden="true">
                                    {userInitials}
                                </div>
                                <span className="user-name hidden md:inline">{displayName}</span>
                                <ChevronDown size={14} className={`transition-transform duration-200 ${menuOpen ? 'rotate-180' : ''}`} style={{ color: "var(--text-muted)" }} />
                            </button>

                            {menuOpen && (
                                <div className="user-menu-dropdown animate-scale-in">
                                    <div className="user-menu-header">
                                        <div className="font-semibold text-sm truncate" style={{ color: "var(--text-primary)" }}>{displayName}</div>
                                        <span className="user-menu-email">{userEmail}</span>
                                    </div>
                                    
                                    <div className="user-menu-theme-item">
                                        <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Aparência</span>
                                        <ThemeToggle />
                                    </div>

                                    <div className="user-menu-divider" />
                                    
                                    <button 
                                        type="button" 
                                        className="user-menu-item"
                                        onClick={() => { setMenuOpen(false); setEditAccountOpen(true); }}
                                    >
                                        <User size={14} />
                                        Editar Conta
                                    </button>
                                    
                                    {user?.role === "admin" && (
                                        <Link to="/admin" className="user-menu-item sm:hidden" onClick={() => setMenuOpen(false)}>
                                            <Shield size={14} />
                                            Painel Admin
                                        </Link>
                                    )}

                                    <button 
                                        type="button"
                                        className="user-menu-item danger" 
                                        onClick={() => { setMenuOpen(false); onLogout?.(); }}
                                    >
                                        <LogOut size={14} />
                                        Sair da conta
                                    </button>
                                </div>
                            )}
                        </div>
                    ) : null}
                </div>
            </div>

            <EditAccountModal 
                open={editAccountOpen} 
                onClose={() => setEditAccountOpen(false)} 
            />
        </header>
    );
}
