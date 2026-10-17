'use client';

import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { RaOff } from '@/components/ra/RaOff';
import { RaQuestionForm } from '@/components/ra/RaQuestionForm';
import { useRaStatus } from '@/hooks/use-ra-status';
import { UserRole } from '@/types/user.types';

export default function NewRaQuestionPage() {
  const { enabled, loading } = useRaStatus();
  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        {loading ? null : enabled ? <RaQuestionForm /> : <RaOff />}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
