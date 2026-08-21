'use client';

import { useCallback, useEffect, useRef } from 'react';

import { toPngFile } from '@/components/DrawioBoard';

/**
 * Draw a draw.io XML source to a PNG, off screen.
 *
 * Why: only image submissions store a picture, so an attempt graded from XML has
 * nothing for staff to look at in analytics. draw.io itself is the only thing that
 * can render its own format, and it lives in a cross-origin iframe, so the picture
 * has to be made in the browser before the request goes out.
 *
 * The PNG is decoration, never evidence: grading reads the XML, which is exact.
 * Every failure path therefore resolves to null rather than throwing, so a slow or
 * silent draw.io can never block a grade.
 */

/** The frame URL every caller must give its off-screen iframe. Exported so the
 *  constant lives in one place rather than being restated at each call site. */
export const DRAWIO_RENDERER_URL =
  process.env.NEXT_PUBLIC_DRAWIO_ORIGIN?.trim() ??
  'https://embed.diagrams.net/?embed=1&spin=1&ui=min&libs=er;general&proto=json';

const EDITOR_ORIGIN = (() => {
  try {
    return new URL(DRAWIO_RENDERER_URL).origin;
  } catch {
    return DRAWIO_RENDERER_URL;
  }
})();

// draw.io ignores a load sent before its own `init`, and offers no readiness query.
const LOAD_RETRY_MS = 250;
// Generous: a cold iframe must boot, parse the diagram and rasterise it. Past this
// the caller submits without a picture rather than waiting any longer.
const RENDER_TIMEOUT_MS = 15_000;

export interface ErXmlToPng {
  /** Attach to an off-screen iframe. */
  frameRef: React.RefObject<HTMLIFrameElement | null>;
  /** Resolves to the PNG, or null when draw.io did not produce one in time. */
  render: (xml: string) => Promise<File | null>;
}

export function useErXmlToPng(): ErXmlToPng {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const pendingRef = useRef<((file: File | null) => void) | null>(null);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== EDITOR_ORIGIN) return;
      if (event.source !== frameRef.current?.contentWindow) return;

      let data: { event?: string; format?: string; data?: string };
      try {
        data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
      } catch {
        return;
      }
      if (data?.event !== 'export' || data.format === 'xml') return;

      const settle = pendingRef.current;
      if (!settle) return;
      pendingRef.current = null;

      void (async () => {
        try {
          settle(await toPngFile(data.data ?? ''));
        } catch {
          settle(null);
        }
      })();
    };

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  const render = useCallback((xml: string) => {
    const frame = frameRef.current?.contentWindow;
    if (!frame) return Promise.resolve<File | null>(null);

    return new Promise<File | null>((resolve) => {
      let done = false;
      const settle = (file: File | null) => {
        if (done) return;
        done = true;
        window.clearInterval(retry);
        window.clearTimeout(timeout);
        resolve(file);
      };
      pendingRef.current = settle;

      // Load, then ask for the same white-background PNG a student's submit
      // produces. Both messages are retried because only draw.io knows when it
      // is listening; a duplicate load is harmless.
      const post = () => {
        frame.postMessage(JSON.stringify({ action: 'load', xml, autosave: 0 }), EDITOR_ORIGIN);
        frame.postMessage(
          JSON.stringify({ action: 'export', format: 'png', bg: '#ffffff', transparent: false }),
          EDITOR_ORIGIN,
        );
      };

      const retry = window.setInterval(post, LOAD_RETRY_MS);
      const timeout = window.setTimeout(() => {
        pendingRef.current = null;
        settle(null);
      }, RENDER_TIMEOUT_MS);
      post();
    });
  }, []);

  return { frameRef, render };
}

/** Where the renderer's iframe must sit: real pixels so draw.io rasterises a real
 *  diagram, but out of view. `display: none` or a zero size yields a blank export. */
export const OFFSCREEN_FRAME_STYLE: React.CSSProperties = {
  position: 'fixed',
  left: -10000,
  top: 0,
  width: 1200,
  height: 800,
  border: 0,
  visibility: 'hidden',
};
