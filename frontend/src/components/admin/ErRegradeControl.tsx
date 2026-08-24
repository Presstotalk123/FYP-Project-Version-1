'use client';

import { useEffect, useRef, useState } from 'react';
import {
  fetchRegradeStatus,
  startRegrade,
  type RegradeStatus,
} from '@/services/er-analytics.service';
import { getApiErrorMessage } from '@/utils/api-error';

const POLL_MS = 3000;

/**
 * Button + confirm dialog + progress banner for a question-wide regrade.
 *
 * The regrade replays every stored submission through the grading pipeline
 * against the question's CURRENT rubric, and replaces the stored grades —
 * staff overrides included. It is an explicit staff choice, scoped to one
 * class group or to everyone, and runs as a backend job this control polls.
 *
 * `autoOpen` opens the dialog on mount — the rubric editor routes here with
 * ?regrade=1 after a save, so "save, then choose whether to regrade" is one
 * flow with a single implementation of the dialog.
 */
export function ErRegradeControl({
  questionId,
  classGroups,
  autoOpen = false,
  onFinished,
}: {
  questionId: number;
  classGroups: string[];
  autoOpen?: boolean;
  onFinished?: () => void;
}) {
  const [modalOpen, setModalOpen] = useState(autoOpen);
  const [group, setGroup] = useState('');
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [status, setStatus] = useState<RegradeStatus | null>(null);
  // The finished callback must fire once per job, not once per poll.
  const notifiedRef = useRef(false);

  const running = status?.exists && status.status === 'running';

  // One fetch on mount picks up a job started elsewhere (another tab, or a
  // save-and-regrade flow that navigated here); the interval then follows it.
  useEffect(() => {
    let cancelled = false;
    const read = async () => {
      try {
        const s = await fetchRegradeStatus(questionId);
        if (!cancelled) setStatus(s.exists ? s : null);
      } catch {
        /* a failed poll changes nothing; the next one retries */
      }
    };
    void read();
    const timer = setInterval(() => {
      void read();
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [questionId]);

  useEffect(() => {
    if (!status?.exists) return;
    if (status.status === 'running') {
      notifiedRef.current = false;
      return;
    }
    if (!notifiedRef.current) {
      notifiedRef.current = true;
      onFinished?.();
    }
  }, [status, onFinished]);

  const begin = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const s = await startRegrade(questionId, group || null);
      setStatus(s);
      setModalOpen(false);
    } catch (err) {
      setStartError(getApiErrorMessage(err, 'Failed to start the regrade'));
    } finally {
      setStarting(false);
    }
  };

  return (
    <>
      <button
        className="btn btn-secondary"
        onClick={() => {
          setStartError(null);
          setModalOpen(true);
        }}
        disabled={Boolean(running)}
      >
        {running ? 'Regrading…' : 'Regrade scores'}
      </button>

      {status?.exists && (
        <div
          className={`da-alert ${status.status === 'failed' ? 'alert-error' : 'alert-info'}`}
          style={{ fontSize: 12, marginTop: 8 }}
          role="status"
        >
          <span>
            {status.status === 'running' && (
              <>
                Regrading{status.class_group ? ` ${status.class_group}` : ''}…{' '}
                {status.completed ?? 0} of {status.total ?? '?'} submissions done.
              </>
            )}
            {status.status === 'done' && (
              <>
                Regrade finished{status.class_group ? ` for ${status.class_group}` : ''}:{' '}
                {status.regraded ?? 0} regraded
                {status.skipped ? `, ${status.skipped} skipped (no stored diagram)` : ''}
                {status.failed ? `, ${status.failed} failed` : ''}.
              </>
            )}
            {status.status === 'failed' && (
              <>Regrade failed: {status.error || 'unknown error'}. You can start it again.</>
            )}
          </span>
        </div>
      )}

      {modalOpen && (
        <div
          role="dialog"
          aria-label="Regrade submissions"
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 300,
          }}
          onClick={() => setModalOpen(false)}
        >
          <div
            className="card"
            style={{ maxWidth: 520, width: '92%' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3>Regrade submissions against the current rubric?</h3>
            <p style={{ fontSize: 13 }}>
              Every stored attempt in the chosen scope is graded again by the AI
              with the rubric as it is now. New results replace the old scores,
              including scores staff adjusted by hand. Assessment totals are
              updated. This cannot be undone.
            </p>
            <label style={{ display: 'block', fontSize: 13, marginBottom: 12 }}>
              Class group
              <select
                className="da-select"
                value={group}
                onChange={(e) => setGroup(e.target.value)}
                style={{ display: 'block', marginTop: 4 }}
              >
                <option value="">All class groups</option>
                {classGroups.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </label>
            {startError && (
              <div className="da-alert alert-error" role="alert" style={{ fontSize: 12 }}>
                <span>{startError}</span>
              </div>
            )}
            <div className="button-row" style={{ justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setModalOpen(false)}>
                Not now
              </button>
              <button className="btn btn-danger" onClick={begin} disabled={starting}>
                {starting ? 'Starting…' : 'Start regrade'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
