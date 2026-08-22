"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { onForceLogout } from "@/lib/auth-events";
import { tokenStorage } from "@/lib/token-storage";
import { getCurrentUser, loginUser, logoutUser, registerUser, type RegisterPayload } from "@/services/auth";
import type { User } from "@/types/auth";

interface AuthContextValue {
  user: User | null;
  /** True only while the initial session-restore check (on first mount)
   * is in flight. Lets consumers like Navbar avoid flashing "Login" for
   * a split second before flipping to the real logged-in state. */
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Runs once on mount - including after a hard page refresh. This is
  // what makes "being logged in" survive a reload: if a token already
  // exists in storage from a previous visit, resolve it to a real user
  // profile via GET /api/users/me rather than just trusting the token's
  // mere presence.
  useEffect(() => {
    let isMounted = true;

    async function restoreSession() {
      const hasToken = Boolean(tokenStorage.getAccessToken() ?? tokenStorage.getRefreshToken());
      if (!hasToken) {
        if (isMounted) setIsLoading(false);
        return;
      }

      try {
        const currentUser = await getCurrentUser();
        if (isMounted) setUser(currentUser);
      } catch {
        // Access token missing/expired, and the axios interceptor's own
        // refresh attempt (triggered automatically by this same 401)
        // already failed too by the time this catch runs - there's no
        // valid session left to restore.
        tokenStorage.clearTokens();
        if (isMounted) setUser(null);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    restoreSession();
    return () => {
      isMounted = false;
    };
  }, []);

  // The axios response interceptor fires this event when a refresh
  // attempt fails outright (the refresh token itself is dead, not just
  // expired-and-renewable) - Context is the one place that actually owns
  // `user` state, so it's what clears it and redirects, no matter which
  // API call anywhere in the app happened to trigger the failure.
  useEffect(() => {
    const unsubscribe = onForceLogout(() => {
      setUser(null);
      router.push("/login");
    });
    return unsubscribe;
  }, [router]);

  const login = useCallback(async (email: string, password: string, rememberMe: boolean = true) => {
    const data = await loginUser(email, password, rememberMe);
    setUser(data.user);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    // Registration does not log the user in (the backend's /register
    // endpoint returns no tokens by design - see Milestone 3) - this
    // just creates the account. The register page sends them to /login
    // afterward.
    return registerUser(payload);
  }, []);

  const logout = useCallback(async () => {
    await logoutUser();
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, isLoading, isAuthenticated: user !== null, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}