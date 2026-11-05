'use client';

import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { RaSymbolInfo } from './raSymbols';

const WIDTH = 320;
const GAP = 6;

/** The pop-up for one symbol: its name, what it does, how to write it and an example. */
export function RaSymbolCard({ info }: { info: RaSymbolInfo }) {
  const code = { fontFamily: 'var(--font-geist-mono)', fontSize: 12 };
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 18, fontWeight: 700, minWidth: 18 }}>{info.symbol}</span>
        <strong style={{ fontSize: 14 }}>{info.name}</strong>
      </div>
      <span style={{ fontSize: 13 }}>{info.meaning}</span>
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 8, rowGap: 2, fontSize: 12 }}>
        <span style={{ color: 'var(--text-muted)' }}>Write:</span><span style={code}>{info.write}</span>
        <span style={{ color: 'var(--text-muted)' }}>Example:</span><span style={code}>{info.example}</span>
      </div>
    </div>
  );
}

/**
 * One floating symbol pop-up, placed under (or, near the bottom of the window, above) the
 * element being hovered. ``show`` it on hover or focus and ``hide`` it on leave or blur;
 * render ``tip`` anywhere. It hides on scroll, as its position would go stale.
 */
export function useRaSymbolTip() {
  const [state, setState] = useState<{ info: RaSymbolInfo; rect: DOMRect } | null>(null);

  const show = useCallback((info: RaSymbolInfo, el: Element) => setState({ info, rect: el.getBoundingClientRect() }), []);
  const hide = useCallback(() => setState(null), []);

  useEffect(() => {
    if (!state) return;
    window.addEventListener('scroll', hide, true);
    return () => window.removeEventListener('scroll', hide, true);
  }, [state, hide]);

  let tip = null;
  if (state && typeof document !== 'undefined') {
    const { rect } = state;
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - WIDTH - 8));
    const below = rect.bottom + 170 < window.innerHeight;
    tip = createPortal(
      <div role="tooltip" style={{
        position: 'fixed', zIndex: 1000, left, width: WIDTH, pointerEvents: 'none',
        ...(below ? { top: rect.bottom + GAP } : { bottom: window.innerHeight - rect.top + GAP }),
        padding: '10px 12px', borderRadius: 8, background: 'var(--surface)', color: 'var(--brand-charcoal)',
        border: '1px solid var(--border-strong)', boxShadow: '0 6px 20px rgba(0, 0, 0, 0.12)',
      }}>
        <RaSymbolCard info={state.info} />
      </div>,
      document.body,
    );
  }
  return { show, hide, tip };
}
