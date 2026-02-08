"use client";

import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { AuthProvider } from "@/contexts/AuthContext";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider
      defaultColorScheme="light"
      colorSchemeManager={localStorageColorSchemeManager({
        key: "dbassist-color-scheme",
      })}
    >
      <AuthProvider>{children}</AuthProvider>
    </MantineProvider>
  );
}
