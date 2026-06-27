'use client';

import { Box, NavLink } from '@mantine/core';
import { IconLayoutDashboard, IconCode, IconDatabase, IconUsers, IconListDetails, IconClipboardList } from '@tabler/icons-react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const { isStaff, isAdmin } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  return (
    <Box style={{ display: 'flex', minHeight: 'calc(100vh - 60px)' }}>
      <Box
        style={{
          width: 200,
          borderRight: '1px solid var(--mantine-color-gray-3)',
          padding: '8px 0',
          flexShrink: 0,
        }}
      >
        {isStaff || isAdmin ? (
          <>
            <NavLink
              label="Dashboard"
              leftSection={<IconLayoutDashboard size={16} />}
              active={pathname === '/admin'}
              onClick={() => router.push('/admin')}
            />
            <NavLink
              label="Problems"
              leftSection={<IconListDetails size={16} />}
              active={pathname === '/admin/problems' || pathname.startsWith('/admin/problems/')}
              onClick={() => router.push('/admin/problems')}
            />
            <NavLink
              label="Manage Questions"
              leftSection={<IconCode size={16} />}
              active={pathname === '/admin/questions'}
              onClick={() => router.push('/admin/questions')}
            />
            <NavLink
              label="Manage Labs"
              leftSection={<IconDatabase size={16} />}
              active={pathname === '/admin/labs'}
              onClick={() => router.push('/admin/labs')}
            />
            <NavLink
              label="Assessments"
              leftSection={<IconClipboardList size={16} />}
              active={pathname === '/admin/assessments' || pathname.startsWith('/admin/assessments/')}
              onClick={() => router.push('/admin/assessments')}
            />
            {isAdmin && (
              <NavLink
                label="Manage Users"
                leftSection={<IconUsers size={16} />}
                active={pathname === '/admin/users'}
                onClick={() => router.push('/admin/users')}
              />
            )}
          </>
        ) : (
          <>
            <NavLink
              label="Questions"
              leftSection={<IconCode size={16} />}
              active={pathname === '/student'}
              onClick={() => router.push('/student')}
            />
            <NavLink
              label="Labs"
              leftSection={<IconDatabase size={16} />}
              active={pathname === '/student/labs'}
              onClick={() => router.push('/student/labs')}
            />
            <NavLink
              label="Assessments"
              leftSection={<IconClipboardList size={16} />}
              active={pathname === '/student/assessments' || pathname.startsWith('/student/assessments/')}
              onClick={() => router.push('/student/assessments')}
            />
          </>
        )}
      </Box>

      <Box
        style={{
          flex: 1,
          padding: '24px',
          background: 'var(--mantine-color-body)',
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
