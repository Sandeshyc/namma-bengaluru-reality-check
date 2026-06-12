const apiUrl = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Query key prefix; use with `user.id` for per-user cache + invalidation. */
export const listingsHistoryQueryKeyRoot = ["listings", "history"] as const;

export function listingsHistoryQueryKey(userId: string) {
  return [...listingsHistoryQueryKeyRoot, userId] as const;
}

export type HistoricalListing = {
  id: string;
  search_date: string;
  raw_location: string;
  bhk_type: string | null;
  rent_amount: number | null;
  security_deposit: number | null;
  livability_score: number;
  water_risk_level: string;
  commute_avg_minutes?: number | null;
  created_at?: string;
};

export type ListingsHistoryResponse = {
  listings: HistoricalListing[];
  total?: number;
};

export async function fetchListingsHistory(accessToken: string): Promise<ListingsHistoryResponse> {
  const response = await fetch(`${apiUrl()}/api/listings/history`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to fetch search history");
  }
  const data = await response.json();
  return {
    listings: data.listings || [],
    total: data.total,
  };
}
