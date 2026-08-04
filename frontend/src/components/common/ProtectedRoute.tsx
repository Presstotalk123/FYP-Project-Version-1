'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Center, Loader } from '@mantine/core';
import { useAuth } from '@/contexts/AuthContext';
import { UserRole } from '@/types/user.types';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: UserRole;
  allowedRoles?: UserRole[];
}

function isAdminOrStaff(role: UserRole | undefined) {
  return role === UserRole.STAFF || role === UserRole.ADMIN;
}

export function ProtectedRoute({ children, requiredRole, allowedRoles }: ProtectedRouteProps) {
  const { user, loading, isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      if (!isAuthenticated) {
        router.replace('/login');
      } else {
        const roleAllowed = allowedRoles
          ? allowedRoles.includes(user!.role)
          : requiredRole
          ? user?.role === requiredRole
          : true;

        if (!roleAllowed) {
          const redirectPath = isAdminOrStaff(user?.role) ? '/admin' : '/student/course';
          router.replace(redirectPath);
        }
      }
    }
  }, [loading, isAuthenticated, user, requiredRole, allowedRoles, router]);

  if (loading) {
    return (
      <Center style={{ height: 'calc(100vh - 60px)' }}>
        <Loader size="lg" />
      </Center>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  const roleAllowed = allowedRoles
    ? allowedRoles.includes(user!.role)
    : requiredRole
    ? user?.role === requiredRole
    : true;

  if (!roleAllowed) {
    return null;
  }

  return <>{children}</>;
}
