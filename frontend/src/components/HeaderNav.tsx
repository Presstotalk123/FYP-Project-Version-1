"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Anchor, Box, Button, Container, Group, Text } from "@mantine/core";
import { useAuth } from "@/contexts/AuthContext";

const links = [
  { label: "Home", href: "/" },
  { label: "SQL", href: "/sql" },
  { label: "ER Diagram", href: "/er-diagram" },
];

export function HeaderNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isAuthenticated } = useAuth();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <Box
      component="header"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        background: "var(--mantine-color-body)",
        borderBottom: "1px solid var(--mantine-color-gray-3)",
      }}
    >
      <Container size="lg" py="sm">
        <Group justify="space-between">
          <Text fw={600}>Database Assist</Text>
          <Group gap="md">
            {links.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Anchor
                  key={link.href}
                  component={Link}
                  href={link.href}
                  fw={isActive ? 600 : 500}
                  c={isActive ? "blue" : "dimmed"}
                >
                  {link.label}
                </Anchor>
              );
            })}
          </Group>
          <Group gap="sm">
            {isAuthenticated ? (
              <>
                <Text size="sm" c="dimmed">
                  {user?.email}
                </Text>
                <Button size="xs" variant="subtle" color="red" onClick={handleLogout}>
                  Logout
                </Button>
              </>
            ) : (
              <Anchor component={Link} href="/login" fw={500} c="blue">
                Login
              </Anchor>
            )}
          </Group>
        </Group>
      </Container>
    </Box>
  );
}
