'use client';

import { useState } from 'react';
import { GoogleLogin, CredentialResponse } from '@react-oauth/google';
import { useMsal } from '@azure/msal-react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { msalLoginRequest } from '@/config/msal.config';
import { UserRole } from '@/types/user.types';

function MicrosoftLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 21 21" aria-hidden="true">
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}

export default function LoginForm() {
  const [error, setError] = useState<string | null>(null);
  const [msLoading, setMsLoading] = useState(false);
  const { googleLogin, microsoftLogin } = useAuth();
  const { instance } = useMsal();
  const router = useRouter();

  const redirectForRole = (role: UserRole) =>
    role === UserRole.STAFF || role === UserRole.ADMIN ? '/admin' : '/student';

  const handleGoogleSuccess = async (credentialResponse: CredentialResponse) => {
    setError(null);
    const token = credentialResponse.credential;
    if (!token) {
      setError('No credential received from Google.');
      return;
    }

    try {
      const user = await googleLogin(token);
      router.push(redirectForRole(user.role));
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(
        axiosErr.response?.data?.detail ??
          'Login failed. Contact your administrator to get access.'
      );
    }
  };

  const handleMicrosoftLogin = async () => {
    setError(null);
    setMsLoading(true);
    try {
      // initialize() is required and idempotent in MSAL v3+; guarantees the
      // instance is ready before we open the sign-in popup.
      await instance.initialize();
      const result = await instance.loginPopup(msalLoginRequest);

      const idToken = result.idToken;
      if (!idToken) {
        setError('No credential received from Microsoft.');
        return;
      }

      const user = await microsoftLogin(idToken);
      router.push(redirectForRole(user.role));
    } catch (err: unknown) {
      // User closed / cancelled the popup — not an error worth surfacing.
      const errorCode = (err as { errorCode?: string }).errorCode;
      if (errorCode === 'user_cancelled') {
        return;
      }

      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(
        axiosErr.response?.data?.detail ??
          'Microsoft sign-in failed. Contact your administrator to get access.'
      );
    } finally {
      setMsLoading(false);
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
        <p className="sub">Sign in with your Google or Microsoft account to continue&nbsp;practising SQL and ER diagrams.</p>

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

        {/* Sign-in options */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 8 }}>
          {/* Google Login button */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <GoogleLogin
              onSuccess={handleGoogleSuccess}
              onError={() => setError('Google sign-in failed. Please try again.')}
            />
          </div>

          {/* Divider */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              color: 'var(--text-muted)',
              fontSize: 12,
            }}
          >
            <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            or
            <span style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          </div>

          {/* Microsoft Login button */}
          <button
            type="button"
            className="btn btn-secondary"
            style={{ width: '100%' }}
            onClick={handleMicrosoftLogin}
            disabled={msLoading}
          >
            {msLoading ? (
              <>
                <span
                  className="spinner"
                  style={{ width: 16, height: 16, borderWidth: 2 }}
                  aria-hidden="true"
                />
                Signing in…
              </>
            ) : (
              <>
                <MicrosoftLogo />
                Continue with Microsoft
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
