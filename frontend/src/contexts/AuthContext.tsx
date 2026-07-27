'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { useMsal } from '@azure/msal-react';
import { notifications } from '@mantine/notifications';
import { User, UserRole } from '@/types/user.types';
import { authService } from '@/services/auth.service';
import { getPostLoginRedirect } from '@/utils/auth-redirect';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  googleLogin: (token: string) => Promise<User>;
  logout: () => void;
  isAuthenticated: boolean;
  isStaff: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const { instance } = useMsal();
  const router = useRouter();

  useEffect(() => {
    const init = async () => {
      // Microsoft sign-in uses a full-page redirect (not a popup) — after Microsoft
      // sends the user back, this is where the response is picked up, regardless of
      // which page they land on, since the redirect URI is the site's origin.
      try {
        // MsalProvider also calls initialize() itself, but as a child component
        // this effect can run before that one — initialize() is idempotent and
        // required before handleRedirectPromise() will work reliably.
        await instance.initialize();
        const redirectResult = await instance.handleRedirectPromise();
        if (redirectResult?.idToken) {
          const response = await authService.microsoftLogin(redirectResult.idToken);
          authService.setToken(response.access_token);
          const currentUser = await authService.getCurrentUser();
          setUser(currentUser);
          router.push(getPostLoginRedirect(currentUser.role));
          setLoading(false);
          return;
        }
      } catch (err: unknown) {
        const errorCode = (err as { errorCode?: string }).errorCode;
        // The user declining consent / cancelling on Microsoft's page — not an error.
        if (errorCode !== 'access_denied' && errorCode !== 'user_cancelled') {
          console.error('Microsoft sign-in failed:', err);
          const axiosErr = err as { response?: { data?: { detail?: string } } };
          notifications.show({
            color: 'red',
            title: 'Microsoft sign-in failed',
            message:
              axiosErr.response?.data?.detail ??
              'Contact your administrator to get access.',
          });
        }
      }

      const token = authService.getToken();
      if (token) {
        try {
          const currentUser = await authService.getCurrentUser();
          setUser(currentUser);
        } catch {
          authService.removeToken();
        }
      }
      setLoading(false);
    };

    init();
    // Only ever run once on mount — the redirect response (if any) is only present
    // on the very first load after returning from Microsoft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const googleLogin = async (token: string): Promise<User> => {
    const response = await authService.googleLogin(token);
    authService.setToken(response.access_token);
    const currentUser = await authService.getCurrentUser();
    setUser(currentUser);
    return currentUser;
  };

  const logout = () => {
    authService.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        googleLogin,
        logout,
        isAuthenticated: !!user,
        isStaff: user?.role === UserRole.STAFF || user?.role === UserRole.ADMIN,
        isAdmin: user?.role === UserRole.ADMIN,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
