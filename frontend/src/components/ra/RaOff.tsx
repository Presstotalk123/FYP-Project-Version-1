'use client';

/** Shown on every RA page while the module is switched off (RA_ENABLED). */
export function RaOff() {
  return (
    <div className="card" style={{ padding: 24, maxWidth: 640 }}>
      <h2 style={{ marginTop: 0 }}>Relational Algebra is switched off</h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 0 }}>
        Set <code>RA_ENABLED=true</code> in <code>backend/.env</code> and restart the backend.
      </p>
    </div>
  );
}

export const RA_DIFFICULTY_LABEL: Record<string, string> = { easy: 'Easy', medium: 'Medium', hard: 'Hard' };
