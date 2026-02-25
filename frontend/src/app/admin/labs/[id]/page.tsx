'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Container, Loader, Alert, Group } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
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
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <Container size="lg">
          {loading && (
            <Group justify="center" py="xl">
              <Loader size="lg" />
            </Group>
          )}

          {error && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
              {error}
            </Alert>
          )}

          {!loading && !error && lab && <LabForm lab={lab} isEdit={true} />}
        </Container>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
