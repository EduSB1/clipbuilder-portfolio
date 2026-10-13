import { useState, useEffect, useMemo } from "react";
import { api } from "../../utils/api";
import {
    FileText, Plus, Trash2, Users, Shield, ShieldCheck,
    Loader2, Save, X, CheckCircle2, Search, ChevronRight,
} from "lucide-react";

// ─── Sub-tab constants ──────────────────────────────────────────────
const SUB_TABS = [
    { id: "overview", label: "Templates Cadastrados", icon: FileText },
    { id: "permissions", label: "Permissões por Usuário", icon: Shield },
    { id: "import", label: "Importar Template", icon: Plus },
];

// ─── Main TemplatesTab ──────────────────────────────────────────────
export default function TemplatesTab({
    users: usersProp,
    templates,
    setTemplates,
    toast,
    openTemplatesModal,
    saveUserTemplates,
    templateSaving,
}) {
    const [subTab, setSubTab] = useState("overview");
    const [adminTemplates, setAdminTemplates] = useState([]);
    const [loading, setLoading] = useState(false);
    const [allUsers, setAllUsers] = useState([]);

    // Fetch admin templates with user counts
    const fetchAdminTemplates = async () => {
        setLoading(true);
        try {
            const res = await api.get("/admin/templates");
            setAdminTemplates(res.data?.templates || []);
        } catch (e) {
            console.error("Erro ao carregar templates admin:", e);
        } finally {
            setLoading(false);
        }
    };

    // Fetch all users for permissions view
    const fetchAllUsers = async () => {
        try {
            const res = await api.get("/admin/users", { params: { page: 1, page_size: 500, status: "todos" } });
            setAllUsers(res.data?.users || []);
        } catch (e) {
            console.error("Erro ao carregar usuários:", e);
        }
    };

    useEffect(() => {
        fetchAdminTemplates();
        fetchAllUsers();
    }, []);

    return (
        <div className="space-y-6">
            {/* Sub-tab navigation */}
            <div className="flex gap-2 flex-wrap">
                {SUB_TABS.map(({ id, label, icon: Icon }) => (
                    <button
                        key={id}
                        onClick={() => setSubTab(id)}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
                        style={{
                            backgroundColor: subTab === id ? "var(--accent)" : "rgba(255,255,255,0.04)",
                            color: subTab === id ? "#fff" : "var(--muted-text)",
                            border: `1px solid ${subTab === id ? "var(--accent)" : "var(--panel-border)"}`,
                        }}
                    >
                        <Icon className="h-4 w-4" />
                        {label}
                    </button>
                ))}
            </div>

            {subTab === "overview" && (
                <OverviewSubTab
                    templates={adminTemplates}
                    loading={loading}
                    toast={toast}
                    onRefresh={fetchAdminTemplates}
                />
            )}
            {subTab === "permissions" && (
                <PermissionsSubTab
                    users={allUsers}
                    templates={templates}
                    toast={toast}
                    openTemplatesModal={openTemplatesModal}
                    saveUserTemplates={saveUserTemplates}
                    templateSaving={templateSaving}
                    onRefresh={fetchAllUsers}
                />
            )}
            {subTab === "import" && (
                <ImportSubTab
                    toast={toast}
                    onCreated={() => {
                        fetchAdminTemplates();
                        // Also refresh the global templates list
                        api.get("/templates")
                            .then((res) => setTemplates(res.data?.templates || []))
                            .catch(() => {});
                    }}
                />
            )}
        </div>
    );
}

// ─── Overview: List all templates ───────────────────────────────────
function OverviewSubTab({ templates, loading, toast, onRefresh }) {
    const [deleting, setDeleting] = useState(null);

    const handleDelete = async (id) => {
        if (!confirm(`Excluir template "${id}"? Esta ação não pode ser desfeita.`)) return;
        setDeleting(id);
        try {
            await api.delete(`/admin/templates/${id}`);
            toast.success("Template excluído com sucesso.");
            onRefresh();
        } catch (e) {
            const msg = e?.response?.data?.detail || "Falha ao excluir template.";
            toast.error(msg);
        } finally {
            setDeleting(null);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-16" style={{ color: "var(--muted-text)" }}>
                <Loader2 className="h-6 w-6 animate-spin mr-3" />
                Carregando templates...
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-base font-semibold" style={{ color: "var(--text)" }}>
                        Templates Cadastrados
                    </h3>
                    <p className="text-xs mt-1" style={{ color: "var(--muted-text)" }}>
                        {templates.length} template(s) registrado(s) no sistema.
                    </p>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {templates.map((t) => (
                    <div
                        key={t.id}
                        className="rounded-xl border p-5 transition-all hover:shadow-lg"
                        style={{
                            backgroundColor: "var(--card-bg)",
                            borderColor: "var(--card-border)",
                        }}
                    >
                        <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-3">
                                <div
                                    className="h-10 w-10 rounded-lg flex items-center justify-center text-lg overflow-hidden"
                                    style={{
                                        backgroundColor: t.is_builtin ? "var(--accent)" : "rgba(168,85,247,0.2)",
                                        color: t.is_builtin ? "#fff" : "#a855f7",
                                    }}
                                >
                                    {t.logo_path ? (
                                        <img src={t.logo_path} alt={t.name} className="h-full w-full object-contain p-1 bg-white/5" />
                                    ) : (
                                        t.icon || "📄"
                                    )}
                                </div>
                                <div>
                                    <h4 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                                        {t.name}
                                    </h4>
                                    <span
                                        className="text-[10px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider"
                                        style={{
                                            backgroundColor: t.category === "corporate" ? "#1F4E79" : t.category === "custom" ? "#7c3aed" : "var(--card-border)",
                                            color: t.category === "corporate" || t.category === "custom" ? "#fff" : "var(--muted-text)",
                                        }}
                                    >
                                        {t.category === "corporate" ? "Corporativo" : t.category === "custom" ? "Customizado" : "Geral"}
                                    </span>
                                </div>
                            </div>
                            {!t.is_builtin && (
                                <button
                                    onClick={() => handleDelete(t.id)}
                                    disabled={deleting === t.id}
                                    className="p-1.5 rounded-lg hover:bg-red-500/10 transition-colors"
                                    style={{ color: "#ef4444" }}
                                    title="Excluir template"
                                >
                                    {deleting === t.id ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Trash2 className="h-4 w-4" />
                                    )}
                                </button>
                            )}
                        </div>

                        <p className="text-xs leading-relaxed mb-3" style={{ color: "var(--muted-text)" }}>
                            {t.description || "Sem descrição."}
                        </p>

                        {/* Stats row */}
                        <div className="flex items-center gap-3 text-[11px]" style={{ color: "var(--muted-text)" }}>
                            {t.is_builtin && (
                                <span className="flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ backgroundColor: "rgba(34,197,94,0.1)", color: "#22c55e" }}>
                                    <ShieldCheck className="h-3 w-3" /> Nativo
                                </span>
                            )}
                            {t.has_logo && <span>🏢 Com Logo</span>}
                            {t.sections && <span>{t.sections.length} seções</span>}
                            {typeof t.user_count_restricted === "number" && (
                                <span className="flex items-center gap-1">
                                    <Users className="h-3 w-3" />
                                    {t.user_count_allowed}/{t.user_count_restricted} usuários
                                </span>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {templates.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 opacity-40">
                    <FileText className="h-12 w-12 mb-3" />
                    <p className="text-sm">Nenhum template encontrado.</p>
                </div>
            )}
        </div>
    );
}

// ─── Permissions: Per-user template access ──────────────────────────
function PermissionsSubTab({ users, templates, toast, openTemplatesModal, saveUserTemplates, templateSaving, onRefresh }) {
    const [searchTerm, setSearchTerm] = useState("");
    const [bulkEnabled, setBulkEnabled] = useState(false);
    const [bulkIds, setBulkIds] = useState([]);
    const [bulkSaving, setBulkSaving] = useState(false);

    const filteredUsers = useMemo(() => {
        if (!searchTerm) return users.filter(u => u.role !== "admin");
        const term = searchTerm.toLowerCase();
        return users.filter(u => u.role !== "admin" && (
            (u.email || "").toLowerCase().includes(term) ||
            (u.full_name || "").toLowerCase().includes(term)
        ));
    }, [users, searchTerm]);

    const handleBulkSave = async () => {
        if (filteredUsers.length === 0) return;
        setBulkSaving(true);
        try {
            const promises = filteredUsers.map(u =>
                api.put(`/admin/users/${u.id}/permissions`, {
                    template_permissions_enabled: bulkEnabled,
                    allowed_templates: JSON.stringify(bulkIds),
                })
            );
            await Promise.all(promises);
            toast.success(`Permissões atualizadas para ${filteredUsers.length} usuário(s).`);
            onRefresh();
        } catch (e) {
            toast.error("Falha ao atualizar permissões em lote.");
        } finally {
            setBulkSaving(false);
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <h3 className="text-base font-semibold" style={{ color: "var(--text)" }}>
                        Permissões por Usuário
                    </h3>
                    <p className="text-xs mt-1" style={{ color: "var(--muted-text)" }}>
                        Gerencie quais templates cada usuário pode acessar. Admins têm acesso total.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative">
                        <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--muted-text)" }} />
                        <input
                            type="text"
                            placeholder="Buscar usuário..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="cb-input pl-9 text-sm"
                            style={{ width: "220px" }}
                        />
                    </div>
                </div>
            </div>

            {/* Users table */}
            <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--panel-border)" }}>
                <table className="w-full text-sm">
                    <thead>
                        <tr style={{ backgroundColor: "rgba(0,0,0,0.2)" }}>
                            <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted-text)" }}>Usuário</th>
                            <th className="text-center px-4 py-3 font-medium" style={{ color: "var(--muted-text)" }}>Templates Permitidos</th>
                            <th className="text-right px-4 py-3 font-medium" style={{ color: "var(--muted-text)" }}>Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredUsers.map((u) => {
                            const perms = u.permissions || {};
                            let allowedCount = 0;
                            let isConfigured = false;
                            try {
                                const raw = perms.allowed_templates;
                                isConfigured = raw !== null && raw !== undefined;
                                const arr = raw ? (typeof raw === "string" ? JSON.parse(raw) : raw) : [];
                                allowedCount = Array.isArray(arr) ? arr.length : 0;
                            } catch { allowedCount = 0; }

                            return (
                                <tr key={u.id} className="border-t" style={{ borderColor: "var(--panel-border)" }}>
                                    <td className="px-4 py-3">
                                        <div>
                                            <p className="font-medium text-sm" style={{ color: "var(--text)" }}>
                                                {u.full_name || "—"}
                                            </p>
                                            <p className="text-xs" style={{ color: "var(--muted-text)" }}>{u.email}</p>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 text-center">
                                        <span className="text-sm font-mono" style={{ color: isConfigured ? "var(--accent)" : "var(--muted-text)" }}>
                                            {isConfigured ? `${allowedCount}/${templates.length}` : "Nenhum (Bloqueado)"}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <button
                                            onClick={() => openTemplatesModal(u)}
                                            className="cb-btn text-xs px-3 py-1.5 flex items-center gap-1.5 ml-auto"
                                            style={{ borderColor: "var(--accent)", color: "var(--accent)" }}
                                        >
                                            <Shield className="h-3.5 w-3.5" />
                                            Configurar
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>

                {filteredUsers.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-12 opacity-40">
                        <Users className="h-8 w-8 mb-2" />
                        <p className="text-sm">Nenhum usuário encontrado.</p>
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Import: Create new template ────────────────────────────────────
function ImportSubTab({ toast, onCreated }) {
    const [form, setForm] = useState({
        id: "",
        name: "",
        short_name: "",
        description: "",
        icon: "📄",
        category: "custom",
        has_logo: false,
        sections: "",
        logo_b64: null,
        logo_preview: null,
    });
    const [saving, setSaving] = useState(false);

    const handleLogoChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onloadend = () => {
            setForm((f) => ({
                ...f,
                logo_b64: reader.result,
                logo_preview: reader.result,
            }));
        };
        reader.readAsDataURL(file);
    };

    const ICONS = ["📄", "📋", "📑", "📝", "📊", "📈", "🏢", "⚙️", "✨", "🔧"];

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!form.name.trim()) {
            toast.error("Nome do template é obrigatório.");
            return;
        }

        setSaving(true);
        try {
            const payload = {
                ...form,
                id: form.id.trim() || undefined,
                sections: form.sections
                    ? form.sections.split(",").map((s) => s.trim()).filter(Boolean)
                    : [],
                header_fields: [],
                footer_fields: [],
            };
            await api.post("/admin/templates", payload);
            toast.success(`Template "${form.name}" criado com sucesso!`);
            setForm({
                id: "",
                name: "",
                short_name: "",
                description: "",
                icon: "📄",
                category: "custom",
                has_logo: false,
                sections: "",
                logo_b64: null,
                logo_preview: null,
            });
            onCreated();
        } catch (e) {
            const msg = e?.response?.data?.detail || "Falha ao criar template.";
            toast.error(msg);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="max-w-2xl">
            <div className="mb-6">
                <h3 className="text-base font-semibold" style={{ color: "var(--text)" }}>
                    Importar Novo Template
                </h3>
                <p className="text-xs mt-1" style={{ color: "var(--muted-text)" }}>
                    Registre um novo template de documento no sistema. Templates customizados ficam disponíveis para atribuição a usuários.
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
                {/* ID + Name row */}
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text)" }}>
                            ID do Template
                        </label>
                        <input
                            type="text"
                            value={form.id}
                            onChange={(e) => setForm(f => ({ ...f, id: e.target.value.replace(/[^a-z0-9_]/g, "") }))}
                            placeholder="ex: minha_empresa_it"
                            className="cb-input text-sm w-full"
                        />
                        <p className="text-[10px] mt-1 opacity-50">Opcional. Se vazio, será gerado automaticamente.</p>
                    </div>
                    <div>
                        <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text)" }}>
                            Nome *
                        </label>
                        <input
                            type="text"
                            value={form.name}
                            onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
                            placeholder="ex: Instrução de Trabalho - Empresa X"
                            className="cb-input text-sm w-full"
                            required
                        />
                    </div>
                </div>

                {/* Short name + Icon */}
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text)" }}>
                            Nome Curto
                        </label>
                        <input
                            type="text"
                            value={form.short_name}
                            onChange={(e) => setForm(f => ({ ...f, short_name: e.target.value }))}
                            placeholder="ex: IT"
                            className="cb-input text-sm w-full"
                            maxLength={20}
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text)" }}>
                            Ícone
                        </label>
                        <div className="flex gap-1.5 flex-wrap">
                            {ICONS.map((ic) => (
                                <button
                                    type="button"
                                    key={ic}
                                    onClick={() => setForm(f => ({ ...f, icon: ic }))}
                                    className="h-9 w-9 rounded-lg flex items-center justify-center text-lg border transition-all"
                                    style={{
                                        borderColor: form.icon === ic ? "var(--accent)" : "var(--card-border)",
                                        backgroundColor: form.icon === ic ? "var(--accent)" : "transparent",
                                    }}
                                >
                                    {ic}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Category */}
                <div>
                    <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text)" }}>
                        Categoria
                    </label>
                    <div className="flex gap-2">
                        {[
                            { value: "custom", label: "Customizado" },
                            { value: "corporate", label: "Corporativo" },
                            { value: "general", label: "Geral" },
                        ].map((opt) => (
                            <button
                                type="button"
                                key={opt.value}
                                onClick={() => setForm(f => ({ ...f, category: opt.value }))}
                                className="px-4 py-2 rounded-lg text-xs font-medium border transition-all"
                                style={{
                                    borderColor: form.category === opt.value ? "var(--accent)" : "var(--card-border)",
                                    backgroundColor: form.category === opt.value ? "var(--accent)" : "transparent",
                                    color: form.category === opt.value ? "#fff" : "var(--muted-text)",
                                }}
                            >
                                {opt.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Description */}
                <div>
                    <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text)" }}>
                        Descrição
                    </label>
                    <textarea
                        value={form.description}
                        onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
                        placeholder="Descreva o template e seu uso..."
                        className="cb-input text-sm w-full"
                        rows={3}
                    />
                </div>

                {/* Sections */}
                <div>
                    <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--text)" }}>
                        Seções (separadas por vírgula)
                    </label>
                    <input
                        type="text"
                        value={form.sections}
                        onChange={(e) => setForm(f => ({ ...f, sections: e.target.value }))}
                        placeholder="ex: introduction, procedure, annexes"
                        className="cb-input text-sm w-full"
                    />
                    <p className="text-[10px] mt-1 opacity-50">
                        Defina as seções do template. Cada seção será uma parte do documento final.
                    </p>
                </div>

                {/* Has logo toggle */}
                <div className="space-y-4">
                    <div className="flex items-center gap-3">
                        <label className="relative inline-flex cursor-pointer items-center">
                            <input
                                type="checkbox"
                                className="sr-only"
                                checked={form.has_logo}
                                onChange={(e) => setForm(f => ({ ...f, has_logo: e.target.checked }))}
                            />
                            <div
                                className="h-5 w-9 rounded-full transition-colors"
                                style={{ backgroundColor: form.has_logo ? "var(--accent)" : "var(--card-border)" }}
                            />
                            <div
                                className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform shadow-sm"
                                style={{ transform: form.has_logo ? "translateX(1rem)" : "translateX(0)" }}
                            />
                        </label>
                        <span className="text-sm" style={{ color: "var(--text)" }}>
                            Template com logo corporativo
                        </span>
                    </div>

                    {form.has_logo && (
                        <div
                            className="p-4 rounded-xl border border-dashed transition-all"
                            style={{
                                borderColor: "var(--card-border)",
                                backgroundColor: "rgba(255,255,255,0.02)",
                            }}
                        >
                            <div className="flex items-start gap-4">
                                <div className="flex-1">
                                    <label className="block text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: "var(--muted-text)" }}>
                                        Importar Logo (PNG/JPG)
                                    </label>
                                    <input
                                        type="file"
                                        accept="image/*"
                                        onChange={handleLogoChange}
                                        className="text-xs w-full cursor-pointer file:mr-3 file:py-1 file:px-3 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-white/10 file:text-white hover:file:bg-white/20 transition-all"
                                        style={{ color: "var(--text)" }}
                                    />
                                    <p className="text-[10px] mt-2 opacity-50">
                                        Recomendado: fundo transparente, proporção landscape.
                                    </p>
                                </div>

                                {form.logo_preview && (
                                    <div
                                        className="h-16 w-16 rounded-lg border overflow-hidden flex items-center justify-center bg-white/5 relative group"
                                        style={{ borderColor: "var(--card-border)" }}
                                    >
                                        <img src={form.logo_preview} alt="Logo preview" className="max-h-full max-w-full object-contain p-1" />
                                        <button
                                            type="button"
                                            onClick={() => setForm(f => ({ ...f, logo_b64: null, logo_preview: null }))}
                                            className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                                        >
                                            <X className="h-4 w-4 text-white" />
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                {/* Submit */}
                <div className="flex gap-3 pt-4 border-t" style={{ borderColor: "var(--panel-border)" }}>
                    <button
                        type="submit"
                        disabled={saving || !form.name.trim()}
                        className="cb-btn cb-btn-primary flex items-center gap-2 px-6"
                    >
                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                        Criar Template
                    </button>
                </div>
            </form>
        </div>
    );
}
