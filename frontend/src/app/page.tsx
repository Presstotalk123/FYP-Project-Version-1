"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useAuth } from "@/contexts/AuthContext";
import styles from "./page.module.css";

type HomepageCTA = {
  primary: { label: string; href: string };
  secondary: { label: string; href: string };
};

export default function Home() {
  const { loading, isAuthenticated, isStaff } = useAuth();

  const ctas = useMemo<HomepageCTA | null>(() => {
    if (loading) {
      return null;
    }

    if (!isAuthenticated) {
      return {
        primary: { label: "Get Started", href: "/register" },
        secondary: { label: "Log In", href: "/login" },
      };
    }

    if (isStaff) {
      return {
        primary: { label: "Open Dashboard", href: "/admin" },
        secondary: { label: "Practice ER Diagram", href: "/er-diagram" },
      };
    }

    return {
      primary: { label: "Continue SQL Practice", href: "/student" },
      secondary: { label: "Practice ER Diagram", href: "/er-diagram" },
    };
  }, [loading, isAuthenticated, isStaff]);

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <section className={styles.hero}>
          <p className={styles.kicker}>Database Assist</p>
          <h1 className={styles.heroTitle}>
            Practice SQL and ER diagrams with guided feedback designed for learning.
          </h1>
          <p className={styles.heroSubtitle}>
            Build confidence through structured practice, clear scoring signals, and AI support that helps you
            understand why an answer works.
          </p>
          {ctas ? (
            <div className={styles.ctas}>
              <Link className={styles.primary} href={ctas.primary.href}>
                {ctas.primary.label}
              </Link>
              <Link className={styles.secondary} href={ctas.secondary.href}>
                {ctas.secondary.label}
              </Link>
            </div>
          ) : (
            <p className={styles.loadingLabel}>Preparing your learning shortcuts...</p>
          )}
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>What You Can Practice</h2>
          <div className={styles.featureGrid}>
            <article className={styles.featureCard}>
              <h3>SQL Practice Workspace</h3>
              <p>
                Solve hands-on SQL questions, run queries instantly, and learn from correctness checks and attempt
                history.
              </p>
            </article>
            <article className={styles.featureCard}>
              <h3>ER Diagram Challenges</h3>
              <p>
                Attempt ERD questions with draw.io or image upload, then review structured feedback and score results.
              </p>
            </article>
            <article className={styles.featureCard}>
              <h3>Pedagogical AI Support</h3>
              <p>
                Ask targeted questions during practice and get learning-oriented guidance instead of just final answers.
              </p>
            </article>
          </div>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>How Learning Works</h2>
          <div className={styles.steps}>
            <article className={styles.step}>
              <span className={styles.stepNumber}>1</span>
              <div>
                <h3>Pick a Practice Track</h3>
                <p>Start with SQL questions or ER diagram practice based on what you want to improve.</p>
              </div>
            </article>
            <article className={styles.step}>
              <span className={styles.stepNumber}>2</span>
              <div>
                <h3>Submit and Evaluate</h3>
                <p>Run your solution and immediately see execution outcomes, scoring cues, and key feedback points.</p>
              </div>
            </article>
            <article className={styles.step}>
              <span className={styles.stepNumber}>3</span>
              <div>
                <h3>Reflect and Iterate</h3>
                <p>Use AI chat and rubric-guided feedback to fix gaps and improve with each new attempt.</p>
              </div>
            </article>
          </div>
        </section>

        <section className={styles.callout}>
          <h2>Learn by Doing, Not Memorizing</h2>
          <p>Move from concept to confidence with continuous, feedback-driven database practice.</p>
          {ctas ? (
            <div className={styles.ctas}>
              <Link className={styles.primary} href={ctas.primary.href}>
                {ctas.primary.label}
              </Link>
              <Link className={styles.secondary} href={ctas.secondary.href}>
                {ctas.secondary.label}
              </Link>
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
