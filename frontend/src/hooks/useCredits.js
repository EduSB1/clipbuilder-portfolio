import { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";

/**
 * Hook to fetch and manage the user's credit balance.
 *
 * Returns:
 *   - credits: current credit balance (number | null while loading)
 *   - totalPurchased: lifetime credits purchased
 *   - totalUsed: lifetime credits consumed
 *   - loading: whether the initial fetch is in progress
 *   - error: error message if the fetch failed
 *   - refetch: function to manually refresh the balance
 */
export default function useCredits() {
    const [credits, setCredits] = useState(null);
    const [totalPurchased, setTotalPurchased] = useState(0);
    const [totalUsed, setTotalUsed] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchBalance = useCallback(async () => {
        try {
            setError(null);
            const res = await api.get("/billing/balance");
            const data = res?.data;
            if (data && typeof data.credits === "number") {
                setCredits(data.credits);
                setTotalPurchased(data.total_purchased ?? 0);
                setTotalUsed(data.total_used ?? 0);
            }
        } catch (err) {
            // 401/403 means user is not authenticated — don't treat as error
            const status = err?.response?.status;
            if (status === 401 || status === 403) {
                setCredits(null);
            } else {
                setError(
                    err?.response?.data?.detail ||
                        err?.message ||
                        "Erro ao buscar saldo",
                );
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchBalance();
    }, [fetchBalance]);

    return {
        credits,
        totalPurchased,
        totalUsed,
        loading,
        error,
        refetch: fetchBalance,
    };
}
