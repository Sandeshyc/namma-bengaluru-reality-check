"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import PipelineVisualizer from "../../components/PipelineVisualizer";
import LivabilityScorecard from "../../components/LivabilityScorecard";
import { useAuth } from "../../components/AuthContext";
import Link from "next/link";
import { listingsHistoryQueryKeyRoot } from "../../lib/listingsHistory";

// ---- Shapes mirroring backend AgentState ----------------------------------

type PipelineStatus =
  | "success"
  | "partial"
  | "duplicate"
  | "failed"
  | "timeout"
  | "running";

type ErrorEntry = {
  node: string;
  type: string;
  message: string;
  retryable: boolean;
};

type ScorecardPayload = Record<string, unknown> & {
  total_score?: number;
};

type ParsedListingPayload = {
  raw_location?: string;
  bhk_type?: string | null;
  rent_amount?: number | null;
  security_deposit?: number | null;
};

type ApiResponse = {
  status: PipelineStatus;
  id?: string | null;
  duplicate_of?: string | null;
  pipeline_result: {
    pipeline_status: PipelineStatus;
    scorecard: ScorecardPayload | null;
    errors?: ErrorEntry[];
    duplicate_of?: string | null;
    parsed_listing?: ParsedListingPayload | null;
    commutes?: Record<string, number>;
    latitude?: number | null;
    longitude?: number | null;
    geocode_provider?: string | null;
    geocode_confidence?: number | null;
    [k: string]: unknown;
  };
};

export default function AnalyzePage() {
  const { user, session } = useAuth();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<ApiResponse["pipeline_result"] | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const resultSectionRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!result || analyzing) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const frame = window.requestAnimationFrame(() => {
      resultSectionRef.current?.scrollIntoView({
        behavior: prefersReducedMotion ? "auto" : "smooth",
        block: "start",
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [result, analyzing]);

  const handleAnalyze = async () => {
    if (!text) return;
    setAnalyzing(true);
    setResult(null);
    setSavedId(null);
    setFetchError(null);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (session?.access_token) {
        headers["Authorization"] = `Bearer ${session.access_token}`;
      }

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${apiUrl}/api/analyze`, {
        method: "POST",
        headers,
        body: JSON.stringify({ raw_text: text, source_platform: "manual" }),
      });

      if (response.status === 429) {
        const errorData = await response.json();
        setFetchError(errorData.detail || "Rate limit exceeded.");
        setAnalyzing(false);
        return;
      }

      const data: ApiResponse = await response.json();

      // Always surface the partial/duplicate/failed payload — the body carries
      // useful debugging info even when the HTTP code is non-200.
      if (data && data.pipeline_result) {
        setResult(data.pipeline_result);
        setSavedId(data.id ?? null);
      }

      if (user?.id && data?.id) {
        queryClient.invalidateQueries({ queryKey: [...listingsHistoryQueryKeyRoot] });
      }

      // Distinguish HTTP failure modes for the user-facing toast.
      if (response.status === 504) {
        setFetchError(
          "Pipeline timed out (>60s). The backend may be under load — check the server logs and try again."
        );
      } else if (response.status === 502 || data?.status === "failed") {
        setFetchError(
          "Pipeline failed. The extraction or geocoding step couldn't complete — see the error details below."
        );
      }
    } catch (err) {
      console.error("Fetch error:", err);
      setFetchError(
        "Failed to reach the backend. Make sure the FastAPI server is running on port 8000."
      );
    } finally {
      setAnalyzing(false);
    }
  };


  return (
    <div className="animate-slide-up" style={{ animationDelay: "0.1s" }}>
      <div className="section-header" data-step="01">
        <span className="eyebrow">Manual audit console</span>
      </div>
      <div className="meta-row" style={{ alignItems: "end", marginBottom: "var(--space-6)" }}>
        <div>
          <h1 style={{ fontSize: "clamp(2rem, 4vw, 3.5rem)", lineHeight: 1 }}>
            Convert broker text into a civic score.
          </h1>
          <p className="fine-print" style={{ marginTop: "var(--space-3)", maxWidth: "720px" }}>
            The backend checks prompt cache, geocodes inside Bengaluru, deduplicates by vector +
            distance, reuses commute cache, joins ward water data, and persists the result.
          </p>
        </div>
      {!user && (
        <div
          className="panel"
          style={{
            border: "1px dashed var(--warning)",
            background: "color-mix(in oklch, var(--warning) 4%, transparent)",
            padding: "var(--space-4)",
            marginBottom: "var(--space-6)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "var(--space-3)"
          }}
        >
          <p className="fine-print" style={{ margin: 0 }}>
            ⚠️ You are auditing anonymously. Your search results will not be saved to your history.
          </p>
          <Link href="/login" className="btn-primary" style={{ padding: "6px 14px", fontSize: "0.8rem", borderRadius: "var(--radius-sm)" }}>
            Log In to Save History
          </Link>
        </div>
      )}
      </div>

      <div className="analyze-grid">
        <section className="panel" style={{ padding: "var(--space-6)" }}>
          <div className="meta-row" style={{ marginBottom: "var(--space-5)" }}>
            <div>
              <span className="eyebrow">Input</span>
              <h2 style={{ marginTop: "6px" }}>Paste listing claim</h2>
            </div>
            <span className="fine-print">{text.length} chars</span>
          </div>

          <textarea
            className="input-field"
            rows={8}
            placeholder="e.g. 2BHK available in Indiranagar 100ft road. Rent 45k, deposit 2.5L. Cauvery water, 24/7 supply. Call 9999999999"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={analyzing}
            aria-label="Raw rental listing text"
          />

          <div className="meta-row" style={{ marginTop: "var(--space-4)" }}>
            <p className="fine-print">Tip: include location, rent, deposit, water claims, and restrictions.</p>
            <button
              className="btn-primary"
              onClick={handleAnalyze}
              disabled={!text || analyzing}
            >
              {analyzing ? "Running audit..." : "Analyze listing"}
            </button>
          </div>
        </section>

        <section className="stack">
          {(analyzing || result) ? (
            <PipelineVisualizer isRunning={analyzing} />
          ) : (
            <div className="panel" style={{ padding: "var(--space-6)" }}>
              <span className="eyebrow">Awaiting listing</span>
              <h2 style={{ marginTop: "8px" }}>No audit has run yet</h2>
              <p className="fine-print" style={{ marginTop: "var(--space-3)" }}>
                Results will appear here as an evidence card with commute, water, finance, and
                civic breakdowns.
              </p>
            </div>
          )}

        </section>
      </div>

      {fetchError && !analyzing && (
        <div
          className="panel"
          style={{
            border: "1px solid var(--danger)",
            background: "color-mix(in oklch, var(--danger) 8%, var(--ink-panel))",
            marginTop: "var(--space-6)",
            padding: "var(--space-5)",
          }}
        >
          <p style={{ color: "var(--danger)", fontWeight: 600 }}>{fetchError}</p>
        </div>
      )}

      {result && !analyzing && (
        <section
          ref={resultSectionRef}
          style={{ marginTop: "var(--space-6)", scrollMarginTop: "var(--space-6)" }}
        >
          <ResultBlock result={result} savedId={savedId} />
        </section>
      )}
    </div>
  );
}

// ---- Result rendering -----------------------------------------------------

function ResultBlock({
  result,
  savedId,
}: {
  result: ApiResponse["pipeline_result"];
  savedId: string | null;
}) {
  const status = result.pipeline_status;
  const scorecard = result.scorecard;

  return (
    <div className="scorecard-reveal" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {savedId && (
        <div
          style={{
            fontSize: "0.75rem",
            color: "var(--text-muted)",
            textAlign: "right",
            letterSpacing: "0.5px",
          }}
        >
          Saved as listing <code style={{ color: "var(--primary)" }}>{savedId.slice(0, 8)}...</code>
        </div>
      )}

      {scorecard ? (
        <>
          {status === "duplicate" && <DuplicateReuseBanner duplicateOf={result.duplicate_of ?? null} />}
          {status === "partial" && <PartialBanner errors={result.errors ?? []} />}
          <LivabilityScorecard data={scorecard} pipelineResult={result} />
        </>
      ) : (
        <PipelineFailedPanel status={status} errors={result.errors ?? []} />
      )}
    </div>
  );
}

function DuplicateReuseBanner({ duplicateOf }: { duplicateOf: string | null }) {
  return (
    <div
      className="panel"
      style={{
        border: "1px solid var(--warning)",
        background: "color-mix(in oklch, var(--warning) 8%, var(--ink-panel))",
        padding: "var(--space-4)",
      }}
    >
      <div className="meta-row">
        <span className="badge warning">cached analysis</span>
        {duplicateOf && <code className="fine-print">{duplicateOf.slice(0, 8)}...</code>}
      </div>
      <p className="fine-print" style={{ marginTop: "var(--space-3)" }}>
        This listing matched an existing record, so the scorecard below was reused from the
        canonical analysis instead of spending another full routing/scoring pass.
      </p>
    </div>
  );
}

function PartialBanner({ errors }: { errors: ErrorEntry[] }) {
  if (errors.length === 0) return null;
  return (
    <div
      className="panel"
      style={{
        border: "1px solid var(--warning)",
        background: "color-mix(in oklch, var(--warning) 8%, var(--ink-panel))",
        padding: "16px 20px",
      }}
    >
      <p style={{ color: "var(--warning)", fontWeight: 600, marginBottom: "8px", fontSize: "0.9rem" }}>
        Scorecard generated with caveats - {errors.length} non-fatal{" "}
        {errors.length === 1 ? "issue" : "issues"} during processing:
      </p>
      <ErrorList errors={errors} />
    </div>
  );
}

function PipelineFailedPanel({
  status,
  errors,
}: {
  status: PipelineStatus;
  errors: ErrorEntry[];
}) {
  const isTimeout = status === "timeout";
  const title = isTimeout ? "Pipeline Timed Out" : "Pipeline Failed";
  const sub = isTimeout
    ? "The backend exceeded the 60-second budget. This usually means an upstream API (Gemini, geocoding, routing) was slow or unreachable."
    : "The AI engine couldn't finish processing this listing. Most often this is a Gemini extraction or geocoding failure.";
  return (
    <div className="panel" style={{ border: "1px solid var(--danger)", padding: "var(--space-5)" }}>
      <h3 style={{ color: "var(--danger)", marginBottom: "8px" }}>{title}</h3>
      <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: "12px" }}>{sub}</p>
      {errors.length > 0 && <ErrorList errors={errors} />}
    </div>
  );
}

function ErrorList({ errors }: { errors: ErrorEntry[] }) {
  return (
    <ul style={{ paddingLeft: "20px", fontSize: "0.85rem", color: "var(--text-muted)", margin: 0 }}>
      {errors.map((err, i) => (
        <li key={i} style={{ marginBottom: "6px" }}>
          <strong style={{ color: "var(--danger)" }}>{err.node}</strong>
          <span style={{ color: "var(--text-muted)" }}> ({err.type})</span>
          {": "}
          {err.message}
          {err.retryable && (
            <span
              style={{
                marginLeft: "8px",
                fontSize: "0.7rem",
                color: "var(--warning)",
                border: "1px solid var(--warning)",
                padding: "1px 6px",
                borderRadius: "4px",
              }}
            >
              retryable
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
