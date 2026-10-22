'use client';

import { AssessmentStudentFlag } from '@/types/assessment.types';

interface StudentFlagButtonProps {
  flag: AssessmentStudentFlag | null | undefined;
  onClick: () => void;
}

/** The hover text: the reason when there is one, so staff can read it without
 *  opening the dialog. */
export function flagTitle(flag: AssessmentStudentFlag | null | undefined): string {
  if (!flag) return 'Flag this student';
  return flag.reason ? `Flagged: ${flag.reason}` : 'Flagged';
}

/** A small flag toggle for the dashboard student lists. Orange when the student
 *  is flagged, grey otherwise. Opens the flag dialog. */
export function StudentFlagButton({ flag, onClick }: StudentFlagButtonProps) {
  const flagged = !!flag;
  const title = flagTitle(flag);
  return (
    <button
      type="button"
      onClick={(e) => {
        // The surrounding table rows expand on click; the flag must not toggle them.
        e.stopPropagation();
        onClick();
      }}
      title={title}
      aria-label={title}
      aria-pressed={flagged}
      style={{
        border: 'none',
        background: 'transparent',
        cursor: 'pointer',
        padding: '0 4px',
        marginRight: 4,
        fontSize: 15,
        lineHeight: 1,
        color: flagged ? '#c2410c' : 'var(--text-muted)',
        opacity: flagged ? 1 : 0.55,
      }}
    >
      {'⚑'}
    </button>
  );
}
