'use client';

import { useEffect, useState } from 'react';
import 'katex/dist/katex.min.css';
import { raService } from '@/services/ra.service';
import { RaNotationResponse } from '@/types/ra.types';

type Katex = typeof import('katex');

/**
 * The answer in textbook notation, one line per statement: σ with its condition as a
 * subscript, ← for :=, and brackets around exactly what each operator applies to. It is
 * printed from the parsed answer, so it shows how the answer was read. Updates while typing.
 */
export function RaNotation({ program, names }: { program: string; names?: string[] }) {
  const [katex, setKatex] = useState<Katex | null>(null);
  const [notation, setNotation] = useState<RaNotationResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    void import('katex').then((m) => setKatex(m.default ?? m));
  }, []);

  // A key, not the array: callers may build a new names array on every render.
  const namesKey = (names ?? []).join('\n');
  useEffect(() => {
    let current = true;
    setPending(true);
    const timer = setTimeout(() => {
      raService.notation(program, namesKey ? namesKey.split('\n') : [])
        .then((r) => { if (current) { setNotation(r); setOffline(false); } })
        .catch(() => { if (current) setOffline(true); })
        .finally(() => { if (current) setPending(false); });
    }, 350);
    return () => { current = false; clearTimeout(timer); };
  }, [program, namesKey]);

  const render = (latex: string) => katex
    ? katex.renderToString(latex, { throwOnError: false, displayMode: false, strict: 'ignore' })
    : latex;

  let body;
  if (offline) {
    body = <span style={muted}>The notation preview could not reach the server.</span>;
  } else if (!notation || (!notation.ok && !notation.error)) {
    body = <span style={muted}>…</span>;
  } else if (!notation.ok && notation.error) {
    const e = notation.error;
    body = (
      <span style={muted}>
        Can&apos;t show the notation until the answer can be read: {e.line ? `line ${e.line}: ` : ''}{e.message}
      </span>
    );
  } else if (notation.lines.length === 0) {
    body = <span style={muted}>Type an answer to see it in textbook notation.</span>;
  } else {
    body = (
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 12, rowGap: 6, alignItems: 'baseline' }}>
        {notation.lines.map((l, i) => (
          <div key={i} style={{ display: 'contents' }}>
            <span style={{ ...muted, fontSize: 11 }}>{l.line != null ? `line ${l.line}` : ''}</span>
            <span style={{ fontSize: 17, overflowX: 'auto', whiteSpace: 'nowrap', padding: '2px 0' }}
              dangerouslySetInnerHTML={{ __html: render(l.latex) }} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div aria-live="polite" style={{
      padding: '10px 12px', borderTop: '1px solid var(--border)', background: 'var(--surface)',
      opacity: pending && notation ? 0.6 : 1, transition: 'opacity 120ms',
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, letterSpacing: 0.3 }}>
        NOTATION PREVIEW · as the answer is read (brackets show what each operator applies to)
      </div>
      {body}
    </div>
  );
}

const muted: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)' };
