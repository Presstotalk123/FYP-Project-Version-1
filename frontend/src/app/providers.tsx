"use client";

import { useState } from "react";
import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { MsalProvider } from "@azure/msal-react";
import { PublicClientApplication } from "@azure/msal-browser";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/contexts/AuthContext";
import { msalConfig } from "@/config/msal.config";

// Single MSAL instance for the app. Constructing it here is safe during SSR —
// browser-only work is deferred to initialize()/login calls (invoked client-side).
const msalInstance = new PublicClientApplication(msalConfig);

// Session-lifetime cache: staff-page data is fetched once and reused across
// navigation for the whole session. Nothing auto-refetches — data only refreshes
// on a full page reload, an explicit Refresh button, or after a mutation
// invalidates its query key. This is what cuts repeated calls to the server.
function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: Infinity, // cached data is always "fresh" → revisits don't refetch
        gcTime: Infinity, // keep cache while a page is unmounted (survives navigation)
        refetchOnMount: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        retry: 1,
      },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  // Build the client once per app instance (never on re-render).
  const [queryClient] = useState(makeQueryClient);

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
            <QueryClientProvider client={queryClient}>
              <AuthProvider>{children}</AuthProvider>
            </QueryClientProvider>
          </ModalsProvider>
        </MantineProvider>
      </MsalProvider>
    </GoogleOAuthProvider>
  );
}