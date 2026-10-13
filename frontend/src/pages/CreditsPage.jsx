import { useState, useEffect, useCallback, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
    ArrowLeft,
    Zap,
    ShoppingCart,
    CheckCircle,
    XCircle,
    RefreshCw,
    CreditCard,
    Gift,
    Undo2,
    Copy,
    X,
    Loader2,
    QrCode,
    Sparkles,
    History,
} from "lucide-react";
import { api } from "../utils/api";
import useCredits from "../hooks/useCredits";

const MP_PUBLIC_KEY = import.meta.env.VITE_MP_PUBLIC_KEY || "";

const TRANSACTION_TYPE_CONFIG = {
    purchase: { label: "Compra", icon: ShoppingCart, color: "#10b981" },
    usage: { label: "Uso", icon: Zap, color: "#f59e0b" },
    refund: { label: "Reembolso", icon: Undo2, color: "#6366f1" },
    bonus: { label: "Bônus", icon: Gift, color: "#8b5cf6" },
};

function formatDate(isoString) {
    if (!isoString) return "—";
    try {
        const d = new Date(isoString);
        return d.toLocaleDateString("pt-BR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return isoString;
    }
}

function formatBRL(value) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
    }).format(value);
}

// ── Pix Modal Component ─────────────────────────────────────────────────────

function PixModal({ pixData, onClose, onSuccess }) {
    const [status, setStatus] = useState(pixData?.status || "pending");
    const [copied, setCopied] = useState(false);
    const [error, setError] = useState(null);
    const pollingRef = useRef(null);

    // Poll for payment status
    useEffect(() => {
        if (!pixData?.payment_id) return;

        const pollStatus = async () => {
            try {
                const res = await api.get(
                    `/billing/payment/${pixData.payment_id}`,
                );
                const newStatus = res?.data?.status;
                setStatus(newStatus);

                if (newStatus === "approved") {
                    clearInterval(pollingRef.current);
                    setTimeout(() => onSuccess?.(), 1500);
                } else if (
                    newStatus === "cancelled" ||
                    newStatus === "rejected"
                ) {
                    clearInterval(pollingRef.current);
                    setError("Pagamento cancelado ou rejeitado.");
                }
            } catch (err) {
                console.error("Error polling payment status:", err);
            }
        };

        // Poll every 4 seconds
        pollingRef.current = setInterval(pollStatus, 4000);
        // Initial check
        pollStatus();

        return () => {
            if (pollingRef.current) {
                clearInterval(pollingRef.current);
            }
        };
    }, [pixData?.payment_id, onSuccess]);

    const handleCopyCode = async () => {
        if (!pixData?.qr_code) return;
        try {
            await navigator.clipboard.writeText(pixData.qr_code);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Fallback for older browsers
            const textarea = document.createElement("textarea");
            textarea.value = pixData.qr_code;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            document.body.removeChild(textarea);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    const isApproved = status === "approved";
    const isError = status === "cancelled" || status === "rejected" || error;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div
                className="relative w-full max-w-md rounded-2xl border p-6 shadow-2xl"
                style={{
                    backgroundColor: "var(--panel)",
                    borderColor: "var(--panel-border)",
                }}
            >
                {/* Close button */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 p-1 rounded-lg hover:bg-black/10 transition-colors"
                    style={{ color: "var(--muted-text)" }}
                >
                    <X className="h-5 w-5" />
                </button>

                {/* Header */}
                <div className="text-center mb-6">
                    <div
                        className="inline-flex items-center justify-center h-12 w-12 rounded-full mb-3"
                        style={{ backgroundColor: "rgba(16, 185, 129, 0.1)" }}
                    >
                        {isApproved ? (
                            <CheckCircle className="h-6 w-6 text-green-500" />
                        ) : isError ? (
                            <XCircle className="h-6 w-6 text-red-500" />
                        ) : (
                            <QrCode
                                className="h-6 w-6"
                                style={{ color: "var(--accent)" }}
                            />
                        )}
                    </div>
                    <h3
                        className="text-lg font-semibold"
                        style={{ color: "var(--text)" }}
                    >
                        {isApproved
                            ? "Pagamento Confirmado!"
                            : isError
                              ? "Pagamento Falhou"
                              : "Pagar com Pix"}
                    </h3>
                    {pixData?.package && (
                        <p
                            className="text-sm mt-1"
                            style={{ color: "var(--muted-text)" }}
                        >
                            {pixData.package.label} — {pixData.package.credits}{" "}
                            créditos
                        </p>
                    )}
                </div>

                {/* Success state */}
                {isApproved && (
                    <div className="text-center py-4">
                        <p
                            className="text-sm"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            Seus créditos foram adicionados com sucesso!
                        </p>
                    </div>
                )}

                {/* Error state */}
                {isError && !isApproved && (
                    <div className="text-center py-4">
                        <p className="text-sm text-red-500">
                            {error || "O pagamento foi cancelado ou rejeitado."}
                        </p>
                    </div>
                )}

                {/* Pending state - show QR code */}
                {!isApproved && !isError && (
                    <>
                        {/* QR Code */}
                        {pixData?.qr_code_base64 && (
                            <div className="flex justify-center mb-4">
                                <div className="p-3 bg-white rounded-xl">
                                    <img
                                        src={`data:image/png;base64,${pixData.qr_code_base64}`}
                                        alt="QR Code Pix"
                                        className="w-48 h-48"
                                    />
                                </div>
                            </div>
                        )}

                        {/* Pix Copia e Cola */}
                        {pixData?.qr_code && (
                            <div className="mb-4">
                                <label
                                    className="block text-xs font-medium mb-2"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Pix Copia e Cola
                                </label>
                                <div
                                    className="relative p-3 rounded-xl text-xs break-all font-mono border"
                                    style={{
                                        backgroundColor: "transparent",
                                        borderColor: "var(--panel-border)",
                                        color: "var(--text-secondary)",
                                    }}
                                >
                                    <span className="line-clamp-3">
                                        {pixData.qr_code}
                                    </span>
                                    <button
                                        onClick={handleCopyCode}
                                        className="absolute top-2 right-2 p-1.5 rounded-lg transition-colors"
                                        style={{
                                            backgroundColor: copied
                                                ? "rgba(16, 185, 129, 0.2)"
                                                : "var(--panel)",
                                            color: copied
                                                ? "#10b981"
                                                : "var(--accent)",
                                        }}
                                        title="Copiar código"
                                    >
                                        {copied ? (
                                            <CheckCircle className="h-4 w-4" />
                                        ) : (
                                            <Copy className="h-4 w-4" />
                                        )}
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Status indicator */}
                        <div
                            className="flex items-center justify-center gap-2 py-3 rounded-xl"
                            style={{
                                backgroundColor: "rgba(99, 102, 241, 0.1)",
                            }}
                        >
                            <Loader2
                                className="h-4 w-4 animate-spin"
                                style={{ color: "var(--accent)" }}
                            />
                            <span
                                className="text-sm font-medium"
                                style={{ color: "var(--accent)" }}
                            >
                                Aguardando pagamento...
                            </span>
                        </div>

                        <p
                            className="text-xs text-center mt-3"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Escaneie o QR Code ou copie o código acima e pague
                            no app do seu banco.
                        </p>
                    </>
                )}

                {/* Close button at bottom for success/error */}
                {(isApproved || isError) && (
                    <button
                        onClick={onClose}
                        className="w-full mt-4 py-2.5 px-4 rounded-xl text-sm font-semibold transition-colors"
                        style={{
                            backgroundColor: "var(--accent)",
                            color: "#fff",
                        }}
                    >
                        Fechar
                    </button>
                )}
            </div>
        </div>
    );
}

// ── Card Modal Component ────────────────────────────────────────────────────

function CardModal({ pkg, onClose, onSuccess }) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [sdkLoaded, setSdkLoaded] = useState(false);
    const [result, setResult] = useState(null);

    // Form state
    const [cardNumber, setCardNumber] = useState("");
    const [cardHolder, setCardHolder] = useState("");
    const [expirationMonth, setExpirationMonth] = useState("");
    const [expirationYear, setExpirationYear] = useState("");
    const [securityCode, setSecurityCode] = useState("");
    const [docType, setDocType] = useState("CPF");
    const [docNumber, setDocNumber] = useState("");
    const [email, setEmail] = useState("");
    const [installments, setInstallments] = useState(1);

    // Load MP SDK
    useEffect(() => {
        if (window.MercadoPago) {
            setSdkLoaded(true);
            return;
        }

        const script = document.createElement("script");
        script.src = "https://sdk.mercadopago.com/js/v2";
        script.async = true;
        script.onload = () => setSdkLoaded(true);
        script.onerror = () =>
            setError("Falha ao carregar SDK do Mercado Pago");
        document.body.appendChild(script);

        return () => {
            // Don't remove script on unmount to allow reuse
        };
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        if (!MP_PUBLIC_KEY) {
            setError(
                "Chave pública do Mercado Pago não configurada (VITE_MP_PUBLIC_KEY)",
            );
            setLoading(false);
            return;
        }

        if (!sdkLoaded || !window.MercadoPago) {
            setError(
                "SDK do Mercado Pago ainda não carregou. Tente novamente.",
            );
            setLoading(false);
            return;
        }

        try {
            const mp = new window.MercadoPago(MP_PUBLIC_KEY, {
                locale: "pt-BR",
            });

            // Create card token
            const cardTokenResult = await mp.createCardToken({
                cardNumber: cardNumber.replace(/\s/g, ""),
                cardholderName: cardHolder,
                cardExpirationMonth: expirationMonth,
                cardExpirationYear:
                    expirationYear.length === 2
                        ? `20${expirationYear}`
                        : expirationYear,
                securityCode: securityCode,
                identificationType: docType,
                identificationNumber: docNumber.replace(/\D/g, ""),
            });

            if (cardTokenResult.error) {
                throw new Error(cardTokenResult.error);
            }

            // Get payment method from BIN
            const bin = cardNumber.replace(/\s/g, "").slice(0, 6);
            let paymentMethodId = "visa";
            let issuerId = null;

            try {
                const paymentMethods = await mp.getPaymentMethods({ bin });
                if (
                    paymentMethods.results &&
                    paymentMethods.results.length > 0
                ) {
                    paymentMethodId = paymentMethods.results[0].id;
                    issuerId = paymentMethods.results[0].issuer?.id || null;
                }
            } catch (pmErr) {
                console.warn(
                    "Could not detect payment method, using default:",
                    pmErr,
                );
            }

            // Send to backend
            const res = await api.post("/billing/checkout/card", {
                package_id: pkg.id,
                token: cardTokenResult.id,
                installments: installments,
                payment_method_id: paymentMethodId,
                issuer_id: issuerId,
                payer: {
                    email: email,
                    identification: {
                        type: docType,
                        number: docNumber.replace(/\D/g, ""),
                    },
                },
            });

            const data = res?.data;

            if (data?.approved) {
                setResult({ success: true, message: "Pagamento aprovado!" });
                setTimeout(() => onSuccess?.(data), 1500);
            } else if (data?.status === "in_process") {
                setResult({
                    success: false,
                    pending: true,
                    message:
                        "Pagamento em análise. Você receberá uma confirmação em breve.",
                });
            } else if (data?.status === "rejected") {
                setError(
                    translateStatusDetail(data?.status_detail) ||
                        "Pagamento rejeitado. Verifique os dados do cartão.",
                );
            } else {
                setResult({
                    success: false,
                    pending: true,
                    message: `Status: ${data?.status || "pendente"}. Aguarde a confirmação.`,
                });
            }
        } catch (err) {
            console.error("Card payment error:", err);
            const detail =
                err?.response?.data?.detail ||
                err?.message ||
                "Erro ao processar pagamento";
            setError(detail);
        } finally {
            setLoading(false);
        }
    };

    const translateStatusDetail = (detail) => {
        const translations = {
            cc_rejected_bad_filled_card_number: "Número do cartão inválido",
            cc_rejected_bad_filled_date: "Data de validade inválida",
            cc_rejected_bad_filled_other: "Dados do cartão inválidos",
            cc_rejected_bad_filled_security_code:
                "Código de segurança inválido",
            cc_rejected_blacklist: "Cartão não autorizado",
            cc_rejected_call_for_authorize:
                "Ligue para sua operadora para autorizar",
            cc_rejected_card_disabled: "Cartão desabilitado",
            cc_rejected_card_error: "Erro no cartão",
            cc_rejected_duplicated_payment: "Pagamento duplicado",
            cc_rejected_high_risk: "Pagamento recusado por segurança",
            cc_rejected_insufficient_amount: "Saldo insuficiente",
            cc_rejected_invalid_installments: "Parcelas inválidas",
            cc_rejected_max_attempts: "Tentativas excedidas",
            cc_rejected_other_reason: "Pagamento recusado",
        };
        return translations[detail] || null;
    };

    // Format card number with spaces
    const formatCardNumber = (value) => {
        const v = value.replace(/\s/g, "").replace(/\D/g, "").slice(0, 16);
        const parts = [];
        for (let i = 0; i < v.length; i += 4) {
            parts.push(v.slice(i, i + 4));
        }
        return parts.join(" ");
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm overflow-y-auto">
            <div
                className="relative w-full max-w-md rounded-2xl border p-6 shadow-2xl my-8"
                style={{
                    backgroundColor: "var(--panel)",
                    borderColor: "var(--panel-border)",
                }}
            >
                {/* Close button */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 p-1 rounded-lg hover:bg-black/10 transition-colors"
                    style={{ color: "var(--muted-text)" }}
                >
                    <X className="h-5 w-5" />
                </button>

                {/* Header */}
                <div className="text-center mb-6">
                    <div
                        className="inline-flex items-center justify-center h-12 w-12 rounded-full mb-3"
                        style={{ backgroundColor: "rgba(99, 102, 241, 0.1)" }}
                    >
                        {result?.success ? (
                            <CheckCircle className="h-6 w-6 text-green-500" />
                        ) : (
                            <CreditCard
                                className="h-6 w-6"
                                style={{ color: "var(--accent)" }}
                            />
                        )}
                    </div>
                    <h3
                        className="text-lg font-semibold"
                        style={{ color: "var(--text)" }}
                    >
                        {result?.success
                            ? "Pagamento Aprovado!"
                            : "Pagamento com Cartão"}
                    </h3>
                    <p
                        className="text-sm mt-1"
                        style={{ color: "var(--muted-text)" }}
                    >
                        {pkg.label} — {pkg.credits} créditos —{" "}
                        {formatBRL(pkg.price_brl)}
                    </p>
                </div>

                {/* Success/Pending result */}
                {result && (
                    <div className="text-center py-4">
                        <p
                            className="text-sm"
                            style={{
                                color: result.success
                                    ? "#10b981"
                                    : "var(--text-secondary)",
                            }}
                        >
                            {result.message}
                        </p>
                        {!result.success && (
                            <button
                                onClick={onClose}
                                className="mt-4 py-2.5 px-6 rounded-xl text-sm font-semibold"
                                style={{
                                    backgroundColor: "var(--accent)",
                                    color: "#fff",
                                }}
                            >
                                Fechar
                            </button>
                        )}
                    </div>
                )}

                {/* Error message */}
                {error && !result && (
                    <div
                        className="mb-4 p-3 rounded-xl text-sm"
                        style={{
                            backgroundColor: "rgba(239, 68, 68, 0.1)",
                            color: "#ef4444",
                        }}
                    >
                        {error}
                    </div>
                )}

                {/* Form */}
                {!result && (
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {/* Card Number */}
                        <div>
                            <label
                                className="block text-xs font-medium mb-1.5"
                                style={{ color: "var(--text-secondary)" }}
                            >
                                Número do Cartão
                            </label>
                            <input
                                type="text"
                                value={cardNumber}
                                onChange={(e) =>
                                    setCardNumber(
                                        formatCardNumber(e.target.value),
                                    )
                                }
                                placeholder="0000 0000 0000 0000"
                                required
                                className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                style={{
                                    backgroundColor: "var(--bg)",
                                    borderColor: "var(--panel-border)",
                                    color: "var(--text)",
                                }}
                            />
                        </div>

                        {/* Cardholder Name */}
                        <div>
                            <label
                                className="block text-xs font-medium mb-1.5"
                                style={{ color: "var(--text-secondary)" }}
                            >
                                Nome no Cartão
                            </label>
                            <input
                                type="text"
                                value={cardHolder}
                                onChange={(e) =>
                                    setCardHolder(e.target.value.toUpperCase())
                                }
                                placeholder="NOME COMO NO CARTÃO"
                                required
                                className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                style={{
                                    backgroundColor: "var(--bg)",
                                    borderColor: "var(--panel-border)",
                                    color: "var(--text)",
                                }}
                            />
                        </div>

                        {/* Expiration & CVV */}
                        <div className="grid grid-cols-3 gap-3">
                            <div>
                                <label
                                    className="block text-xs font-medium mb-1.5"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Mês
                                </label>
                                <input
                                    type="text"
                                    value={expirationMonth}
                                    onChange={(e) =>
                                        setExpirationMonth(
                                            e.target.value
                                                .replace(/\D/g, "")
                                                .slice(0, 2),
                                        )
                                    }
                                    placeholder="MM"
                                    required
                                    maxLength={2}
                                    className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                    style={{
                                        backgroundColor: "transparent",
                                        borderColor: "var(--panel-border)",
                                        color: "var(--text)",
                                    }}
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-xs font-medium mb-1.5"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Ano
                                </label>
                                <input
                                    type="text"
                                    value={expirationYear}
                                    onChange={(e) =>
                                        setExpirationYear(
                                            e.target.value
                                                .replace(/\D/g, "")
                                                .slice(0, 4),
                                        )
                                    }
                                    placeholder="AAAA"
                                    required
                                    maxLength={4}
                                    className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                    style={{
                                        backgroundColor: "var(--bg)",
                                        borderColor: "var(--panel-border)",
                                        color: "var(--text)",
                                    }}
                                />
                            </div>
                            <div>
                                <label
                                    className="block text-xs font-medium mb-1.5"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    CVV
                                </label>
                                <input
                                    type="text"
                                    value={securityCode}
                                    onChange={(e) =>
                                        setSecurityCode(
                                            e.target.value
                                                .replace(/\D/g, "")
                                                .slice(0, 4),
                                        )
                                    }
                                    placeholder="000"
                                    required
                                    maxLength={4}
                                    className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                    style={{
                                        backgroundColor: "var(--bg)",
                                        borderColor: "var(--panel-border)",
                                        color: "var(--text)",
                                    }}
                                />
                            </div>
                        </div>

                        {/* Email */}
                        <div>
                            <label
                                className="block text-xs font-medium mb-1.5"
                                style={{ color: "var(--text-secondary)" }}
                            >
                                E-mail
                            </label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="seu@email.com"
                                required
                                className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                style={{
                                    backgroundColor: "var(--bg)",
                                    borderColor: "var(--panel-border)",
                                    color: "var(--text)",
                                }}
                            />
                        </div>

                        {/* Document */}
                        <div className="grid grid-cols-3 gap-3">
                            <div>
                                <label
                                    className="block text-xs font-medium mb-1.5"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Tipo Doc
                                </label>
                                <select
                                    value={docType}
                                    onChange={(e) => setDocType(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                    style={{
                                        backgroundColor: "var(--bg)",
                                        borderColor: "var(--panel-border)",
                                        color: "var(--text)",
                                    }}
                                >
                                    <option value="CPF">CPF</option>
                                    <option value="CNPJ">CNPJ</option>
                                </select>
                            </div>
                            <div className="col-span-2">
                                <label
                                    className="block text-xs font-medium mb-1.5"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    {docType}
                                </label>
                                <input
                                    type="text"
                                    value={docNumber}
                                    onChange={(e) =>
                                        setDocNumber(e.target.value)
                                    }
                                    placeholder={
                                        docType === "CPF"
                                            ? "000.000.000-00"
                                            : "00.000.000/0000-00"
                                    }
                                    required
                                    className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                    style={{
                                        backgroundColor: "var(--bg)",
                                        borderColor: "var(--panel-border)",
                                        color: "var(--text)",
                                    }}
                                />
                            </div>
                        </div>

                        {/* Installments */}
                        <div>
                            <label
                                className="block text-xs font-medium mb-1.5"
                                style={{ color: "var(--text-secondary)" }}
                            >
                                Parcelas
                            </label>
                            <select
                                value={installments}
                                onChange={(e) =>
                                    setInstallments(Number(e.target.value))
                                }
                                className="w-full px-3 py-2.5 rounded-xl text-sm border outline-none focus:ring-2"
                                style={{
                                    backgroundColor: "var(--bg)",
                                    borderColor: "var(--panel-border)",
                                    color: "var(--text)",
                                }}
                            >
                                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(
                                    (n) => (
                                        <option key={n} value={n}>
                                            {n}x de{" "}
                                            {formatBRL(pkg.price_brl / n)}
                                            {n === 1 ? " (à vista)" : ""}
                                        </option>
                                    ),
                                )}
                            </select>
                        </div>

                        {/* Submit button */}
                        <button
                            type="submit"
                            disabled={loading || !sdkLoaded}
                            className="w-full py-3 px-4 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                            style={{
                                backgroundColor: "var(--accent)",
                                color: "#fff",
                            }}
                        >
                            {loading ? (
                                <>
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Processando...
                                </>
                            ) : (
                                <>
                                    <CreditCard className="h-4 w-4" />
                                    Pagar {formatBRL(pkg.price_brl)}
                                </>
                            )}
                        </button>

                        <p
                            className="text-[10px] text-center"
                            style={{ color: "var(--muted-text)" }}
                        >
                            Seus dados de cartão são processados de forma segura
                            pelo Mercado Pago.
                        </p>
                    </form>
                )}
            </div>
        </div>
    );
}

// ── Main CreditsPage Component ──────────────────────────────────────────────

export default function CreditsPage() {
    const {
        credits,
        totalPurchased,
        totalUsed,
        loading: balanceLoading,
        refetch,
    } = useCredits();
    const [packages, setPackages] = useState([]);
    const [transactions, setTransactions] = useState([]);
    const [txLoading, setTxLoading] = useState(true);
    const [pkgLoading, setPkgLoading] = useState(true);
    const [pixLoading, setPixLoading] = useState(null);
    const [error, setError] = useState(null);
    const [successMessage, setSuccessMessage] = useState(null);
    const [searchParams, setSearchParams] = useSearchParams();

    // Modal state
    const [pixModal, setPixModal] = useState(null);
    const [cardModal, setCardModal] = useState(null);

    // Check for redirect status (legacy, might still be useful)
    useEffect(() => {
        const status = searchParams.get("status");
        if (status === "success") {
            setSuccessMessage(
                "Pagamento realizado com sucesso! Seus créditos foram adicionados.",
            );
            setSearchParams({}, { replace: true });
            setTimeout(() => refetch(), 1500);
            setTimeout(() => setSuccessMessage(null), 8000);
        } else if (status === "cancelled") {
            setError("Pagamento cancelado.");
            setSearchParams({}, { replace: true });
            setTimeout(() => setError(null), 5000);
        }
    }, [searchParams, setSearchParams, refetch]);

    // Fetch packages
    useEffect(() => {
        setPkgLoading(true);
        api.get("/billing/packages")
            .then((res) => {
                setPackages(res?.data || []);
            })
            .catch(() => {
                setPackages([]);
            })
            .finally(() => setPkgLoading(false));
    }, []);

    // Fetch transactions
    const fetchTransactions = useCallback(() => {
        setTxLoading(true);
        api.get("/billing/transactions", { params: { limit: 50 } })
            .then((res) => {
                setTransactions(res?.data || []);
            })
            .catch(() => {
                setTransactions([]);
            })
            .finally(() => setTxLoading(false));
    }, []);

    useEffect(() => {
        fetchTransactions();
    }, [fetchTransactions]);

    // Handle Pix checkout
    async function handleCheckoutPix(pkg) {
        setPixLoading(pkg.id);
        setError(null);
        try {
            const res = await api.post("/billing/checkout/pix", {
                package_id: pkg.id,
            });
            setPixModal(res.data);
        } catch (err) {
            const detail =
                err?.response?.data?.detail ||
                err?.message ||
                "Erro ao criar pagamento Pix";
            setError(detail);
        } finally {
            setPixLoading(null);
        }
    }

    // Handle payment success
    function handlePaymentSuccess() {
        setPixModal(null);
        setCardModal(null);
        setSuccessMessage(
            "Pagamento realizado com sucesso! Seus créditos foram adicionados.",
        );
        refetch();
        fetchTransactions();
        setTimeout(() => setSuccessMessage(null), 8000);
    }

    function handleRefresh() {
        refetch();
        fetchTransactions();
    }

    const packageHighlight = { starter: false, pro: true, business: false };

    return (
        <div className="cb-app-shell min-h-screen" style={{ color: "var(--text)" }}>
            {/* Modals */}
            {pixModal && (
                <PixModal
                    pixData={pixModal}
                    onClose={() => setPixModal(null)}
                    onSuccess={handlePaymentSuccess}
                />
            )}
            {cardModal && (
                <CardModal
                    pkg={cardModal}
                    onClose={() => setCardModal(null)}
                    onSuccess={handlePaymentSuccess}
                />
            )}

            {/* Header */}
            <header className="cb-header">
                <div className="cb-header-inner !max-w-5xl">
                    <div className="flex items-center gap-4">
                        <Link
                            to="/"
                            className="cb-btn p-2.5 flex items-center gap-1.5"
                            title="Voltar ao Dashboard"
                        >
                            <ArrowLeft className="h-4 w-4" />
                            <span className="text-xs font-medium hidden sm:inline">
                                Voltar
                            </span>
                        </Link>
                        <div className="flex items-center gap-2">
                            <CreditCard
                                size={22}
                                style={{ color: "var(--accent)" }}
                            />
                            <h1
                                className="text-xl font-semibold"
                                style={{ color: "var(--text)" }}
                            >
                                Créditos
                            </h1>
                        </div>
                    </div>
                    <button
                        onClick={handleRefresh}
                        className="cb-btn p-2.5"
                        title="Atualizar"
                    >
                        <RefreshCw className="h-4 w-4" />
                    </button>
                </div>
            </header>

            <main className="mx-auto max-w-5xl px-6 py-8 space-y-10">
                {/* Success message */}
                {successMessage && (
                    <div
                        className="flex items-center gap-3 rounded-xl px-5 py-4 border"
                        style={{
                            backgroundColor: "rgba(16, 185, 129, 0.08)",
                            borderColor: "rgba(16, 185, 129, 0.25)",
                            color: "#10b981",
                        }}
                    >
                        <CheckCircle className="h-5 w-5 flex-shrink-0" />
                        <span className="text-sm font-medium">
                            {successMessage}
                        </span>
                    </div>
                )}

                {/* Error message */}
                {error && (
                    <div
                        className="flex items-center gap-3 rounded-xl px-5 py-4 border"
                        style={{
                            backgroundColor: "rgba(239, 68, 68, 0.08)",
                            borderColor: "rgba(239, 68, 68, 0.25)",
                            color: "#ef4444",
                        }}
                    >
                        <XCircle className="h-5 w-5 flex-shrink-0" />
                        <span className="text-sm font-medium">{error}</span>
                    </div>
                )}

                {/* ── Balance Card ──────────────────────────────────────────── */}
                <section
                    className="rounded-2xl border p-6 sm:p-8"
                    style={{
                        backgroundColor: "var(--card-bg)",
                        borderColor: "var(--card-border)",
                    }}
                >
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                        <div>
                            <p
                                className="text-xs font-semibold uppercase tracking-widest mb-1"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Saldo atual
                            </p>
                            <div className="flex items-baseline gap-2">
                                <span
                                    className="text-4xl sm:text-5xl font-bold"
                                    style={{ color: "var(--accent)" }}
                                >
                                    {balanceLoading ? "…" : (credits ?? 0)}
                                </span>
                                <span
                                    className="text-lg font-medium"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    créditos
                                </span>
                            </div>
                        </div>
                        <div
                            className="flex gap-6 text-sm"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            <div>
                                <span
                                    className="block text-xs uppercase tracking-wider"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Comprados
                                </span>
                                <span
                                    className="text-lg font-semibold"
                                    style={{ color: "#10b981" }}
                                >
                                    {totalPurchased}
                                </span>
                            </div>
                            <div>
                                <span
                                    className="block text-xs uppercase tracking-wider"
                                    style={{ color: "var(--muted-text)" }}
                                >
                                    Utilizados
                                </span>
                                <span
                                    className="text-lg font-semibold"
                                    style={{ color: "#f59e0b" }}
                                >
                                    {totalUsed}
                                </span>
                            </div>
                        </div>
                    </div>
                </section>

                {/* ── Credit Packages ───────────────────────────────────────── */}
                <section>
                    <div className="flex items-center gap-2 mb-6">
                        <Sparkles
                            className="h-5 w-5"
                            style={{ color: "var(--accent)" }}
                        />
                        <h2 className="text-lg font-semibold">
                            Comprar Créditos
                        </h2>
                    </div>

                    {pkgLoading ? (
                        <div
                            className="text-center py-12"
                            style={{ color: "var(--muted-text)" }}
                        >
                            <div
                                className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-current border-r-transparent mb-3"
                                style={{ borderColor: "var(--accent)" }}
                            />
                            <p className="text-sm">Carregando pacotes...</p>
                        </div>
                    ) : packages.length === 0 ? (
                        <div
                            className="text-center py-12 rounded-xl border"
                            style={{
                                backgroundColor: "var(--card-bg)",
                                borderColor: "var(--card-border)",
                                color: "var(--muted-text)",
                            }}
                        >
                            <p className="text-sm">
                                Nenhum pacote disponível no momento.
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                            {packages.map((pkg) => {
                                const isHighlighted = packageHighlight[pkg.id];
                                const pricePerCredit = (
                                    pkg.price_brl / pkg.credits
                                ).toFixed(2);
                                const isPixLoading = pixLoading === pkg.id;

                                return (
                                    <div
                                        key={pkg.id}
                                        className={`credit-pkg-card flex flex-col ${isHighlighted ? "highlighted" : ""}`}
                                    >
                                        {isHighlighted && (
                                            <div
                                                className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                                                style={{
                                                    backgroundColor:
                                                        "var(--accent)",
                                                    color: "#fff",
                                                }}
                                            >
                                                Popular
                                            </div>
                                        )}

                                        <h3 className="text-lg font-semibold mb-1">
                                            {pkg.label}
                                        </h3>
                                        <p
                                            className="text-xs mb-4"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            {pkg.description ||
                                                `${pkg.credits} créditos`}
                                        </p>

                                        <div className="flex items-baseline gap-1 mb-1">
                                            <span
                                                className="text-3xl font-bold"
                                                style={{
                                                    color: "var(--accent)",
                                                }}
                                            >
                                                {formatBRL(pkg.price_brl)}
                                            </span>
                                        </div>
                                        <p
                                            className="text-xs mb-5"
                                            style={{
                                                color: "var(--muted-text)",
                                            }}
                                        >
                                            {pkg.credits} créditos · R$
                                            {pricePerCredit}/crédito
                                        </p>

                                        {/* Pix button (primary) */}
                                        <button
                                            onClick={() =>
                                                handleCheckoutPix(pkg)
                                            }
                                            disabled={
                                                isPixLoading ||
                                                pixLoading !== null
                                            }
                                            className="w-full py-2.5 px-4 rounded-xl text-sm font-semibold transition-all duration-150 flex items-center justify-center gap-2 disabled:opacity-50 mb-2"
                                            style={{
                                                backgroundColor: isHighlighted
                                                    ? "var(--accent)"
                                                    : "transparent",
                                                color: isHighlighted
                                                    ? "#fff"
                                                    : "var(--accent)",
                                                border: isHighlighted
                                                    ? "none"
                                                    : "1.5px solid var(--accent)",
                                            }}
                                        >
                                            {isPixLoading ? (
                                                <>
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                    Gerando Pix...
                                                </>
                                            ) : (
                                                <>
                                                    <QrCode className="h-4 w-4" />
                                                    Pagar com Pix
                                                </>
                                            )}
                                        </button>

                                        {/* Card button (secondary) */}
                                        <button
                                            onClick={() => setCardModal(pkg)}
                                            disabled={pixLoading !== null}
                                            className="w-full py-2 px-4 rounded-xl text-xs font-medium transition-all duration-150 flex items-center justify-center gap-2 disabled:opacity-50"
                                            style={{
                                                backgroundColor: "transparent",
                                                color: "var(--text-secondary)",
                                                border: "1px solid var(--panel-border)",
                                            }}
                                        >
                                            <CreditCard className="h-3.5 w-3.5" />
                                            Cartão de Crédito/Débito
                                        </button>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </section>

                {/* ── Transaction History ────────────────────────────────────── */}
                <section>
                    <div className="flex items-center gap-2 mb-6">
                        <History
                            className="h-5 w-5"
                            style={{ color: "var(--accent)" }}
                        />
                        <h2 className="text-lg font-semibold">
                            Histórico de Transações
                        </h2>
                    </div>

                    {txLoading ? (
                        <div
                            className="text-center py-12"
                            style={{ color: "var(--muted-text)" }}
                        >
                            <div
                                className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-current border-r-transparent mb-3"
                                style={{ borderColor: "var(--accent)" }}
                            />
                            <p className="text-sm">Carregando histórico...</p>
                        </div>
                    ) : transactions.length === 0 ? (
                        <div
                            className="text-center py-16 rounded-xl border"
                            style={{
                                backgroundColor: "var(--card-bg)",
                                borderColor: "var(--card-border)",
                            }}
                        >
                            <History
                                className="h-10 w-10 mx-auto mb-3"
                                style={{
                                    color: "var(--muted-text)",
                                    opacity: 0.4,
                                }}
                            />
                            <p
                                className="text-sm font-medium mb-1"
                                style={{ color: "var(--text-secondary)" }}
                            >
                                Nenhuma transação ainda
                            </p>
                            <p
                                className="text-xs"
                                style={{ color: "var(--muted-text)" }}
                            >
                                Suas transações de créditos aparecerão aqui.
                            </p>
                        </div>
                    ) : (
                        <div
                            className="rounded-xl border overflow-hidden"
                            style={{
                                backgroundColor: "var(--card-bg)",
                                borderColor: "var(--card-border)",
                            }}
                        >
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr
                                            className="border-b"
                                            style={{
                                                borderColor:
                                                    "var(--card-border)",
                                            }}
                                        >
                                            <th
                                                className="text-left px-5 py-3 text-xs font-semibold uppercase tracking-wider"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                Tipo
                                            </th>
                                            <th
                                                className="text-left px-5 py-3 text-xs font-semibold uppercase tracking-wider"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                Descrição
                                            </th>
                                            <th
                                                className="text-right px-5 py-3 text-xs font-semibold uppercase tracking-wider"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                Créditos
                                            </th>
                                            <th
                                                className="text-right px-5 py-3 text-xs font-semibold uppercase tracking-wider"
                                                style={{
                                                    color: "var(--muted-text)",
                                                }}
                                            >
                                                Data
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {transactions.map((tx) => {
                                            const config =
                                                TRANSACTION_TYPE_CONFIG[
                                                    tx.type
                                                ] ||
                                                TRANSACTION_TYPE_CONFIG.usage;
                                            const Icon = config.icon;
                                            const isPositive = tx.amount > 0;

                                            return (
                                                <tr
                                                    key={tx.id}
                                                    className="border-b last:border-b-0 transition-colors"
                                                    style={{
                                                        borderColor:
                                                            "var(--card-border)",
                                                    }}
                                                >
                                                    <td className="px-5 py-3">
                                                        <div className="flex items-center gap-2">
                                                            <div
                                                                className="flex items-center justify-center h-7 w-7 rounded-lg"
                                                                style={{
                                                                    backgroundColor:
                                                                        config.color +
                                                                        "18",
                                                                }}
                                                            >
                                                                <Icon
                                                                    className="h-3.5 w-3.5"
                                                                    style={{
                                                                        color: config.color,
                                                                    }}
                                                                />
                                                            </div>
                                                            <span
                                                                className="text-xs font-medium"
                                                                style={{
                                                                    color: config.color,
                                                                }}
                                                            >
                                                                {config.label}
                                                            </span>
                                                        </div>
                                                    </td>
                                                    <td className="px-5 py-3">
                                                        <span
                                                            className="text-xs"
                                                            style={{
                                                                color: "var(--text-secondary)",
                                                            }}
                                                        >
                                                            {tx.description ||
                                                                "—"}
                                                        </span>
                                                        {tx.endpoint && (
                                                            <span
                                                                className="ml-2 inline-block text-[10px] px-1.5 py-0.5 rounded"
                                                                style={{
                                                                    backgroundColor:
                                                                        "var(--panel)",
                                                                    color: "var(--muted-text)",
                                                                }}
                                                            >
                                                                {tx.endpoint}
                                                            </span>
                                                        )}
                                                    </td>
                                                    <td className="px-5 py-3 text-right">
                                                        <span
                                                            className="text-sm font-semibold"
                                                            style={{
                                                                color: isPositive
                                                                    ? "#10b981"
                                                                    : "#f59e0b",
                                                            }}
                                                        >
                                                            {isPositive
                                                                ? "+"
                                                                : ""}
                                                            {tx.amount}
                                                        </span>
                                                    </td>
                                                    <td
                                                        className="px-5 py-3 text-right text-xs whitespace-nowrap"
                                                        style={{
                                                            color: "var(--muted-text)",
                                                        }}
                                                    >
                                                        {formatDate(
                                                            tx.created_at,
                                                        )}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </section>

                {/* ── Cost Reference ────────────────────────────────────────── */}
                <section
                    className="rounded-xl border p-6"
                    style={{
                        backgroundColor: "var(--card-bg)",
                        borderColor: "var(--card-border)",
                    }}
                >
                    <h3
                        className="text-sm font-semibold mb-4"
                        style={{ color: "var(--text)" }}
                    >
                        Custo por operação
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {[
                            { name: "Smart Text", cost: 1 },
                            { name: "Descrever GIF", cost: 1 },
                            { name: "Formatar & Exportar", cost: 2 },
                            { name: "Aprimorar Documento", cost: 3 },
                            { name: "Gerar Documentação", cost: 3 },
                            { name: "Upload de Vídeo", cost: 5 },
                            { name: "Import YouTube", cost: 5 },
                        ].map((item) => (
                            <div
                                key={item.name}
                                className="flex items-center justify-between px-3 py-2 rounded-lg"
                                style={{ backgroundColor: "var(--panel)" }}
                            >
                                <span
                                    className="text-xs"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    {item.name}
                                </span>
                                <span
                                    className="text-xs font-bold ml-2"
                                    style={{ color: "var(--accent)" }}
                                >
                                    {item.cost}
                                    <Zap className="inline h-3 w-3 ml-0.5" />
                                </span>
                            </div>
                        ))}
                    </div>
                </section>
            </main>
        </div>
    );
}
