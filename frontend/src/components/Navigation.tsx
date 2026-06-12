"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "./AuthContext";
import { usePathname } from "next/navigation";

function useIsMobileNav() {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches
  );
  useLayoutEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return isMobile;
}

export default function Navigation() {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const isMobile = useIsMobileNav();

  useEffect(() => {
    if (!isMobile) setMenuOpen(false);
  }, [isMobile]);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  useEffect(() => {
    if (menuOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  if (pathname === "/login") return null;

  const closeMenu = () => setMenuOpen(false);

  const manualAuditClass =
    pathname === "/analyze" ? "nav-cta is-active" : "nav-cta nav-cta--spotlight";

  const authButtonStyle = {
    padding: "var(--space-2) var(--space-4)",
    fontSize: "0.85rem",
    borderRadius: "var(--radius-sm)",
  } as const;

  const nav = (
    <nav
      id="primary-nav-panel"
      className="nav-links"
      aria-label="Primary navigation"
      inert={Boolean(isMobile && !menuOpen)}
    >
      {isMobile ? (
        <button type="button" className="nav-drawer-close" onClick={closeMenu} aria-label="Close menu">
          <span aria-hidden="true">×</span>
        </button>
      ) : null}
      <Link href="/" className={pathname === "/" ? "nav-link is-active" : "nav-link"} onClick={closeMenu}>
        Feed
      </Link>
      {user ? (
        <>
          <Link
            href="/history"
            className={pathname.startsWith("/history") ? "nav-link is-active" : "nav-link"}
            onClick={closeMenu}
          >
            History
          </Link>
          <Link href="/analyze" className={manualAuditClass} onClick={closeMenu}>
            Manual Audit
          </Link>
          <button
            type="button"
            onClick={() => {
              closeMenu();
              signOut();
            }}
            className="btn-secondary"
            style={authButtonStyle}
          >
            Log Out
          </button>
        </>
      ) : (
        <>
          <Link href="/analyze" className={manualAuditClass} onClick={closeMenu}>
            Manual Audit
          </Link>
          <Link href="/login" className="btn-primary" style={authButtonStyle} onClick={closeMenu}>
            Log In
          </Link>
        </>
      )}
    </nav>
  );

  return (
    <div className={`nav-shell${menuOpen ? " is-open" : ""}`}>
      {isMobile
        ? createPortal(
            <div className={`nav-mobile-portal${menuOpen ? " is-open" : ""}`} data-nav-mobile-portal="">
              <div className="nav-drawer-backdrop" aria-hidden="true" onClick={closeMenu} />
              {nav}
            </div>,
            document.body
          )
        : nav}
      {isMobile ? (
        <button
          type="button"
          className="nav-menu-btn"
          aria-expanded={menuOpen}
          aria-controls="primary-nav-panel"
          id="primary-nav-toggle"
          onClick={() => setMenuOpen((o) => !o)}
        >
          <span className="visually-hidden">{menuOpen ? "Close menu" : "Open menu"}</span>
          <span className="nav-menu-icon" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </button>
      ) : null}
    </div>
  );
}
