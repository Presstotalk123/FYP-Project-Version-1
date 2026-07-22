'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { LabWizardShell } from '@/components/admin/LabWizardShell';
import { labService } from '@/services/lab.service';
import { UserRole } from '@/types/user.types';
import { LabDetail } from '@/types/lab.types';

export default function EditLabWizardPage() {
  const params = useParams();
  const router = useRouter();
  const labId = parseInt(params.id as string);

  const [lab, setLab] = useState<LabDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    labService
      .getLabById(labId)
      .then(setLab)
      .catch(() => setError('Failed to load lab. It may have been deleted.'))
      .finally(() => setLoading(false));
  }, [labId]);

  if (loading) {
    return (
      <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
        <div className="loading-center" style={{ minHeight: '100vh' }}>
          <div className="spinner" />
          <span>Loading lab…</span>
        </div>
      </ProtectedRoute>
    );
  }

  if (error || !lab) {
    return (
      <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
        <div style={{ maxWidth: 600, margin: '48px auto', padding: '0 28px', display: 'grid', gap: 16 }}>
          <div className="da-alert alert-error" role="alert">
            <strong>Error</strong>
            <span>{error ?? 'Lab not found.'}</span>
          </div>
          <div>
            <button className="btn btn-secondary" onClick={() => router.push('/admin/labs')}>
              Back to Labs
            </button>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <LabWizardShell title="Edit Lab" initialLab={lab} />
    </ProtectedRoute>
  );
}
