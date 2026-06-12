import type { ReactNode } from "react";

const TECH_PARK_NAMES: Record<string, string> = {
  tp_manyata: "Manyata",
  tp_whitefield: "Whitefield",
  tp_ecity: "Electronic City",
  tp_bagmane: "Bagmane ORR",
  tp_marathahalli: "Marathahalli",
};

type WaterBreakdown = {
  total: number;
  cauvery_supply: number;
  groundwater_resilience: number;
  building_signals: number;
  confidence: "high" | "medium" | "low";
  rationale: string[];
};

type ScoreItem = {
  label: string;
  value: number;
  max: number;
  tone?: string;
};

type ParsedListing = {
  raw_location?: string;
  bhk_type?: string | null;
  rent_amount?: number | null;
  security_deposit?: number | null;
};

type Alternative = {
  neighborhood: string;
  reason: string;
};

type ScorecardPayload = {
  total_score?: number;
  commute_score?: number;
  water_score?: number;
  financial_score?: number;
  civic_score?: number;
  water_breakdown?: WaterBreakdown | null;
  red_flags?: string[];
  alternatives?: Alternative[];
};

type PipelineResult = {
  parsed_listing?: ParsedListing | null;
  commutes?: Record<string, number>;
  latitude?: number | null;
  longitude?: number | null;
  geocode_provider?: string | null;
  geocode_confidence?: number | null;
};

function formatRupees(value?: number | null) {
  if (value == null) return "-";
  const raw = String(value);
  const lastThree = raw.slice(-3);
  const rest = raw.slice(0, -3);
  const groupedRest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return groupedRest ? `Rs ${groupedRest},${lastThree}` : `Rs ${lastThree}`;
}

export default function LivabilityScorecard({
  data,
  pipelineResult,
}: {
  data: ScorecardPayload;
  pipelineResult?: PipelineResult;
}) {
  const score = data.total_score ?? 0;
  const parsed = pipelineResult?.parsed_listing;
  const commutes = pipelineResult?.commutes || {};
  const sortedCommutes = Object.entries(commutes).sort(([, a], [, b]) => a - b);
  const waterBreakdown: WaterBreakdown | null = data.water_breakdown || null;
  const redFlags = data.red_flags ?? [];
  const alternatives = data.alternatives ?? [];
  const scoreColor = getScoreColor(score);
  const verdict =
    score >= 75 ? "Strong rental signal" : score >= 50 ? "Acceptable with caveats" : "High caution";

  const items: ScoreItem[] = [
    { label: "Commute", value: data.commute_score ?? 0, max: 40, tone: "var(--cauvery)" },
    { label: "Water", value: data.water_score ?? 0, max: 35, tone: "var(--cauvery-strong)" },
    { label: "Deposit", value: data.financial_score ?? 0, max: 15, tone: "var(--signal-amber)" },
    { label: "Civic", value: data.civic_score ?? 0, max: 10, tone: "var(--metro-green)" },
  ];

  return (
    <section className="panel scorecard-shell">
      <div className="scorecard-hero">
        <div
          className="scorecard-score"
          aria-label={`Livability score ${score} out of 100`}
          style={{
            borderColor: scoreColor,
            color: scoreColor,
            background: `radial-gradient(circle at 50% 35%, color-mix(in oklch, ${scoreColor} 22%, transparent), transparent 62%), var(--ink-inset)`,
            boxShadow: `0 0 42px color-mix(in oklch, ${scoreColor} 18%, transparent)`,
          }}
        >
          <div className="data-value">{score}</div>
          <span>out of 100</span>
        </div>

        <div className="scorecard-verdict">
          <span className="eyebrow">Reality check complete</span>
          <h2>{verdict}</h2>
          <p>
            Score is weighted by fastest commute options, ward-level water resilience, deposit
            pressure, and civic coverage.
          </p>
        </div>

        <div className="scorecard-status">
          <span className={`badge ${score >= 75 ? "success" : score >= 50 ? "warning" : "danger"}`}>
            {score >= 75 ? "clear signal" : score >= 50 ? "review" : "caution"}
          </span>
          {waterBreakdown && <ConfidenceBadge level={waterBreakdown.confidence} />}
        </div>
      </div>

      {parsed && <ExtractedDetails parsed={parsed} pipelineResult={pipelineResult} />}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: "var(--space-3)",
          marginBottom: "var(--space-6)",
        }}
      >
        {items.map((item) => (
          <ScoreTile key={item.label} item={item} />
        ))}
      </div>

      <div className="scorecard-evidence-grid">
        {waterBreakdown && <WaterBreakdownPanel breakdown={waterBreakdown} />}
        {sortedCommutes.length > 0 && <CommutePanel rows={sortedCommutes as [string, number][]} />}
        {redFlags.length > 0 && <RedFlags flags={redFlags} />}
        {alternatives.length > 0 && <Alternatives alternatives={alternatives} />}
      </div>
    </section>
  );
}

function ExtractedDetails({ parsed, pipelineResult }: { parsed: ParsedListing; pipelineResult?: PipelineResult }) {
  const lat = pipelineResult?.latitude;
  const lng = pipelineResult?.longitude;
  const geocodeProvider = pipelineResult?.geocode_provider;
  const geocodeConfidence = pipelineResult?.geocode_confidence;

  return (
    <div
      style={{
        marginBottom: "var(--space-6)",
        padding: "var(--space-4)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        background: "var(--ink-inset)",
      }}
    >
      <div className="meta-row" style={{ marginBottom: "var(--space-3)" }}>
        <span className="eyebrow">Extracted listing</span>
        {lat && lng && <span className="badge info">{geocodeProvider || "geocoded"}</span>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "var(--space-3)" }}>
        <Fact label="Location" value={parsed.raw_location || "-"} />
        <Fact label="Type" value={parsed.bhk_type || "-"} />
        <Fact label="Rent" value={formatRupees(parsed.rent_amount)} />
        <Fact label="Deposit" value={formatRupees(parsed.security_deposit)} />
      </div>
      {lat && lng && (
        <p className="fine-print" style={{ marginTop: "var(--space-3)" }}>
          Coordinates {lat.toFixed(4)}, {lng.toFixed(4)}
          {geocodeConfidence ? ` / confidence ${((geocodeConfidence || 0) * 100).toFixed(0)}%` : ""}
        </p>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div style={{ marginTop: "4px", color: "var(--text-main)", fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function ScoreTile({ item }: { item: ScoreItem }) {
  const pct = Math.min((item.value / item.max) * 100, 100);
  const tone = item.tone || getScoreColor(pct);

  return (
    <div style={{ padding: "var(--space-4)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", background: "var(--border-subtle)" }}>
      <div className="meta-row">
        <span className="eyebrow">{item.label}</span>
        <span className="data-value" style={{ color: tone, fontWeight: 800 }}>
          {item.value}/{item.max}
        </span>
      </div>
      <div style={{ height: "7px", marginTop: "var(--space-3)", borderRadius: "var(--radius-full)", background: "var(--ink-inset)", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: "inherit", background: tone }} />
      </div>
    </div>
  );
}

function WaterBreakdownPanel({ breakdown }: { breakdown: WaterBreakdown }) {
  return (
    <EvidencePanel title="Water security evidence" badge={<ConfidenceBadge level={breakdown.confidence} />}>
      <SubScoreBar label="Cauvery supply" value={breakdown.cauvery_supply} max={17} />
      <SubScoreBar label="Groundwater resilience" value={breakdown.groundwater_resilience} max={11} />
      <SubScoreBar label="Building signals" value={breakdown.building_signals} max={7} />
      {breakdown.rationale.length > 0 && (
        <ul className="fine-print" style={{ marginTop: "var(--space-4)", paddingLeft: "18px" }}>
          {breakdown.rationale.map((line, i) => (
            <li key={i} style={{ marginBottom: "6px" }}>{line}</li>
          ))}
        </ul>
      )}
    </EvidencePanel>
  );
}

function CommutePanel({ rows }: { rows: [string, number][] }) {
  return (
    <EvidencePanel title="Commute to tech parks" badge={<span className="badge neutral">best two weighted</span>}>
      <div style={{ display: "grid", gap: "var(--space-3)" }}>
        {rows.map(([parkId, mins], index) => {
          const pct = Math.min((mins / 90) * 100, 100);
          const color = mins <= 30 ? "var(--success)" : mins <= 45 ? "var(--warning)" : "var(--danger)";
          return (
            <div key={parkId} style={{ display: "grid", gridTemplateColumns: "132px 1fr 64px", gap: "var(--space-3)", alignItems: "center" }}>
              <span style={{ color: index < 2 ? "var(--text-main)" : "var(--text-muted)", fontWeight: index < 2 ? 700 : 500 }}>
                {TECH_PARK_NAMES[parkId] || parkId}
              </span>
              <div style={{ height: "8px", borderRadius: "var(--radius-full)", background: "var(--ink-inset)", overflow: "hidden" }}>
                <div style={{ width: `${pct}%`, height: "100%", borderRadius: "inherit", background: color }} />
              </div>
              <span className="data-value" style={{ color, textAlign: "right", fontWeight: 800 }}>{mins}m</span>
            </div>
          );
        })}
      </div>
    </EvidencePanel>
  );
}

function RedFlags({ flags }: { flags: string[] }) {
  return (
    <EvidencePanel title="Critical red flags" badge={<span className="badge danger">{flags.length} flags</span>}>
      <ul className="fine-print" style={{ paddingLeft: "18px" }}>
        {flags.map((flag, i) => (
          <li key={i} style={{ marginBottom: "6px", color: "var(--text-soft)" }}>{flag}</li>
        ))}
      </ul>
    </EvidencePanel>
  );
}

function Alternatives({ alternatives }: { alternatives: { neighborhood: string; reason: string }[] }) {
  return (
    <EvidencePanel title="Better alternatives" badge={<span className="badge info">same budget</span>}>
      <div style={{ display: "grid", gap: "var(--space-3)" }}>
        {alternatives.map((alt) => (
          <div key={alt.neighborhood} style={{ padding: "var(--space-3)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)", background: "var(--ink-inset)" }}>
            <strong>{alt.neighborhood}</strong>
            <p className="fine-print" style={{ marginTop: "4px" }}>{alt.reason}</p>
          </div>
        ))}
      </div>
    </EvidencePanel>
  );
}

function EvidencePanel({ title, badge, children }: { title: string; badge?: ReactNode; children: ReactNode }) {
  return (
    <div className="evidence-panel">
      <div className="meta-row" style={{ marginBottom: "var(--space-4)" }}>
        <h3 style={{ fontSize: "1rem" }}>{title}</h3>
        {badge}
      </div>
      {children}
    </div>
  );
}

function SubScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const color = pct >= 75 ? "var(--success)" : pct >= 50 ? "var(--warning)" : "var(--danger)";

  return (
    <div className="subscore-row">
      <span className="fine-print">{label}</span>
      <div style={{ height: "8px", borderRadius: "var(--radius-full)", background: "var(--ink-inset)", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: "inherit", background: color }} />
      </div>
      <span className="data-value" style={{ color, textAlign: "right", fontWeight: 800 }}>{value}/{max}</span>
    </div>
  );
}

function ConfidenceBadge({ level }: { level: "high" | "medium" | "low" }) {
  const className = level === "high" ? "success" : level === "medium" ? "warning" : "danger";
  return <span className={`badge ${className}`}>{level} confidence</span>;
}

function getScoreColor(score: number) {
  if (score >= 75) return "var(--success)";
  if (score >= 50) return "var(--warning)";
  return "var(--danger)";
}
