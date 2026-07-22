'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { notifications } from '@mantine/notifications';
import { LabForm } from '@/components/admin/LabForm';
import { LabWorkspace } from '@/components/workspace/LabWorkspace';
import { labService } from '@/services/lab.service';
import { LabDetail } from '@/types/lab.types';

/* ── SVG icons ── */
const IconArrowLeft = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
  </svg>
);

const IconCheck = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);

interface LabWizardShellProps {
  initialLab?: LabDetail;
  title?: string;
  labType?: 'sql' | 'graph';
}

export function LabWizardShell({ initialLab, title, labType: labTypeProp }: LabWizardShellProps) {
  const labType: 'sql' | 'graph' = labTypeProp ?? initialLab?.lab_type ?? 'sql';
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [savedLab, setSavedLab] = useState<LabDetail | null>(initialLab ?? null);
  const [transitioning, setTransitioning] = useState(false);

  const isEditFlow = initialLab != null;

  const handleLabSaved = async (labId: number) => {
    setTransitioning(true);
    try {
      const detail = await labService.getLabById(labId);
      setSavedLab(detail);
      setStep(2);
    } catch {
      notifications.show({
        title: 'Error',
        message: 'Lab saved but failed to load details. Please try again.',
        color: 'red',
      });
    } finally {
      setTransitioning(false);
    }
  };

  /* ── Step 2: Lab workspace (full-screen) ── */
  if (step === 2 && savedLab) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
        {/* Wizard top bar */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 20px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--surface)',
          flexShrink: 0,
        }}>
          {/* Back button */}
          <button
            className="btn btn-secondary"
            style={{ minHeight: 34, padding: '0 12px', fontSize: 13 }}
            onClick={() => setStep(1)}
          >
            <IconArrowLeft />
            Back to Template
          </button>

          {/* Stepper */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Step 1 – completed */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                background: 'var(--success)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12,
              }}>
                <IconCheck />
              </div>
              <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--text-muted)' }}>Lab Template</span>
            </div>

            {/* Connector */}
            <div style={{ width: 40, height: 2, background: 'var(--brand-lilac)', borderRadius: 2 }} />

            {/* Step 2 – active */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                background: 'var(--brand-lilac)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
              }}>
                2
              </div>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-lilac)' }}>Set Up Tasks</span>
            </div>
          </div>

          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Step 2 of 2</span>
        </div>

        {/* Workspace */}
        <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
          <LabWorkspace labId={savedLab.id} isStaffMode={true} />
        </div>
      </div>
    );
  }

  /* ── Step 1: Lab form ── */
  const wizardTitle = title ?? (isEditFlow ? 'Edit Lab' : 'Create New Lab');
  const submitLabel = savedLab
    ? 'Update & Next: Set Up Tasks →'
    : 'Next: Set Up Tasks →';

  return (
    <div style={{ minHeight: '100vh', background: 'var(--surface-workspace)', padding: '2rem 0' }}>
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '0 28px' }}>
        <div style={{ display: 'grid', gap: 24 }}>
          {/* Page heading */}
          <div className="page-head" style={{ marginBottom: 0 }}>
            <div>
              <h2>{wizardTitle}</h2>
              <p>{isEditFlow ? 'Update the lab template settings.' : 'Configure your lab structure and data.'}</p>
            </div>
            <button
              className="btn btn-secondary"
              onClick={() => router.push('/admin/labs')}
            >
              <IconArrowLeft />
              Back to Labs
            </button>
          </div>

          {/* Step indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Step 1 – active */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                background: 'var(--brand-lilac)', color: '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
              }}>
                1
              </div>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-lilac)' }}>Lab Template</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Configure structure</span>
            </div>

            {/* Connector */}
            <div style={{ width: 40, height: 2, background: 'var(--border-strong)', borderRadius: 2 }} />

            {/* Step 2 – pending */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                background: 'var(--border-strong)', color: 'var(--text-muted)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
              }}>
                2
              </div>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 650 }}>Set Up Tasks</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Add tasks & answers</span>
            </div>
          </div>

          {/* Form card */}
          <div className="card" style={{ padding: 28 }}>
            {transitioning ? (
              <div className="loading-center">
                <div className="spinner" />
                <span>Loading workspace…</span>
              </div>
            ) : (
              <LabForm
                key={savedLab?.id ?? 'new'}
                lab={savedLab ?? undefined}
                isEdit={savedLab != null}
                onSuccess={handleLabSaved}
                submitLabel={submitLabel}
                labType={labType}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
