"use client";

import { useEffect, useState, use } from "react";
import { useAuth } from "../../../components/AuthContext";
import LivabilityScorecard from "../../../components/LivabilityScorecard";
import Link from "next/link";
import { useRouter } from "next/navigation";

type ApiResponse = {
  status: string;
  id: string;
  pipeline_result: {
    pipeline_status: string;
    scorecard: any;
    parsed_listing?: any;
    commutes?: Record<string, number>;
    latitude?: number | null;
    longitude?: number | null;
    geocode_provider?: string | null;
    geocode_confidence?: number | null;
  };
};

export default function HistoryDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user, session, loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ApiResponse | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.push("/login");
      return;
    }

    const fetchDetail = async () => {
      setLoading(true);
      setError(null);
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const response = await fetch(`${apiUrl}/api/listings/${id}`, {
          headers: {
            Authorization: `Bearer ${session?.access_token}`,
          },
        });

        if (response.status === 403) {
          throw new Error("You do not have permission to view this listing audit.");
        }
        if (response.status === 404) {
          throw new Error("The requested listing audit was not found.");
        }
        if (!response.ok) {
          throw new Error("Failed to load audit scorecard.");
        }

        const resData = await response.json();
        setData(resData);
      } catch (err: any) {
        console.error(err);
        setError(err.message || "An error occurred while loading detail.");
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [id, user, session, authLoading, router]);

  if (authLoading || loading) {
    return (
      <div style={{ textAlign: "center", paddingBlock: "var(--space-16)" }}>
        <p className="fine-print">Loading scorecard details...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="animate-slide-up" style={{ paddingBlock: "var(--space-10)" }}>
        <div 
          className="panel" 
          style={{ 
            border: "1px solid var(--danger)", 
            background: "color-mix(in oklch, var(--danger) 8%, var(--ink-panel))",
            padding: "var(--space-6)",
            textAlign: "center"
          }}
        >
          <h3 style={{ color: "var(--danger)" }}>Error Loading Audit</h3>
          <p className="fine-print" style={{ marginTop: "var(--space-2)", marginBottom: "var(--space-6)" }}>
            {error}
          </p>
          <Link href="/history" className="btn-primary">
            Back to history
          </Link>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const result = data.pipeline_result;
  const scorecard = result.scorecard;

  return (
    <div className="animate-slide-up" style={{ animationDelay: "0.1s" }}>
      <div style={{ marginBottom: "var(--space-4)" }}>
        <Link href="/history" className="fine-print" style={{ color: "var(--primary)", display: "inline-flex", alignItems: "center", gap: "6px" }}>
          &lt;- Back to history vault
        </Link>
      </div>

      <div className="section-header" data-step="02">
        <span className="eyebrow">Saved Audit Result</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "var(--space-4)" }}>
        <div
          style={{
            fontSize: "0.75rem",
            color: "var(--text-muted)",
            textAlign: "right",
            letterSpacing: "0.5px",
          }}
        >
          Listing UUID: <code style={{ color: "var(--primary)" }}>{data.id}</code>
        </div>

        {scorecard && (
          <LivabilityScorecard data={scorecard} pipelineResult={result} />
        )}
      </div>
    </div>
  );
}
