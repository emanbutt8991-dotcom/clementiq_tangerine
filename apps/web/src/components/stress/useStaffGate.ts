"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useVerifiedRole } from "@/lib/hooks";

/** Stress Test and Needs Attention are for judges and admins. Customers are sent back to Home.
 *  UI convenience only: the API enforces the same rule (require_judge). */
export function useStaffGate(): boolean {
  const role = useVerifiedRole();
  const router = useRouter();
  const allowed = role === "judge" || role === "admin";
  useEffect(() => {
    if (role && !allowed) router.replace("/");
  }, [role, allowed, router]);
  return allowed;
}
