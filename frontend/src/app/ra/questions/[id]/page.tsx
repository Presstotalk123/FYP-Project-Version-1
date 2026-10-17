'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { RaOff } from '@/components/ra/RaOff';
import { RaQuestionWorkspace } from '@/components/ra/RaQuestionWorkspace';
import { useAuth } from '@/contexts/AuthContext';
import { useRaStatus } from '@/hooks/use-ra-status';

/** Solve one relational-algebra question. Staff see the student view, plus an Edit link. */
export default function RaQuestionPage() {
  const params = useParams();
  const questionId = parseInt((params?.id as string) || '0');
  const { isStaff } = useAuth();
  const { enabled, loading } = useRaStatus();
  return (
    <ProtectedRoute>
      <DashboardLayout>
        {loading ? null : !enabled ? <RaOff /> : (
          <>
            <div className="button-row" style={{ marginBottom: 12 }}>
              <Link href="/ra" className="btn btn-ghost" style={{ minHeight: 30, fontSize: 13 }}>← All RA questions</Link>
              {isStaff && (
                <Link href={`/ra/questions/${questionId}/edit`} className="btn btn-secondary"
                  style={{ minHeight: 30, fontSize: 13, marginLeft: 'auto' }}>
                  Edit question
                </Link>
              )}
            </div>
            <RaQuestionWorkspace questionId={questionId} />
          </>
        )}
      </DashboardLayout>
    </ProtectedRoute>
  );
}
