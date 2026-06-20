"use client";

import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { AuthProvider } from "@/contexts/AuthContext";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!}>
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
    </GoogleOAuthProvider>
  );
}
