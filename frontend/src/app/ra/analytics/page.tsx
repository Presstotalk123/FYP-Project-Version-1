'use client';

import Link from 'next/link';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { RaClassAnalytics } from '@/components/ra/RaClassAnalytics';
import { RaOff } from '@/components/ra/RaOff';
import { useRaStatus } from '@/hooks/use-ra-status';
import { UserRole } from '@/types/user.types';

export default function RaAnalyticsPage() {
  const { enabled, loading } = useRaStatus();
  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        {loading ? null : !enabled ? <RaOff /> : (
          <>
            <div className="button-row" style={{ marginBottom: 12 }}>
              <Link href="/ra" className="btn btn-ghost" style={{ minHeight: 30, fontSize: 13 }}>← All RA questions</Link>
            </div>
            <RaClassAnalytics />
          </>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
