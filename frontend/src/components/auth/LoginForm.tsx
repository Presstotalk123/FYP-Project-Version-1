'use client';

import { useState } from 'react';
import { GoogleLogin, CredentialResponse } from '@react-oauth/google';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { UserRole } from '@/types/user.types';

export default function LoginForm() {
  const [error, setError] = useState<string | null>(null);
  const { googleLogin } = useAuth();
  const router = useRouter();

  const handleGoogleSuccess = async (credentialResponse: CredentialResponse) => {
    setError(null);
    const token = credentialResponse.credential;
    if (!token) {
      setError('No credential received from Google.');
      return;
    }

    try {
      const user = await googleLogin(token);
      const redirectPath =
        user.role === UserRole.STAFF || user.role === UserRole.ADMIN ? '/admin' : '/student';
      router.push(redirectPath);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(
        axiosErr.response?.data?.detail ??
          'Login failed. Contact your administrator to get access.'
      );
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card">
        {/* Brand mark */}
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <span className="brand-mark" style={{ width: 40, height: 40, borderRadius: 10 }} aria-hidden="true" />
        </div>

        <h2>Database Assist</h2>
        <p className="sub">Sign in with your Google account to continue&nbsp;practising SQL and ER diagrams.</p>

        {error && (
          <div
            className="da-alert alert-error"
            role="alert"
            style={{ marginBottom: 16 }}
          >
            <strong>Error</strong>
            <span>{error}</span>
          </div>
        )}

        {/* Google Login button */}
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 8 }}>
          <GoogleLogin
            onSuccess={handleGoogleSuccess}
            onError={() => setError('Google sign-in failed. Please try again.')}
          />
        </div>
      </div>
    </div>
  );
}
