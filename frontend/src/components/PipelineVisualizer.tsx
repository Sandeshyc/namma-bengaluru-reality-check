"use client";

import { useEffect, useState } from "react";

const NODES = [
  { label: "Extract", detail: "Gemini Flash + prompt cache" },
  { label: "Locate", detail: "Google Maps bounded to Bengaluru" },
  { label: "Dedup", detail: "pgvector + 500m spatial radius" },
  { label: "Route", detail: "Ola Maps via commute cache" },
  { label: "Civic", detail: "PostGIS ward and water lookup" },
  { label: "Score", detail: "100-point livability model" },
  { label: "Persist", detail: "Supabase listing record" },
];

export default function PipelineVisualizer({ isRunning }: { isRunning: boolean }) {
  const [activeNode, setActiveNode] = useState(-1);

  useEffect(() => {
    if (!isRunning) return;

    let current = 0;
    const start = setTimeout(() => setActiveNode(current), 0);
    const interval = setInterval(() => {
      current++;
      setActiveNode(current);
      if (current >= NODES.length - 1) {
        clearInterval(interval);
      }
    }, 600);

    return () => {
      clearTimeout(start);
      clearInterval(interval);
    };
  }, [isRunning]);

  const displayActiveNode = isRunning ? activeNode : NODES.length;

  return (
    <section className="panel" style={{ padding: "var(--space-5)" }}>
      <div className="meta-row" style={{ marginBottom: "var(--space-5)" }}>
        <div>
          <span className="eyebrow">Live pipeline</span>
          <h3 style={{ marginTop: "6px" }}>Evidence chain</h3>
        </div>
        <span className={`badge ${isRunning ? "info" : "success"}`}>
          {isRunning ? "running" : "complete"}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {NODES.map((node, index) => {
          const isActive = index === displayActiveNode;
          const isComplete = index < displayActiveNode;
          
          return (
            <div key={node.label} style={{ display: "flex", gap: "var(--space-4)", position: "relative" }}>
              {index < NODES.length - 1 && (
                <div style={{
                  position: "absolute",
                  left: "15px",
                  top: "34px",
                  bottom: "-8px",
                  width: "1px",
                  background: isComplete ? "var(--cauvery)" : "var(--border)",
                  zIndex: 0
                }} />
              )}
              
              <div style={{ 
                width: "32px",
                height: "32px",
                borderRadius: "10px",
                background: isActive
                  ? "var(--cauvery)"
                  : isComplete
                  ? "color-mix(in oklch, var(--cauvery) 18%, var(--ink-panel))"
                  : "var(--ink-inset)",
                border: `1px solid ${isActive || isComplete ? "var(--cauvery)" : "var(--border)"}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1,
                boxShadow: isActive ? "0 0 22px var(--cauvery-glow)" : "none",
                transition: "all 220ms var(--ease-standard)"
              }}>
                {isComplete && <span style={{ color: "var(--cauvery-strong)", fontSize: "14px" }}>✓</span>}
                {isActive && (
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: "var(--ink-map)",
                      animation: "pulseDot 1s infinite",
                    }}
                  />
                )}
              </div>
              
              <div style={{ paddingBottom: "var(--space-5)", paddingTop: "2px" }}>
                <p style={{ 
                  fontWeight: isActive ? 700 : 600,
                  color: isActive ? "var(--text-main)" : isComplete ? "var(--text-soft)" : "var(--text-faint)",
                  transition: "all 220ms var(--ease-standard)"
                }}>
                  {node.label}
                </p>
                <p className="fine-print" style={{ marginTop: "2px" }}>{node.detail}</p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
