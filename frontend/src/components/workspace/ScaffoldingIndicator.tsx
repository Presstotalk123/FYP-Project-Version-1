'use client';

import React, { useEffect, useState } from 'react';
import { ladService } from '@/services/lad.service';
import { ScaffoldingLevel } from '@/types/lad.types';

interface ScaffoldingIndicatorProps {
  questionId: number;
  // Change (by identity) to force a refetch, e.g. pass the latest submission result,
  // since a submission is what can change the level.
  refreshKey?: unknown;
}

// Visual style per level. Ordered full -> independent (most -> least AI support).
const LEVEL_META: Record<
  ScaffoldingLevel,
  { label: string; color: string; bg: string; title: string }
> = {
  full: {
    label: 'Full support',
    color: '#1d4ed8',
    bg: 'rgba(37, 99, 235, 0.12)',
    title: 'The tutor gives direct hints and explanations.',
  },
  guided: {
    label: 'Guided',
    color: '#0891b2',
    bg: 'rgba(8, 145, 178, 0.12)',
    title: 'The tutor pairs hints with reflective questions.',
  },
  minimal: {
    label: 'Minimal',
    color: '#d97706',
    bg: 'rgba(217, 119, 6, 0.12)',
    title: 'The tutor mostly asks probing questions; hints are withheld.',
  },
  independent: {
    label: 'Independent',
    color: '#059669',
    bg: 'rgba(5, 150, 105, 0.12)',
    title: 'You’ve shown mastery — the tutor only asks you to reason it through.',
  },
};

/**
 * Small badge in the chat header showing the student's current AI-support level
 * for this question. Self-contained and best-effort: if the fetch fails (e.g. the
 * adaptive feature is off) it renders nothing.
 */
export function ScaffoldingIndicator({ questionId, refreshKey }: ScaffoldingIndicatorProps) {
  const [level, setLevel] = useState<ScaffoldingLevel | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      ladService
        .getScaffolding(questionId)
        .then((state) => {
          if (!cancelled) setLevel(state.scaffolding_level);
        })
        .catch(() => {
          if (!cancelled) setLevel(null);
        });
    load();
    // The level is updated by a background task after the submission response is
    // sent, so re-check shortly after a refresh to pick up that write.
    const retry = refreshKey != null ? setTimeout(load, 2000) : undefined;
    return () => {
      cancelled = true;
      if (retry) clearTimeout(retry);
    };
  }, [questionId, refreshKey]);

  if (!level) return null;
  const meta = LEVEL_META[level] ?? LEVEL_META.full;

  return (
    <div
      title={meta.title}
      aria-label={`AI support level: ${meta.label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 10px',
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 600,
        color: meta.color,
        background: meta.bg,
        border: `1px solid ${meta.color}33`,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: meta.color,
          display: 'inline-block',
        }}
      />
      AI support: {meta.label}
    </div>
  );
}
