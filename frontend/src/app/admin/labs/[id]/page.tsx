'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { LabForm } from '@/components/admin/LabForm';
import { UserRole } from '@/types/user.types';
import { LabDetail } from '@/types/lab.types';
import { labService } from '@/services/lab.service';

export default function EditLabPage() {
  const params = useParams();
  const labId = parseInt(params.id as string);

  const [lab, setLab] = useState<LabDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLab();
  }, [labId]);

  const fetchLab = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await labService.getLabById(labId);
      setLab(data);
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Failed to load lab');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ProtectedRoute allowedRoles={[UserRole.STAFF, UserRole.ADMIN]}>
      <DashboardLayout>
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          {loading && (
            <div className="loading-center">
              <div className="spinner" />
              <span>Loading lab…</span>
            </div>
          )}

          {error && (
            <div className="da-alert alert-error" role="alert">
              <strong>Error</strong>
              <span>{error}</span>
            </div>
          )}

          {!loading && !error && lab && (
            <div className="card" style={{ padding: 28 }}>
              <h3 style={{ margin: '0 0 20px', fontSize: 20 }}>Edit Lab</h3>
              <LabForm lab={lab} isEdit={true} />
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
