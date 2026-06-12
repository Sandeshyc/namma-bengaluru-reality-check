"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../components/AuthContext";
import ListingCard from "../../components/ListingCard";
import Link from "next/link";
import {
  fetchListingsHistory,
  listingsHistoryQueryKey,
} from "../../lib/listingsHistory";

export default function HistoryPage() {
  const { user, session, loading: authLoading } = useAuth();

  const {
    data,
    isPending,
    isError,
    error,
    isFetching,
  } = useQuery({
    queryKey: user?.id ? listingsHistoryQueryKey(user.id) : ["listings", "history", "anon"],
    queryFn: () => fetchListingsHistory(session!.access_token),
    enabled: !authLoading && !!user && !!session?.access_token,
    staleTime: 5 * 60 * 1000,
  });

  const listings = data?.listings ?? [];
  const showLoading = authLoading || (!!user && !!session?.access_token && isPending && !data);

  if (showLoading) {
    return (
      <div style={{ textAlign: "center", paddingBlock: "var(--space-16)" }}>
        <p className="fine-print">Loading your search history...</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{ textAlign: "center", paddingBlock: "var(--space-16)" }}>
        <h2>Access Denied</h2>
        <p className="fine-print" style={{ marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
          Please log in to view your reality check audit history.
        </p>
        <Link href="/login" className="btn-primary">
          Log In
        </Link>
      </div>
    );
  }

  return (
    <div className="animate-slide-up" style={{ animationDelay: "0.1s" }}>
      <div className="section-header" data-step="01">
        <span className="eyebrow">Your Audit Vault</span>
      </div>
      <div className="meta-row" style={{ alignItems: "end", marginBottom: "var(--space-6)" }}>
        <div>
          <h1 style={{ fontSize: "clamp(2rem, 4vw, 3.5rem)", lineHeight: 1 }}>
            Previously checked listings.
          </h1>
          <p className="fine-print" style={{ marginTop: "var(--space-3)", maxWidth: "720px" }}>
            Revisit any of your past audits to review water risk, tech park commute times, and deposit metrics instantly without running the API pipeline again.
          </p>
        </div>
        <span className="badge info" style={{ opacity: isFetching ? 0.75 : 1 }}>
          {listings.length} checks run
        </span>
      </div>

      {isError && (
        <div
          className="panel"
          style={{
            border: "1px solid var(--danger)",
            background: "color-mix(in oklch, var(--danger) 8%, var(--ink-panel))",
            padding: "var(--space-5)",
            marginBottom: "var(--space-6)",
          }}
        >
          <p style={{ color: "var(--danger)" }}>
            {error instanceof Error ? error.message : "An error occurred while fetching history."}
          </p>
        </div>
      )}

      {listings.length === 0 ? (
        <div
          className="panel"
          style={{
            padding: "var(--space-12)",
            textAlign: "center",
            border: "1px dashed var(--border)",
            background: "transparent",
          }}
        >
          <h3>No audits saved yet</h3>
          <p className="fine-print" style={{ marginTop: "var(--space-3)", marginBottom: "var(--space-6)" }}>
            Run your first manual audit of a broker claim to see it listed here in your vault.
          </p>
          <Link href="/analyze" className="btn-primary">
            Audit first listing
          </Link>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "var(--space-6)" }}>
          {listings.map((item) => (
            <Link key={item.id} href={`/history/${item.id}`}>
              <ListingCard
                data={{
                  id: item.id,
                  location: item.raw_location || "Unknown Location",
                  rent: item.rent_amount || undefined,
                  bhk: item.bhk_type || "Listing",
                  score: item.livability_score,
                  water_risk: item.water_risk_level || "Unknown",
                  commute_avg: item.commute_avg_minutes ?? null,
                }}
              />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
