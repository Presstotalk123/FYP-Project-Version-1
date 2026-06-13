'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Group, Loader, Alert, Button } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
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
      <ProtectedRoute requiredRole={UserRole.STAFF}>
        <DashboardLayout>
          <Group justify="center" py="xl">
            <Loader size="lg" />
          </Group>
        </DashboardLayout>
      </ProtectedRoute>
    );
  }

  if (error || !lab) {
    return (
      <ProtectedRoute requiredRole={UserRole.STAFF}>
        <DashboardLayout>
          <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error" mb="md">
            {error ?? 'Lab not found.'}
          </Alert>
          <Button variant="default" onClick={() => router.push('/admin/labs')}>
            Back to Labs
          </Button>
        </DashboardLayout>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <LabWizardShell title="Edit Lab" initialLab={lab} />
    </ProtectedRoute>
  );
}
