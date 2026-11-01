'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { RA_CATEGORY } from '@/components/ra/raProblems';
import { useAuth } from '@/contexts/AuthContext';

/**
 * The old Relational Algebra home. RA questions now live in the shared lists, as a
 * "Relational Algebra" category (components/ra/raProblems.tsx), so this address only
 * forwards: staff to Problems, students to Questions, with that category selected.
 * Kept so bookmarks and the "← All RA questions" links still work.
 */
export default function RaHomePage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <RaRedirect />
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function RaRedirect() {
  const router = useRouter();
  const { isStaff, loading } = useAuth();
  useEffect(() => {
    if (!loading) router.replace(`${isStaff ? '/admin/problems' : '/student'}?category=${RA_CATEGORY}`);
  }, [loading, isStaff, router]);
  return <p style={{ color: 'var(--text-muted)' }}>Opening the relational algebra questions…</p>;
}
