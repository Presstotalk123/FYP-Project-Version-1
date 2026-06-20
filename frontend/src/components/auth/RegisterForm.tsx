'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Center, Loader } from '@mantine/core';

export default function RegisterForm() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/login');
  }, [router]);

  return (
    <Center style={{ minHeight: 'calc(100vh - 60px)' }}>
      <Loader size="lg" />
    </Center>
  );
}
