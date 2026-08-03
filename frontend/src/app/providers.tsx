"use client";

import { useState } from "react";
import {
  createTheme,
  localStorageColorSchemeManager,
  MantineColorsTuple,
  MantineProvider,
} from "@mantine/core";
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

// Brand purple scale built around --brand-lilac (#8458b3) from globals.css.
// #8458b3 sits at index 6 — Mantine's default light primaryShade — so filled
// Buttons, active Tabs, Switches, focus rings and the Loader all render in the
// app's brand purple, matching the native `.btn btn-brand` used elsewhere.
const brand: MantineColorsTuple = [
  "#f6f1fb",
  "#e7dcf4",
  "#ccb4e6",
  "#b08bd8",
  "#9769cc",
  "#875bc4",
  "#8458b3", // --brand-lilac
  "#6f4899",
  "#5b2e89", // dark-purple text token
  "#4a2470",
];

// App-wide Mantine theme: aligns Mantine's primary color, radius and font with
// the design system in globals.css so Mantine-based screens (e.g. the assessment
// editor) look native to the rest of the app.
const theme = createTheme({
  primaryColor: "brand",
  colors: { brand },
  defaultRadius: "md",
  radius: { md: "8px" }, // matches --radius: 8px
  fontFamily: "var(--font-geist-sans)",
  fontFamilyMonospace: "var(--font-geist-mono)",
  headings: { fontFamily: "var(--font-geist-sans)" },
  components: {
    Button: { defaultProps: { fw: 700 } }, // echo the bold weight of `.btn`
  },
});

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
          theme={theme}
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