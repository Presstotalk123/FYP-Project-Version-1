"use client";

import { useRef, useState } from "react";
import {
  ActionIcon,
  Box,
  Container,
  Group,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import Link from "next/link";
import { IconArrowLeft } from "@tabler/icons-react";
import { ChatPanel } from "@/components/ChatPanel";
import { DrawioBoard } from "@/components/DrawioBoard";
import type { QuestionCardData } from "@/components/QuestionCard";

type WorkspaceProps = {
  question: QuestionCardData;
};

export function ERDiagramWorkspace({ question }: WorkspaceProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [leftPercent, setLeftPercent] = useState(70);
  const [isDragging, setIsDragging] = useState(false);

  const updateWidthFromPointer = (clientX: number) => {
    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = clientX - rect.left;
    const nextPercent = (x / rect.width) * 100;
    const clamped = Math.min(75, Math.max(30, nextPercent));
    setLeftPercent(clamped);
  };

  return (
    <Container fluid px="sm" py="md">
      <Stack gap="md">
        <Group align="baseline" gap="sm">
          <ActionIcon
            component={Link}
            href="/er-diagram"
            variant="subtle"
            size="sm"
            aria-label="Back to ER diagram list"
          >
            <IconArrowLeft size={18} />
          </ActionIcon>
          <Title order={2}>{question.title}</Title>
          <Text c="dimmed" mt={4}>
            Difficulty: {question.difficulty}
          </Text>
        </Group>
        <Box
          ref={containerRef}
          style={{
            display: "flex",
            gap: 0,
            alignItems: "stretch",
            border: "1px solid var(--mantine-color-gray-3)",
            borderRadius: 12,
            overflow: "hidden",
            width: "100%",
          }}
        >
          <Box
            style={{
              flex: `0 0 ${leftPercent}%`,
              minWidth: 320,
              background: "var(--mantine-color-body)",
              padding: 16,
            }}
          >
            <Stack gap="sm">
              <Title order={4}>Problem</Title>
              <Text>{question.description}</Text>
              <DrawioBoard
                onExport={(xml) => {
                  console.log("Diagram XML exported:", xml);
                }}
              />
            </Stack>
          </Box>
          <Box
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              setIsDragging(true);
              updateWidthFromPointer(event.clientX);
            }}
            onPointerMove={(event) => {
              if (!isDragging) return;
              updateWidthFromPointer(event.clientX);
            }}
            onPointerUp={(event) => {
              event.currentTarget.releasePointerCapture(event.pointerId);
              setIsDragging(false);
            }}
            style={{
              width: 14,
              cursor: "col-resize",
              background: "var(--mantine-color-gray-2)",
              position: "relative",
              flex: "0 0 8px",
              userSelect: "none",
              touchAction: "none",
            }}
          >
            <Box
              style={{
                position: "absolute",
                top: "25%",
                bottom: "25%",
                left: "50%",
                width: 3,
                transform: "translateX(-50%)",
                background: "var(--mantine-color-gray-6)",
                borderRadius: 2,
              }}
            />
          </Box>
          <Box
            style={{
              flex: "1 1 0",
              minWidth: 260,
              background: "var(--mantine-color-body)",
              padding: 16,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <ChatPanel />
          </Box>
        </Box>
      </Stack>
    </Container>
  );
}
