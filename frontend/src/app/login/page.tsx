"use client";

import { useState } from "react";
import Link from "next/link";
import { supabase } from "../../supabase";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const router = useRouter();

  const switchMode = (signUp: boolean) => {
    setIsSignUp(signUp);
    setError(null);
    setSuccessMsg(null);
  };

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      if (isSignUp) {
        const { error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: `${window.location.origin}/`,
          },
        });
        if (error) throw error;
        setSuccessMsg("Check your inbox to confirm your email, then sign in.");
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (error) throw error;
        router.push("/");
      }
    } catch (err: unknown) {
      console.error(err);
      const message = err instanceof Error ? err.message : "Something went wrong. Try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page auth-entrance">
      <div className="auth-layout">
        <aside className="auth-aside" aria-hidden="false">
          <span className="eyebrow">Secure access</span>
          <h1>
            Sign in to run{" "}
            <span className="text-gradient">reality checks</span>
          </h1>
          <p>
            Save analyses, revisit commute and water scores, and keep a paper trail before you pay a deposit.
          </p>
          <div className="auth-highlights">
            <div className="auth-highlight">
              <span className="auth-highlight-dot" aria-hidden />
              <div>
                <strong>PostGIS-backed joins</strong>
                <span>Listings matched to wards, buffers, and civic layers—not vibes.</span>
              </div>
            </div>
            <div className="auth-highlight">
              <span className="auth-highlight-dot" aria-hidden />
              <div>
                <strong>Your history, exportable</strong>
                <span>Return to past runs and compare neighbourhoods side by side.</span>
              </div>
            </div>
            <div className="auth-highlight">
              <span className="auth-highlight-dot" aria-hidden />
              <div>
                <strong>RLS-protected data</strong>
                <span>We use Supabase Auth; your account is isolated from other users.</span>
              </div>
            </div>
          </div>
        </aside>

        <div className="auth-card">
          <div className="auth-card-inner">
            <Link href="/" className="auth-back">
              ← Back to home
            </Link>

            <div className="auth-segment" role="tablist" aria-label="Authentication mode">
              <button
                type="button"
                role="tab"
                aria-selected={!isSignUp}
                className={!isSignUp ? "is-active" : ""}
                onClick={() => switchMode(false)}
              >
                Sign in
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={isSignUp}
                className={isSignUp ? "is-active" : ""}
                onClick={() => switchMode(true)}
              >
                Create account
              </button>
            </div>

            <h2 className="auth-card-title">{isSignUp ? "Create your account" : "Welcome back"}</h2>
            <p className="auth-card-sub">
              {isSignUp
                ? "Use a real email—you’ll verify it once before your first analysis."
                : "Enter the email and password you used when you signed up."}
            </p>

            <form className="auth-form" onSubmit={handleAuth} noValidate>
              <div>
                <label className="auth-label" htmlFor="email">
                  Email
                </label>
                <input
                  type="email"
                  id="email"
                  autoComplete="email"
                  required
                  className="form-input"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                />
              </div>

              <div>
                <label className="auth-label" htmlFor="password">
                  Password
                </label>
                <input
                  type="password"
                  id="password"
                  autoComplete={isSignUp ? "new-password" : "current-password"}
                  required
                  minLength={6}
                  className="form-input"
                  placeholder="At least 6 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                />
              </div>

              {error && (
                <div className="auth-alert auth-alert--error" role="alert">
                  {error}
                </div>
              )}

              {successMsg && (
                <div className="auth-alert auth-alert--success" role="status">
                  {successMsg}
                </div>
              )}

              <button type="submit" className="btn-primary" style={{ width: "100%" }} disabled={loading}>
                {loading ? "Please wait…" : isSignUp ? "Send confirmation email" : "Sign in & continue"}
              </button>
            </form>

            <p className="auth-footnote">
              {isSignUp ? (
                <>
                  Already registered?
                  <button type="button" onClick={() => switchMode(false)}>
                    Sign in instead
                  </button>
                </>
              ) : (
                <>
                  New here?
                  <button type="button" onClick={() => switchMode(true)}>
                    Create an account
                  </button>
                </>
              )}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
