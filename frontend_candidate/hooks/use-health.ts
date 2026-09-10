"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api/health";

export function useBackendHealth() {
  return useQuery({
    queryKey: ["backend-health"],
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
