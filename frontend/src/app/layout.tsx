import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { AppProviders } from "../components/AppProviders";
import NavigationDynamic from "../components/NavigationDynamic";

export const metadata: Metadata = {
  title: "Namma Bengaluru Reality-Check",
  description: "AI-powered ETL pipeline scoring Bengaluru rentals on commute, water security, and civic data.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AppProviders>
          <div className="container app-shell">
            <header className="header animate-header-in">
              <div className="header-inner">
                <Link href="/" className="brand" aria-label="Namma Bengaluru Reality Check home">
                  <img src="/logo.png" className="brand-mark" alt="Reality Check Logo" />
                  <div>
                    <div className="brand-kicker">Rental Intelligence</div>
                    <h2 className="brand-title">Reality<span className="text-gradient">Check</span></h2>
                  </div>
                </Link>
                <NavigationDynamic />
              </div>
            </header>
            <main>
              {children}
            </main>
            <footer className="app-footer">
              <div className="footer-grid">
                <p>Built for Bengaluru renters who want evidence before deposits.</p>
                <p className="hidden md:block">
                  Geocoding by Google Maps / LocationIQ. Routing by Ola Maps. Civic joins by PostGIS.
                </p>
              </div>
            </footer>
          </div>
        </AppProviders>
      </body>
    </html>
  );
}

