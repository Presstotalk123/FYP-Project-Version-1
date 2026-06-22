import { useMemo } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { defineERAbility } from "@/permissions/er-ability";

export function useERAbility() {
  const { user } = useAuth();
  return useMemo(() => defineERAbility(user), [user]);
}
