"use client";

import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { MsalProvider } from "@azure/msal-react";
import { msalInstance } from "@/config/msalConfig";
import { AuthProvider } from "@/contexts/AuthContext";
import { useEffect, useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [msalReady, setMsalReady] = useState(false);

  useEffect(() => {
    const initMsal = async () => {
      try {
        if (msalInstance.initialize) {
          await msalInstance.initialize();
        }
        await msalInstance.handleRedirectPromise();
      } catch (error) {
        console.error("MSAL initialization failed:", error);
      } finally {
        setMsalReady(true);
      }
    };

    initMsal();
  }, []);

  if (!msalReady) {
    // Render the layout skeleton during initialization to prevent hydration mismatch as much as possible
    // while protecting MsalProvider from receiving an uninitialized instance.
    return (
      <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!}>
        <MantineProvider
          defaultColorScheme="light"
          colorSchemeManager={localStorageColorSchemeManager({
            key: "dbassist-color-scheme",
          })}
        >
          <div style={{ display: 'none' }}>{children}</div>
        </MantineProvider>
      </GoogleOAuthProvider>
    );
  }

  return (
    <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!}>
      <MsalProvider instance={msalInstance}>
        <MantineProvider
          defaultColorScheme="light"
          colorSchemeManager={localStorageColorSchemeManager({
            key: "dbassist-color-scheme",
          })}
        >
          <ModalsProvider>
            <Notifications position="top-right" />
            <AuthProvider>{children}</AuthProvider>
          </ModalsProvider>
        </MantineProvider>
      </MsalProvider>
    </GoogleOAuthProvider>
  );
}

