'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, UserRole } from '@/types/user.types';
import { authService } from '@/services/auth.service';

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

  useEffect(() => {
    const initAuth = async () => {
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

    initAuth();
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
