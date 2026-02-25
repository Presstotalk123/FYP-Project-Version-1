"use client";

import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { AuthProvider } from "@/contexts/AuthContext";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
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
  );
}
