'use client';

import { useState } from 'react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';
import { OverviewTab } from '@/components/admin/dashboard/OverviewTab';
import { AssessmentAnalyticsTab } from '@/components/admin/dashboard/AssessmentAnalyticsTab';

type DashboardTab = 'overview' | 'assessments';

const TABS: { key: DashboardTab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'assessments', label: 'Assessments' },
];

export default function AdminDashboard() {
  const [tab, setTab] = useState<DashboardTab>('overview');

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div style={{ display: 'flex', gap: '28px', alignItems: 'flex-start', minHeight: '100%' }}>
          {/* Left tab sidebar — same pattern as /admin/problems */}
          <div
            style={{
              width: '180px',
              flexShrink: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              position: 'sticky',
              top: '84px',
              alignSelf: 'flex-start',
            }}
          >
            <span
              style={{
                fontSize: '12px',
                fontWeight: 650,
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
                marginBottom: '4px',
                padding: '0 12px',
                letterSpacing: '0.05em',
              }}
            >
              Dashboard
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {TABS.map((t) => {
                const active = tab === t.key;
                return (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '10px 12px',
                      borderRadius: 'var(--radius)',
                      border: 'none',
                      background: active ? 'var(--surface-brand)' : 'transparent',
                      color: active ? 'var(--brand-lilac)' : 'var(--brand-charcoal)',
                      fontWeight: active ? 750 : 650,
                      fontSize: '14px',
                      width: '100%',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'background 140ms ease, color 140ms ease',
                    }}
                  >
                    <span>{t.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Main content */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {tab === 'overview' ? <OverviewTab /> : <AssessmentAnalyticsTab />}
          </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
