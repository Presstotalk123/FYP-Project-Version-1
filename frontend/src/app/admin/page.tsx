'use client';

import { Title, Text, Button } from '@mantine/core';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { UserRole } from '@/types/user.types';

export default function AdminDashboard() {
  const router = useRouter();

  return (
    <ProtectedRoute requiredRole={UserRole.STAFF}>
      <DashboardLayout>
        <Title order={2}>Admin Dashboard</Title>
        <Text mt="sm">Welcome to the administration panel!</Text>
        <Button mt="md" onClick={() => router.push('/admin/questions')}>
          Manage Questions
        </Button>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
