"use client";

import axios from "axios";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/context/AuthContext";
import { getApiErrorMessage } from "@/lib/errors";
import { getAdminMe } from "@/services/admin";

export type AdminAccess =
  | { status: "checking" }
  | { status: "allowed" }
  | { status: "forbidden" }
  | { status: "error"; message: string };

/**
 * Whether the signed-in user may see the admin area.
 *
 * The role on the user object is only a first filter (a customer is turned away
 * without a request). An account that says "admin" is then confirmed by the
 * server (`GET /api/admin/me`), which reads the role from the database - so an
 * admin who was demoted or deactivated since their page loaded is turned away
 * too. Nothing here is a security boundary: the API refuses every admin call
 * from a non-admin on its own.
 */
export function useAdminAccess(): { access: AdminAccess; retry: () => void } {
  const { user, isLoading } = useAuth();
  const userId = user?.id ?? null;
  const isAdminRole = user?.role === "admin";

  const [access, setAccess] = useState<AdminAccess>({ status: "checking" });
  const attempt = useRef(0);

  const check = useCallback(async (owner: string) => {
    const mine = ++attempt.current;
    setAccess({ status: "checking" });
    try {
      const me = await getAdminMe();
      if (attempt.current !== mine) return;
      setAccess(me.role === "admin" && me.id === owner ? { status: "allowed" } : { status: "forbidden" });
    } catch (error) {
      if (attempt.current !== mine) return;
      if (axios.isAxiosError(error) && error.response?.status === 403) {
        setAccess({ status: "forbidden" });
      } else {
        setAccess({ status: "error", message: getApiErrorMessage(error, "We couldn't confirm your admin access.") });
      }
    }
  }, []);

  useEffect(() => {
    attempt.current += 1; // forget anything still in flight for a previous user
    if (isLoading || userId === null) {
      setAccess({ status: "checking" });
      return;
    }
    if (!isAdminRole) {
      setAccess({ status: "forbidden" });
      return;
    }
    void check(userId);
  }, [isLoading, userId, isAdminRole, check]);

  const retry = useCallback(() => {
    if (userId !== null && isAdminRole) void check(userId);
  }, [userId, isAdminRole, check]);

  return { access, retry };
}
