'use client';

import { useState } from 'react';
import { GoogleLogin, CredentialResponse } from '@react-oauth/google';
import { useMsal } from '@azure/msal-react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { UserRole } from '@/types/user.types';
import { loginRequest } from '@/config/msalConfig';

export default function LoginForm() {
  const [error, setError] = useState<string | null>(null);
  const [msLoading, setMsLoading] = useState(false);
  const { googleLogin, microsoftLogin } = useAuth();
  const { instance } = useMsal();
  const router = useRouter();

  const redirectByRole = (user: { role: UserRole }) => {
    const redirectPath =
      user.role === UserRole.STAFF || user.role === UserRole.ADMIN ? '/admin' : '/student';
    router.push(redirectPath);
  };

  const handleGoogleSuccess = async (credentialResponse: CredentialResponse) => {
    setError(null);
    const token = credentialResponse.credential;
    if (!token) {
      setError('No credential received from Google.');
      return;
    }

    try {
      const user = await googleLogin(token);
      redirectByRole(user);
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
      const result = await instance.loginPopup(loginRequest);
      const idToken = result.idToken;
      if (!idToken) {
        setError('No credential received from Microsoft.');
        setMsLoading(false);
        return;
      }

      const user = await microsoftLogin(idToken);
      redirectByRole(user);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      // MSAL throws BrowserAuthError on user cancel — don't show error for that
      const msalErr = err as { errorCode?: string };
      if (msalErr.errorCode === 'user_cancelled') {
        setMsLoading(false);
        return;
      }
      setError(
        axiosErr.response?.data?.detail ??
          'Microsoft login failed. Contact your administrator to get access.'
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
        <p className="sub">Sign in with your account to continue&nbsp;practising SQL and ER diagrams.</p>

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

        {/* Divider */}
        <div className="auth-divider">
          <span>or</span>
        </div>

        {/* Microsoft Login button */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <button
            id="microsoft-login-btn"
            type="button"
            className="ms-login-btn"
            onClick={handleMicrosoftLogin}
            disabled={msLoading}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="21" height="21" viewBox="0 0 21 21">
              <rect x="1" y="1" width="9" height="9" fill="#f25022" />
              <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
              <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
              <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            <span>{msLoading ? 'Signing in…' : 'Sign in with Microsoft'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

