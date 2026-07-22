'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function RegisterForm() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/login');
  }, [router]);

  return (
    <div className="auth-screen">
      <div className="auth-card" style={{ textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <span className="brand-mark" style={{ width: 40, height: 40, borderRadius: 10 }} aria-hidden="true" />
        </div>
        <h2>Database Assist</h2>
        <p className="sub">Redirecting to login…</p>
        <div className="loading-center" style={{ minHeight: 80 }}>
          <div className="spinner" />
        </div>
      </div>
    </div>
  );
}
