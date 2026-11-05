'use client';

import { RaAnswerFormat, RaStepSpecStaff } from '@/types/ra.types';

/**
 * The three question types (backend core/ra/answer_format.py). The professor picks one for
 * the whole question; students never see the type's name or any switch, only the
 * question laid out that way.
 */
export const RA_FORMATS: { value: RaAnswerFormat; label: string; staff: string }[] = [
  {
    value: 'mixed', label: 'Mixed',
    staff: 'One answer box. Students may write steps (R1 := …) or one expression; graded on the final result. The original setup.',
  },
  {
    value: 'final_answer', label: 'Final answer',
    staff: 'One answer box for one expression only, with no steps. Graded only on that expression.',
  },
  {
    value: 'multi_step', label: 'Multi-step',
    staff: 'You list the steps, each with a prompt, a model answer and marks. Students fill in one box per step; a correct final answer earns everything, otherwise each step reached earns its marks.',
  },
];

export const RA_FORMAT_LABEL: Record<RaAnswerFormat, string> = {
  mixed: 'Mixed', final_answer: 'Final answer', multi_step: 'Multi-step',
};

export const MIN_STEPS = 2;
export const MAX_STEPS = 10;

/** Whether an answer is written in steps: some line starts ``Name :=`` (or ``Name ←``). */
export function hasSteps(text: string) {
  return /^\s*[A-Za-z_][\w-]*\s*(:=|←)/m.test(text);
}

export function defaultStepName(index: number) {
  return `R${index + 1}`;
}

/** Two empty steps sharing ``marks`` (the rest going to the final step). */
export function emptySteps(marks: number): RaStepSpecStaff[] {
  const first = Math.floor(Math.max(marks, 1) / 2);
  return [
    { name: defaultStepName(0), prompt: '', marks: first, model_answer: '' },
    { name: null, prompt: '', marks: Math.max(marks, 1) - first, model_answer: '' },
  ];
}

export function stepsTotal(steps: RaStepSpecStaff[] | null | undefined) {
  return (steps ?? []).reduce((sum, s) => sum + (s.marks || 0), 0);
}

/** What students read above the answer box of a Final answer question. */
export function RaFinalAnswerNote() {
  return (
    <div className="alert-info" style={{ fontSize: 13 }}>
      <strong>Write the final answer only:</strong> one expression, without steps (no R1 := …). Use brackets to
      put everything in it, e.g. <code>Π Name (σ School = &apos;SCSE&apos; (CrsSch))</code>.
    </div>
  );
}

/** Shown live when a Final answer question's answer is written in steps. */
export function RaWrongFormatWarning() {
  return (
    <div className="alert-warn" style={{ fontSize: 13 }}>
      <strong>This can&apos;t be submitted:</strong> the question asks for the final answer as one expression, and
      your answer is written in steps (R1 := …). Put the steps into one expression to submit it.
    </div>
  );
}

/** The editor note for a Final answer box (replaces the one about steps). */
export const FINAL_ANSWER_HINT = (
  <>
    Write one expression, e.g. <code>Π Name (σ School = &apos;SCSE&apos; CrsSch)</code>. σ, Π and ρ apply to the
    relation right after them; use brackets for more: <code>Π Name (R ⋈ S)</code>.
    Press <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>Enter</kbd> to run.
  </>
);

/** The model answer a list of steps stands for (backend answer_format.steps_program). */
export function stepsProgram(steps: RaStepSpecStaff[]) {
  return steps.map((s, i) => (i === steps.length - 1 ? s.model_answer.trim()
    : `${s.name?.trim() || defaultStepName(i)} := ${s.model_answer.trim()}`)).join(';\n');
}
