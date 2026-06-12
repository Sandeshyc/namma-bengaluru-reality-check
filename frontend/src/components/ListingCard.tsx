type ListingCardData = {
  id: string;
  location: string;
  rent?: number;
  bhk: string;
  score: number;
  water_risk: "Low" | "Medium" | "High" | string;
  /** Mean of two shortest tech-park commutes (minutes); null if not persisted */
  commute_avg: number | null;
  is_duplicate?: boolean;
};

function formatRupees(value?: number) {
  if (value == null) return "-";
  const [lastThree, rest] = [
    String(value).slice(-3),
    String(value).slice(0, -3),
  ];
  const groupedRest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return groupedRest ? `${groupedRest},${lastThree}` : lastThree;
}

export default function ListingCard({ data }: { data: ListingCardData }) {
  const getScoreColor = (score: number) => {
    if (score >= 75) return "var(--success)";
    if (score >= 50) return "var(--warning)";
    return "var(--danger)";
  };

  const waterClass =
    data.water_risk === "Low" ? "success" : data.water_risk === "Medium" ? "warning" : "danger";
  const commuteMins = data.commute_avg;
  const commuteClass =
    commuteMins == null
      ? "neutral"
      : commuteMins <= 30
        ? "success"
        : commuteMins <= 45
          ? "warning"
          : "danger";

  return (
    <article
      className="panel panel-hover"
      style={{
        minHeight: "220px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "var(--space-5)",
        overflow: "hidden",
      }}
    >
      <div className="meta-row" style={{ alignItems: "flex-start" }}>
        <div>
          <span className="eyebrow">Rental audit</span>
          <h3 style={{ fontSize: "1.25rem", marginTop: "8px", marginBottom: "6px" }}>
            {data.location}
          </h3>
          <p className="fine-print">
            {data.bhk} / Rs {formatRupees(data.rent)}/mo
          </p>
        </div>

        <div
          aria-label={`Livability score ${data.score} out of 100`}
          style={{
            width: "72px",
            height: "72px",
            borderRadius: "20px",
            border: `1px solid ${getScoreColor(data.score)}`,
            background: `color-mix(in oklch, ${getScoreColor(data.score)} 12%, transparent)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: getScoreColor(data.score),
            fontFamily: "var(--font-mono)",
            fontWeight: 800,
            fontSize: "1.6rem",
            letterSpacing: "-0.06em",
          }}
        >
          {data.score}
        </div>
      </div>

      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-6)" }}>
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
          <span className={`badge ${waterClass}`}>{data.water_risk} water risk</span>
          <span className={`badge ${commuteClass}`}>
            {commuteMins != null ? `${commuteMins}m commute` : "Commute unavailable"}
          </span>
          {data.is_duplicate && <span className="badge info">deduped</span>}
        </div>

        <div
          style={{
            height: "7px",
            borderRadius: "var(--radius-full)",
            background: "var(--ink-inset)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${data.score}%`,
              height: "100%",
              borderRadius: "inherit",
              background: getScoreColor(data.score),
            }}
          />
        </div>

        <div className="meta-row fine-print">
          <span>{data.score >= 75 ? "Clear signal" : data.score >= 50 ? "Needs review" : "High caution"}</span>
          <span>score / 100</span>
        </div>
      </div>
    </article>
  );
}
