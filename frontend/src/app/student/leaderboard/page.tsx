'use client';

import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { LeaderboardView } from '@/components/leaderboard/LeaderboardView';
import { UserRole } from '@/types/user.types';

export default function StudentLeaderboardPage() {
  return (
    <ProtectedRoute allowedRoles={[UserRole.STUDENT]}>
      <DashboardLayout>
        <LeaderboardView showEmail={false} />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
