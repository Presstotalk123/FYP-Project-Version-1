"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useAuth } from "@/contexts/AuthContext";

type HomepageCTA = {
  primary: { label: string; href: string };
  secondary: { label: string; href: string };
};

export default function Home() {
  const { loading, isAuthenticated, isStaff } = useAuth();

  const ctas = useMemo<HomepageCTA | null>(() => {
    if (loading) return null;
    if (!isAuthenticated) {
      return {
        primary: { label: "Start Practising", href: "/login" },
        secondary: { label: "Log In", href: "/login" },
      };
    }
    if (isStaff) {
      return {
        primary: { label: "Open Dashboard", href: "/admin" },
        secondary: { label: "Manage Problems", href: "/admin/problems" },
      };
    }
    return {
      primary: { label: "Continue SQL Practice", href: "/student" },
      secondary: { label: "Practice ER Diagram", href: "/student" },
    };
  }, [loading, isAuthenticated, isStaff]);

  return (
    <div className="home-screen">
      {/* ── Home-specific header ── */}
      <header className="home-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span>Database Assist</span>
        </div>
        <nav className="home-nav" aria-label="Site navigation">
          <Link href="/">Home</Link>
          <span className="inactive-nav">SQL</span>
          <span className="inactive-nav">ER Diagram</span>
          <a href="#home-process">How It Works</a>
        </nav>
        <div className="home-actions">
          {ctas ? (
            <>
              <Link href={ctas.secondary.href} style={{ color: 'var(--home-muted)', fontSize: 15, fontWeight: 750 }}>
                {isAuthenticated ? ctas.secondary.label : "Log In"}
              </Link>
              <Link href={ctas.primary.href} className="home-cta">
                {ctas.primary.label}
              </Link>
            </>
          ) : (
            <span style={{ color: 'var(--home-muted)', fontSize: 14 }}>Loading…</span>
          )}
        </div>
      </header>

      {/* ── Hero ── */}
      <div className="home-hero">
        <div className="home-copy">
          <h1>Write the query. Understand the reason.</h1>
          <p>
            Practise SQL and ER modelling with feedback that explains mistakes,
            guides your next step and builds lasting database confidence.
          </p>
          <div className="button-row">
            {ctas ? (
              <Link href={ctas.primary.href} className="btn btn-brand">
                {ctas.primary.label}
              </Link>
            ) : (
              <span className="btn btn-brand" style={{ opacity: 0.6 }}>Loading…</span>
            )}
          </div>
          <p className="home-proof">
            No setup required · Instant feedback · Learn at your own pace
          </p>
        </div>

        {/* SQL feedback demo */}
        <div
          className="learning-demo compact-workspace"
          aria-label="SQL feedback demonstration"
        >
          <p className="demo-question-text">
            <span>Practice example</span>
            Find the latest payment made by each customer.
          </p>
          <pre className="demo-code">
            <code>{`SELECT customer_id, `}<mark>payment_date</mark>{`, MAX(amount)
FROM payments
GROUP BY customer_id;`}</code>
          </pre>
          <div className="sql-note">
            <h3>Review this part of your query</h3>
            <p>
              <strong>payment_date</strong> is not tied to the maximum payment.
              Grouping returns one maximum amount for each customer, but it does
              not identify which payment row supplied that amount.
            </p>
            <p className="hint">
              Hint: Find the row containing each customer&apos;s latest payment
              before selecting its other values.
            </p>
          </div>
          <div className="result-summary">
            <span>Result preview</span>
            <strong>Returned row: Customer 104 · 3 Feb 2024 · $48.00</strong>
          </div>
        </div>
      </div>

      {/* ── How It Works ── */}
      <div className="cycle-section" id="home-process">
        <div className="section-copy">
          <span className="eyebrow">How It Works</span>
          <h2>From attempt to understanding.</h2>
        </div>
        <div className="cycle-row">
          <article>
            <span>1</span>
            <h3>Attempt</h3>
            <p>Solve a focused SQL or ER Diagram exercise.</p>
          </article>
          <article>
            <span>2</span>
            <h3>Review</h3>
            <p>See what worked and what needs attention.</p>
          </article>
          <article>
            <span>3</span>
            <h3>Understand</h3>
            <p>Learn why the result occurred.</p>
          </article>
          <article>
            <span>4</span>
            <h3>Apply</h3>
            <p>Try a related exercise and reinforce the concept.</p>
          </article>
        </div>
      </div>

      {/* ── Final CTA ── */}
      <div className="home-final">
        <pre>
          <code>{`SELECT confidence
FROM practice
WHERE mistakes = 'explained';`}</code>
        </pre>
        <div>
          <h2>Your next correct answer starts with understanding the last mistake.</h2>
          <p>Practise with feedback that turns errors into the next useful step.</p>
          {ctas && (
            <Link href={ctas.primary.href} className="btn btn-secondary">
              {ctas.primary.label}
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
