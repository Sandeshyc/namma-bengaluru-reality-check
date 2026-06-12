import Link from "next/link";
import ListingCard from "../components/ListingCard";

// Mock data for initial frontend build
const MOCK_LISTINGS = [
  {
    id: "1",
    location: "Koramangala 4th Block",
    rent: 35000,
    bhk: "2 BHK",
    score: 85,
    water_risk: "Low",
    commute_avg: 25,
    is_duplicate: false
  },
  {
    id: "2",
    location: "Bellandur (Outer Ring Road)",
    rent: 42000,
    bhk: "3 BHK",
    score: 42,
    water_risk: "High",
    commute_avg: 55,
    is_duplicate: false
  },
  {
    id: "3",
    location: "Indiranagar 100ft Road",
    rent: 45000,
    bhk: "2 BHK",
    score: 92,
    water_risk: "Low",
    commute_avg: 20,
    is_duplicate: false
  },
  {
    id: "4",
    location: "Whitefield (Near ITPB)",
    rent: 28000,
    bhk: "2 BHK",
    score: 60,
    water_risk: "Medium",
    commute_avg: 45,
    is_duplicate: true
  }
];

const PIPELINE_STEPS = [
  {
    label: "Prompt cache",
    detail: "Hash every broker message before Gemini runs.",
    impact: "Prevents repeat token spend on identical listings.",
    status: "cost guard",
  },
  {
    label: "Spatial duplicate",
    detail: "Match embeddings and nearby coordinates inside PostGIS.",
    impact: "Catches reposted broker ads within a 500m radius.",
    status: "dedupe",
  },
  {
    label: "Commute cache",
    detail: "Reuse route times for known location and tech-park pairs.",
    impact: "Avoids repeated routing API calls for the same commute.",
    status: "api save",
  },
  {
    label: "Ward water join",
    detail: "Join listing coordinates to GBA wards and water signals.",
    impact: "Turns civic infrastructure data into rental risk scoring.",
    status: "PostGIS",
  },
];

export default function Home() {
  return (
    <div className="animate-slide-up" style={{ animationDelay: "0.1s" }}>
      <section className="hero-grid">
        <div className="panel hero-copy">
          <div>
            <div className="section-header" data-step="01">
              <span className="eyebrow">Broker claims meet civic evidence</span>
            </div>
            <h1 className="hero-title">
              Don&apos;t rent blind in <span className="text-gradient">Bengaluru.</span>
            </h1>
            <p className="hero-subtitle">
              Paste a broker message and get an evidence-backed livability score across commute,
              water security, deposit pressure, duplicate listings, and ward-level civic context.
            </p>
            <div className="hero-actions">
              <Link href="/analyze" className="btn-primary">
                Audit a listing
                <span aria-hidden="true">-&gt;</span>
              </Link>
              <a href="#intel-feed" className="btn-secondary">
                View sample feed
              </a>
            </div>
            
            <div style={{ position: "relative", marginTop: "var(--space-10)", marginBottom: "-2rem", flexGrow: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <img 
                src="/map-garden.jpg" 
                alt="Stylized Bengaluru Map" 
                className="float-animation"
                style={{
                  maxWidth: "100%",
                  height: "auto",
                  maskImage: "radial-gradient(circle at center, black 50%, transparent 95%)",
                  WebkitMaskImage: "radial-gradient(circle at center, black 50%, transparent 95%)",
                  opacity: 1
                }}
              />
            </div>
          </div>

          <div className="intel-strip" aria-label="System capabilities">
            <div className="intel-tile">
              <div className="intel-value">500m</div>
              <div className="intel-label">spatial duplicate radius</div>
            </div>
            <div className="intel-tile">
              <div className="intel-value">5</div>
              <div className="intel-label">tech park commute checks</div>
            </div>
            <div className="intel-tile">
              <div className="intel-value">369</div>
              <div className="intel-label">GBA ward polygons loaded</div>
            </div>
          </div>
        </div>

        <aside className="panel map-card" aria-label="Bengaluru intelligence map preview">
          <div className="section-header" data-step="02">
            <span className="eyebrow">Spatial cache first</span>
          </div>
          <div className="map-visual">
            <span className="map-pin pin-a" />
            <span className="map-pin pin-b" />
            <span className="map-pin pin-c" />
            <div className="map-caption">
              <div className="meta-row">
                <span className="badge info">PostGIS join</span>
                <span className="fine-print">Indiranagar sample</span>
              </div>
              <h3 style={{ marginTop: "10px" }}>Ward, water, commute, duplicate</h3>
              <p className="fine-print" style={{ marginTop: "6px" }}>
                The UI mirrors the pipeline: cache lookup, geocode, vector match, commute cache,
                water score, then persistence.
              </p>
            </div>
          </div>
          <div className="audit-path" aria-label="Cache-first audit path">
            <div className="meta-row">
              <span className="eyebrow">Architecture decisions</span>
              <span className="badge success">LLM guarded</span>
            </div>
            <p className="audit-path-intro">
              Built to show product judgment: every expensive or noisy operation is preceded by a
              deterministic database lookup.
            </p>

            <div className="pipeline-stack">
              {PIPELINE_STEPS.map((step, index) => (
                <div className="pipeline-step" key={step.label}>
                  <span className="pipeline-index">0{index + 1}</span>
                  <div>
                    <strong>{step.label}</strong>
                    <p className="fine-print">{step.detail}</p>
                    <p className="pipeline-impact">{step.impact}</p>
                  </div>
                  <span className="pipeline-status">{step.status}</span>
                </div>
              ))}
            </div>

            <div className="audit-metrics">
              <div>
                <span className="data-value">0</span>
                <span className="fine-print">LLM calls on cache hit</span>
              </div>
              <div>
                <span className="data-value">3-5s</span>
                <span className="fine-print">AI throttle window</span>
              </div>
            </div>
          </div>
        </aside>
      </section>

      <section id="intel-feed" style={{ marginTop: "var(--space-8)" }}>
        <div className="meta-row" style={{ marginBottom: "var(--space-5)" }}>
          <div>
            <div className="section-header" data-step="03">
              <span className="eyebrow">Sample intelligence feed</span>
            </div>
            <h2 style={{ fontSize: "1.8rem" }}>Recent listing audits</h2>
          </div>
          <span className="badge neutral">Mock data</span>
        </div>

        <div className="dashboard-grid">
          {MOCK_LISTINGS.map((listing) => (
          <ListingCard key={listing.id} data={listing} />
          ))}
        </div>
      </section>
    </div>
  );
}
