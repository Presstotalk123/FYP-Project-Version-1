'use client';

import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { RaOff } from '@/components/ra/RaOff';
import { RaQuestionForm } from '@/components/ra/RaQuestionForm';
import { useRaStatus } from '@/hooks/use-ra-status';
import { raQueryKeys, raService } from '@/services/ra.service';
import { UserRole } from '@/types/user.types';

export default function EditRaQuestionPage() {
  const params = useParams();
  const questionId = parseInt((params?.id as string) || '0');
  const { enabled, loading } = useRaStatus();
  const query = useQuery({
    queryKey: raQueryKeys.questionEdit(questionId),
    queryFn: () => raService.getQuestionForEdit(questionId),
    enabled,
    staleTime: 0,
  });
  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        {loading ? null : !enabled ? <RaOff /> : query.isLoading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
        ) : query.data ? (
          <RaQuestionForm key={query.data.id} initial={query.data} />
        ) : (
          <div className="alert-error">This question does not exist.</div>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
