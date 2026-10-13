/**
 * Auth Context — JWT only
 *
 * Uses the local admin JWT issued by POST /sys/token and stored in sessionStorage.
 */

import {
  createContext,
  useContext,
  useEffect,
  useCallback,
  useMemo,
  useState,
} from "react";
import { useUser, useAuth, useClerk } from "@clerk/clerk-react";
import { api, setupClerkToken } from "./api";

const SYS_TOKEN_KEY = "__sys_token";

const AuthContext = createContext({
  isLoaded: false,
  isSignedIn: false,
  backendLoaded: false,
  user: null, // { id, email, role, full_name }
  signOut: async () => {},
  refreshProfile: async () => {},
  updateProfile: async () => ({ success: false }),
  openExternalProfile: () => {},
  authError: null, // { message, code }
  mode: "jwt", // "jwt" | "clerk"
});

export function useAppAuth() {
  return useContext(AuthContext);
}

function readSysToken() {
  try {
    return sessionStorage.getItem(SYS_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

function clearSysToken() {
  try {
    sessionStorage.removeItem(SYS_TOKEN_KEY);
  } catch {}
}

function JwtOnlyAuthProvider({ children }) {
  const [backendUser, setBackendUser] = useState(null);
  const [backendLoaded, setBackendLoaded] = useState(false);
  const [authError, setAuthError] = useState(null);

  const refreshProfile = useCallback(async () => {
    const token = readSysToken();
    if (!token) {
      setBackendUser(null);
      setBackendLoaded(true);
      return;
    }

    api.defaults.headers.common["Authorization"] = "Bearer " + token;

    try {
      const res = await api.get("/auth/me");
      const d = res?.data;
      if (d && d.id) {
        setBackendUser({
          id: d.id,
          email: d.email || "",
          role: d.role || "user",
          full_name: d.full_name || "",
        });
      } else {
        setBackendUser(null);
      }
    } catch {
      clearSysToken();
      setBackendUser(null);
      try {
        delete api.defaults.headers.common["Authorization"];
      } catch {}
    } finally {
      setBackendLoaded(true);
    }
  }, []);

  useEffect(() => {
    refreshProfile();
    const intervalId = setInterval(() => {
      refreshProfile();
    }, 5 * 60 * 1000);
    return () => clearInterval(intervalId);
  }, [refreshProfile]);

  const signOut = useCallback(async () => {
    clearSysToken();
    setBackendUser(null);
    try {
      delete api.defaults.headers.common["Authorization"];
    } catch {}
  }, []);

  const updateProfile = useCallback(async (data) => {
    try {
      const res = await api.patch("/auth/me", data);
      const d = res?.data;
      if (d && d.id) {
        setBackendUser((prev) => ({ ...prev, ...d }));
        return { success: true, user: d };
      }
      return { success: false, error: "Falha ao atualizar perfil" };
    } catch (err) {
      return { success: false, error: err.response?.data?.detail || "Erro ao atualizar perfil" };
    }
  }, []);

  const value = useMemo(
    () => ({
      isLoaded: backendLoaded,
      isSignedIn: !!backendUser && backendLoaded,
      backendLoaded,
      user: backendUser,
      signOut,
      refreshProfile,
      updateProfile,
      openExternalProfile: null,
      authError,
      mode: "jwt",
    }),
    [backendLoaded, backendUser, signOut, refreshProfile, updateProfile, authError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function ClerkBackedAuthProvider({ children }) {
  const { isLoaded: clerkLoaded, isSignedIn: clerkSignedIn, user: clerkUser } = useUser();
  const { getToken, signOut: clerkSignOut } = useAuth();

  const [backendUser, setBackendUser] = useState(null);
  const [backendLoaded, setBackendLoaded] = useState(false);
  const [authError, setAuthError] = useState(null);

  const mode = "clerk";
  // The app is "loaded" if backend profile is fetched.
  // We don't wait for clerkLoaded indefinitely to allow the JWT backdoor to work.
  const isLoaded = backendLoaded;
  // isSignedIn requires the BACKEND to confirm the user, not just Clerk.
  // This ensures inactive/pending-approval users (who get a 403 from /auth/me)
  // are blocked from protected routes even though Clerk considers them signed-in.
  const isSignedIn = !!backendUser && backendLoaded;

  // Register Clerk token getter with axios interceptor
  useEffect(() => {
    if (clerkLoaded) {
      setupClerkToken(getToken);
    }
  }, [clerkLoaded, getToken]);

  const refreshProfile = useCallback(async () => {
    // If Clerk is active and user is signed in, we rely on Clerk.
    // The axios interceptor handles injecting the Bearer token.
    if (clerkSignedIn) {
      setAuthError(null);
      try {
        // PERM-STARTUP: Add a strict 10s timeout for the initial session check
        // to prevent a "white screen" hang when the backend is unreachable.
        const res = await api.get("/auth/me", { timeout: 10000 });
        const d = res?.data;
        // SECURITY: Only set backendUser if the backend confirms a valid, active DB account.
        // If /auth/me returns no id (user not in DB, deleted, or banned),
        // set backendUser to null so ProtectedRoute redirects to /login.
        if (d && d.id) {
          setBackendUser({
            id: d.id,
            email: d.email || clerkUser?.primaryEmailAddress?.emailAddress || "",
            role: d.role || "user",
            full_name:
              d.full_name || clerkUser?.fullName || clerkUser?.firstName || "",
            plan: d.plan || "free",
            credits_balance: d.credits_balance ?? 0,
            is_active: d.is_active,
            permissions: d.permissions || null,
          });
        } else {
          // Backend returned no valid user — account may be deleted or not yet registered.
          // Do NOT create a fake user from Clerk data. Force sign-out.
          console.warn("AuthContext: backend returned no valid user, signing out.");
          setBackendUser(null);
          try { await clerkSignOut(); } catch (_) {}
        }
      } catch (err) {
        const status = err?.response?.status;
        console.warn("AuthContext: failed to fetch profile via Clerk:", err);
        if (status === 401 || status === 403) {
          // Explicit backend rejection (deleted/inactive account)
          // Do NOT sign out immediately, just set a specific authError so we can show PendingApproval
          setBackendUser(null);
          setAuthError({
            message: "Conta aguardando aprovação do administrador.",
            code: status || "INACTIVE_USER",
            isPendingApproval: true,
          });
        } else {
          // Network error or server unavailable — deny access conservatively.
          console.error("AuthContext: server unreachable or network error:", err);
          setBackendUser(null);
          setAuthError({
            message: "Não foi possível contactar o servidor. Verifique a sua ligação.",
            code: status || "NETWORK_ERROR"
          });
        }
      } finally {
        setBackendLoaded(true);
      }
      return;
    }

    // Fallback: local JWT (Admin backdoor/migration)
    const token = readSysToken();
    if (!token) {
      setBackendUser(null);
      setBackendLoaded(true);
      return;
    }

    api.defaults.headers.common["Authorization"] = "Bearer " + token;

    try {
      const res = await api.get("/auth/me");
      const d = res?.data;
      if (d && d.id) {
        setBackendUser({
          id: d.id,
          email: d.email || "",
          role: d.role || "user",
          full_name: d.full_name || "",
        });
      } else {
        setBackendUser(null);
      }
    } catch {
      clearSysToken();
      setBackendUser(null);
      try {
        delete api.defaults.headers.common["Authorization"];
      } catch {}
    } finally {
      setBackendLoaded(true);
    }
  }, [clerkSignedIn, clerkUser, clerkSignOut]);

  useEffect(() => {
    if (clerkLoaded) {
      refreshProfile();

      // Polling para revogação de sessão em tempo real (PERM-04)
      const intervalId = setInterval(() => {
        refreshProfile();
      }, 5 * 60 * 1000); // 5 minutos

      return () => clearInterval(intervalId);
    } else {
      // Se tiver erro de rede no Clerk (ex: 403), o isLoaded do useUser() nunca ficará true.
      // Damos 1.5s e forçamos o refresh para que o fallback local não fique travado.
      const timer = setTimeout(() => {
        if (!backendLoaded) refreshProfile();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [clerkLoaded, refreshProfile, backendLoaded]);

  const signOut = useCallback(async () => {
    if (clerkSignedIn) {
      await clerkSignOut();
    }
    clearSysToken();
    setBackendUser(null);
    setAuthError(null);
    try {
      delete api.defaults.headers.common["Authorization"];
    } catch {}
  }, [clerkSignedIn, clerkSignOut]);

  const { openUserProfile } = useClerk();

  const updateProfile = useCallback(async (data) => {
    try {
      const res = await api.patch("/auth/me", data);
      const d = res?.data;
      if (d && d.id) {
        setBackendUser((prev) => ({
          ...prev,
          ...d,
          // Merge with Clerk data if needed
          email: d.email || clerkUser?.primaryEmailAddress?.emailAddress || prev?.email || "",
          full_name: d.full_name || clerkUser?.fullName || prev?.full_name || "",
        }));
        return { success: true, user: d };
      }
      return { success: false, error: "Falha ao atualizar perfil" };
    } catch (err) {
      console.error("AuthContext: updateProfile failed:", err);
      return { 
        success: false, 
        error: err.response?.data?.detail || "Erro ao atualizar perfil" 
      };
    }
  }, [clerkUser]);

  const value = useMemo(
    () => ({
      isLoaded,
      isSignedIn,
      backendLoaded,
      user: backendUser,
      signOut,
      refreshProfile,
      updateProfile,
      openExternalProfile: openUserProfile,
      authError,
      mode,
    }),
    [isLoaded, isSignedIn, backendLoaded, backendUser, signOut, refreshProfile, updateProfile, openUserProfile, authError, mode],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function _isClerkDisabled() {
  try {
    return localStorage.getItem("CLIPBUILDER_DISABLE_CLERK") === "1";
  } catch {
    return false;
  }
}

export function AppAuthProvider({ children }) {
  const clerkEnabled =
    !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && !_isClerkDisabled();
  if (clerkEnabled) {
    return <ClerkBackedAuthProvider>{children}</ClerkBackedAuthProvider>;
  }
  return <JwtOnlyAuthProvider>{children}</JwtOnlyAuthProvider>;
}

export default AuthContext;
