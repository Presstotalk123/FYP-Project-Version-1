'use client';

import { Box, NavLink } from '@mantine/core';
import { IconLayoutDashboard, IconCode } from '@tabler/icons-react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const { isStaff } = useAuth();
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
        {isStaff ? (
          <>
            <NavLink
              label="Dashboard"
              leftSection={<IconLayoutDashboard size={16} />}
              active={pathname === '/admin'}
              onClick={() => router.push('/admin')}
            />
            <NavLink
              label="Manage Questions"
              leftSection={<IconCode size={16} />}
              active={pathname === '/admin/questions'}
              onClick={() => router.push('/admin/questions')}
            />
          </>
        ) : (
          <NavLink
            label="Questions"
            leftSection={<IconLayoutDashboard size={16} />}
            active={pathname === '/student'}
            onClick={() => router.push('/student')}
          />
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
