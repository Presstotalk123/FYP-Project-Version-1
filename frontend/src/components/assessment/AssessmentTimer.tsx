'use client';

import { Badge, Tooltip } from '@mantine/core';
import { IconClock, IconAlertTriangle, IconPlayerPause } from '@tabler/icons-react';
import { useAssessmentTimer } from '@/contexts/AssessmentTimerContext';

const FIVE_MIN_MS = 5 * 60 * 1000;

function formatHHMMSS(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

/**
 * Live assessment countdown, formatted HH:MM:SS. Turns red under 5 minutes remaining.
 * Renders nothing for untimed assessments (no deadline). Purely cosmetic — the backend
 * `end_time` is the source of truth and is enforced lazily on every request.
 */
export function AssessmentTimer() {
  const { hasTimer, remainingMs, isPaused } = useAssessmentTimer();

  if (!hasTimer) return null;

  const warning = remainingMs < FIVE_MIN_MS;
  const color = warning ? 'red' : 'blue';

  const leftIcon = isPaused ? (
    <IconPlayerPause size={16} />
  ) : warning ? (
    <IconAlertTriangle size={16} />
  ) : (
    <IconClock size={16} />
  );

  const label = isPaused
    ? 'Paused while your query runs — your time is not counting down.'
    : warning
      ? 'Less than 5 minutes remaining!'
      : 'Time remaining';

  return (
    <Tooltip label={label} withArrow>
      <Badge
        size="lg"
        variant={warning ? 'filled' : 'light'}
        color={color}
        leftSection={leftIcon}
        style={{ fontVariantNumeric: 'tabular-nums', opacity: isPaused ? 0.7 : 1 }}
      >
        {formatHHMMSS(remainingMs)}
      </Badge>
    </Tooltip>
  );
}
