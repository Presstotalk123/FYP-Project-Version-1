"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Box,
  Button,
  Group,
  ScrollArea,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  animate?: boolean;
};

const seedMessages: ChatMessage[] = [
  {
    id: "assistant-1",
    role: "assistant",
    content: "Hi! Share your entities and relationships, and I will review them.",
    animate: false,
  },
];

type ChatPanelProps = {
  onSendMessage?: (message: string) => Promise<string>;
  injectedAssistantMessage?: string | null;
  disabled?: boolean;
  onSendingChange?: (value: boolean) => void;
};

const TYPEWRITER_INTERVAL_MS = 12;
const TYPEWRITER_CHARS_PER_TICK = 4;

function TypewriterMessage({
  message,
  onTextUpdate,
}: {
  message: ChatMessage;
  onTextUpdate?: () => void;
}) {
  const shouldAnimate = message.role === "assistant" && message.animate !== false;
  const [displayText, setDisplayText] = useState("");

  useEffect(() => {
    if (!shouldAnimate) return;

    let cursor = 0;
    const timer = window.setInterval(() => {
      cursor = Math.min(message.content.length, cursor + TYPEWRITER_CHARS_PER_TICK);
      setDisplayText(message.content.slice(0, cursor));
      onTextUpdate?.();
      if (cursor >= message.content.length) {
        window.clearInterval(timer);
      }
    }, TYPEWRITER_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [message.content, onTextUpdate, shouldAnimate]);

  return (
    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
      {shouldAnimate ? displayText : message.content}
    </Text>
  );
}

export function ChatPanel({
  onSendMessage,
  injectedAssistantMessage,
  disabled = false,
  onSendingChange,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(seedMessages);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const lastInjectedMessageRef = useRef<string>("");
  const viewportRef = useRef<HTMLDivElement | null>(null);

  const normalizeMessage = (value: string): string => value.replace(/\\n/g, "\n");
  const scrollToLatest = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, []);

  // Keep this dependency array shape fixed as [messages].
  // Switching between [messages] and [messages, scrollToLatest] can trigger
  // Fast Refresh hook-signature mismatch warnings in dev.
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [messages]);

  useEffect(() => {
    const trimmed = injectedAssistantMessage?.trim();
    if (!trimmed) return;
    const normalized = normalizeMessage(trimmed);
    if (normalized === lastInjectedMessageRef.current) return;

    lastInjectedMessageRef.current = normalized;
    setMessages((prev) => [
      ...prev,
      {
        id: `assistant-injected-${Date.now()}`,
        role: "assistant",
        content: normalized,
        animate: true,
      },
    ]);
  }, [injectedAssistantMessage]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isSending || disabled) return;
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      animate: false,
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");

    if (!onSendMessage) {
      return;
    }

    setIsSending(true);
    onSendingChange?.(true);
    try {
      const responseText = await onSendMessage(trimmed);
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: normalizeMessage(responseText || "No response."),
          animate: true,
        },
      ]);
    } catch (err) {
      const error = err as { message?: string };
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          content: error.message || "Failed to send query.",
          animate: true,
        },
      ]);
    } finally {
      setIsSending(false);
      onSendingChange?.(false);
    }
  };

  return (
    <Stack gap="sm" h="100%" style={{ minHeight: 0 }}>
      <Title order={4}>AI Chat</Title>
      <Box
        style={{
          flex: 1,
          minHeight: 0,
          maxHeight: "100vh",
          border: "1px solid var(--mantine-color-gray-3)",
          borderRadius: 12,
          overflow: "hidden",
        }}
      >
        <ScrollArea h="100%" p="md" type="always" offsetScrollbars viewportRef={viewportRef}>
          <Stack gap="sm">
            {messages.map((message) => (
              <Box
                key={message.id}
                style={{
                  alignSelf: message.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "85%",
                  padding: "10px 12px",
                  borderRadius: 12,
                  background:
                    message.role === "user"
                      ? "var(--mantine-color-blue-filled)"
                      : "var(--mantine-color-gray-1)",
                  color:
                    message.role === "user"
                      ? "var(--mantine-color-white)"
                      : "var(--mantine-color-black)",
                }}
              >
                <TypewriterMessage message={message} onTextUpdate={scrollToLatest} />
              </Box>
            ))}
          </Stack>
        </ScrollArea>
      </Box>
      <Group align="stretch" gap="xs">
        <Textarea
          placeholder="Ask the AI about your ER diagram..."
          autosize
          minRows={2}
          maxRows={6}
          value={input}
          onChange={(event) => setInput(event.currentTarget.value)}
          style={{ flex: 1 }}
          disabled={isSending || disabled}
        />
        <Button
          onClick={handleSend}
          loading={isSending}
          disabled={disabled}
          style={{ height: "auto", alignSelf: "stretch" }}
        >
          Send
        </Button>
      </Group>
    </Stack>
  );
}