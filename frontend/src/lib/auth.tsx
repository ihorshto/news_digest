import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { api, ApiError, type User } from "./api";
import { Skeleton } from "../components/ui";

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery<User | null>({
    queryKey: meKey,
    queryFn: async () => {
      try {
        return await api.me();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 30_000,
  });
}

export function useSetMe() {
  const qc = useQueryClient();
  return (user: User | null) => qc.setQueryData(meKey, user);
}

function FullPageSkeleton() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="mt-6 h-28 w-full" />
      <Skeleton className="mt-4 h-28 w-full" />
    </div>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { data: user, isPending } = useMe();
  const location = useLocation();
  if (isPending) return <FullPageSkeleton />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

/** Sends already-signed-in visitors away from /login and /register. The decision is taken
 * once, when the session check first resolves: a successful login *on* this page changes
 * the session too, and then the form itself decides where to go. */
export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { data: user, isPending } = useMe();
  const [authedOnArrival, setAuthedOnArrival] = useState<boolean | null>(null);
  if (!isPending && authedOnArrival === null) setAuthedOnArrival(!!user);
  if (isPending || authedOnArrival === null) return <FullPageSkeleton />;
  if (authedOnArrival) return <Navigate to="/" replace />;
  return <>{children}</>;
}
