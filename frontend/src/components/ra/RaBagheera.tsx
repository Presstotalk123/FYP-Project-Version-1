'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { DescriptionMarkdown } from '@/components/common/DescriptionMarkdown';
import { raQueryKeys, raService } from '@/services/ra.service';
import { RaBagheeraMessage } from '@/types/ra.types';

function errorText(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

/** Whether Bagheera may help on this question, and the student's conversation. */
export function useRaBagheera(questionId: number) {
  return useQuery({
    queryKey: raQueryKeys.bagheera(questionId),
    queryFn: () => raService.bagheera(questionId),
    staleTime: 30_000,
  });
}

function GuardNote() {
  return (
    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
      Bagheera&apos;s first reply would have given the answer away, so this one replaced it.
    </span>
  );
}

function Message({ m }: { m: RaBagheeraMessage }) {
  const mine = m.role === 'user';
  return (
    <div style={{ display: 'grid', gap: 2, justifyItems: mine ? 'end' : 'start' }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        {mine ? 'You' : m.kind === 'explain' ? 'Bagheera · explaining a Submit' : 'Bagheera'}
      </span>
      <div style={{
        maxWidth: '92%', padding: '8px 12px', borderRadius: 10, fontSize: 13,
        background: mine ? 'var(--surface-muted)' : 'var(--surface)', border: '1px solid var(--border)',
      }}>
        {mine ? <span style={{ whiteSpace: 'pre-wrap' }}>{m.content}</span> : <DescriptionMarkdown content={m.content} fontSize={13} />}
      </div>
      {m.guarded && <GuardNote />}
    </div>
  );
}

/**
 * "Ask Bagheera" on an RA question: the AI tutor gives hints, never the answer, and never
 * grades. It sees the question, the current answer (``current``) and the last Submit.
 */
export function RaBagheeraChat({ questionId, partId, current }: {
  questionId: number;
  partId: number;
  current: () => { answer?: string; step_answers?: string[] };
}) {
  const client = useQueryClient();
  const query = useRaBagheera(questionId);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const messages = query.data?.messages ?? [];

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' });
  }, [messages.length, pending]);

  if (!query.data?.available) return null;

  const send = async () => {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError(null);
    setPending(message);
    setText('');
    try {
      await raService.bagheeraChat(questionId, partId, message, current());
      await client.invalidateQueries({ queryKey: raQueryKeys.bagheera(questionId) });
    } catch (err) {
      setError(errorText(err, 'Bagheera could not be reached. Try again.'));
      setText(message);
    } finally {
      setPending(null);
      setBusy(false);
    }
  };

  return (
    <details className="card" style={{ padding: 12 }} open={messages.length > 0}>
      <summary style={{ cursor: 'pointer', fontWeight: 700, fontSize: 14 }}>Ask Bagheera</summary>
      <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Bagheera gives hints, never the answer, and doesn&apos;t grade: Submit for that. It can see the question, your
          answer as it is now, and your last Submit.
        </span>
        <div style={{ display: 'grid', gap: 10, maxHeight: 360, overflowY: 'auto' }}>
          {messages.map((m) => <Message key={m.id} m={m} />)}
          {pending && (
            <>
              <Message m={{ id: -1, part_id: partId, kind: 'chat', role: 'user', content: pending, attempt_id: null, guarded: false, created_at: null }} />
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Bagheera is thinking…</span>
            </>
          )}
          <div ref={end} />
        </div>
        {error && <div className="alert-error" style={{ fontSize: 13 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <textarea className="da-input" rows={2} style={{ flex: 1, resize: 'vertical', fontSize: 13 }}
            placeholder="Ask Bagheera… (Enter to send, Shift+Enter for a new line)" value={text}
            aria-label="Message to Bagheera" maxLength={2000}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }} />
          <button className="btn btn-brand" style={{ minHeight: 34 }} onClick={() => void send()} disabled={busy || !text.trim()}>
            {busy ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </details>
  );
}

/** After a wrong Submit: one explanation per attempt, in words, of what the grader found. */
export function RaExplainMistake({ questionId, attemptId }: { questionId: number; attemptId: number }) {
  const client = useQueryClient();
  const query = useRaBagheera(questionId);
  const saved = query.data?.messages.find((m) => m.kind === 'explain' && m.attempt_id === attemptId) ?? null;
  const [reply, setReply] = useState<RaBagheeraMessage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = reply ?? saved;

  if (!query.data?.available) return null;

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      setReply(await raService.bagheeraExplain(questionId, attemptId));
      await client.invalidateQueries({ queryKey: raQueryKeys.bagheera(questionId) });
    } catch (err) {
      setError(errorText(err, 'Bagheera could not be reached. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  if (shown) {
    return (
      <div className="alert-info" style={{ display: 'grid', gap: 4, fontSize: 13 }}>
        <strong>Bagheera explains</strong>
        <DescriptionMarkdown content={shown.content} fontSize={13} />
        {shown.guarded && <GuardNote />}
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Ask a follow-up question in “Ask Bagheera”.</span>
      </div>
    );
  }
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <div>
        <button className="btn btn-secondary" style={{ minHeight: 30, fontSize: 13 }} onClick={() => void ask()} disabled={busy}>
          {busy ? 'Bagheera is thinking…' : 'Explain my mistake'}
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 8 }}>
          Bagheera explains what went wrong, without giving the answer (once per Submit).
        </span>
      </div>
      {error && <div className="alert-error" style={{ fontSize: 13 }}>{error}</div>}
    </div>
  );
}

/** Staff: a student's Bagheera conversation, with any reply that was held back. */
export function RaBagheeraTranscript({ messages }: { messages: RaBagheeraMessage[] }) {
  if (messages.length === 0) return <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>No messages with Bagheera.</p>;
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {messages.map((m) => (
        <div key={m.id} style={{ display: 'grid', gap: 4 }}>
          <Message m={m} />
          {m.blocked_content && (
            <details style={{ fontSize: 12, marginLeft: 8 }}>
              <summary style={{ cursor: 'pointer', color: 'var(--error)' }}>Held back by the leak guard (staff only)</summary>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{m.blocked_content}</pre>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}
