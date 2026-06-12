"use client";

import Link from "next/link";
import { useAuth } from "./AuthContext";
import { usePathname } from "next/navigation";

export default function Navigation() {
  const { user, signOut } = useAuth();
  const pathname = usePathname();

  if (pathname === "/login") return null;

  const manualAuditClass =
    pathname === "/analyze" ? "nav-cta is-active" : "nav-cta nav-cta--spotlight";

  return (
    <nav className="nav-links" aria-label="Primary navigation" style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
      <Link href="/" className={pathname === "/" ? "nav-link is-active" : "nav-link"}>Feed</Link>
      {user ? (
        <>
          <Link href="/history" className={pathname.startsWith("/history") ? "nav-link is-active" : "nav-link"}>History</Link>
          <Link href="/analyze" className={manualAuditClass}>Manual Audit</Link>
          <button 
            onClick={signOut} 
            className="btn-secondary" 
            style={{ 
              padding: "var(--space-2) var(--space-4)", 
              fontSize: "0.85rem",
              borderRadius: "var(--radius-sm)"
            }}
          >
            Log Out
          </button>
        </>
      ) : (
        <>
          <Link href="/analyze" className={manualAuditClass}>Manual Audit</Link>
          <Link href="/login" className="btn-primary" style={{ padding: "var(--space-2) var(--space-4)", fontSize: "0.85rem", borderRadius: "var(--radius-sm)" }}>
            Log In
          </Link>
        </>
      )}
    </nav>
  );
}
