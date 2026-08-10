'use client';

import { QuestionDetail } from '@/types/question.types';
import { DescriptionMarkdown } from '@/components/common/DescriptionMarkdown';

interface QuestionPanelProps {
  question: QuestionDetail;
}

// Map difficulty to the shared design-system badge classes (globals.css).
const difficultyBadge: Record<string, string> = {
  easy: 'badge-success',
  medium: 'badge-warn',
  hard: 'badge-danger',
};

export function QuestionPanel({ question }: QuestionPanelProps) {
  return (
    <div style={{ height: '100%', overflow: 'auto' }}>
      <div style={{ padding: 16, display: 'grid', gap: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>{question.title}</h3>
          <span className={`badge ${difficultyBadge[question.difficulty] ?? 'neutral'}`}>
            {question.difficulty.charAt(0).toUpperCase() + question.difficulty.slice(1)}
          </span>
        </div>

        <DescriptionMarkdown content={question.description} fontSize={13} />

        <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />

        <div>
          <p style={{ margin: '0 0 6px', fontSize: 12, fontWeight: 700, color: 'var(--brand-charcoal)' }}>Database Schema</p>
          <pre style={{
            margin: 0, fontSize: 11, lineHeight: 1.6,
            background: '#1e1e1e', color: '#d4d4d4',
            padding: 12, borderRadius: 'var(--radius)',
            overflow: 'auto', maxHeight: 200,
            fontFamily: 'var(--font-geist-mono)',
          }}>
            {question.schema_sql}
          </pre>
        </div>

        <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />

        <div>
          <p style={{ margin: '0 0 6px', fontSize: 12, fontWeight: 700, color: 'var(--brand-charcoal)' }}>Sample Data</p>
          <pre style={{
            margin: 0, fontSize: 11, lineHeight: 1.6,
            background: '#1e1e1e', color: '#d4d4d4',
            padding: 12, borderRadius: 'var(--radius)',
            overflow: 'auto', maxHeight: 200,
            fontFamily: 'var(--font-geist-mono)',
          }}>
            {question.sample_data_sql}
          </pre>
        </div>
      </div>
    </div>
  );
}
