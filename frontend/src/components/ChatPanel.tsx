"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Box,
  Button,
  Group,
  Stack,
  Text,
  Textarea,
} from "@mantine/core";
import { BalooAvatar } from "@/components/workspace/AiTutorAvatar";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  animate?: boolean;
};

/** The ER-diagram tutor's name, shown beside every message he sends. */
export const TUTOR_NAME = "Baloo";

const seedMessages: ChatMessage[] = [
  {
    id: "assistant-1",
    role: "assistant",
    content: `Hi, I am ${TUTOR_NAME}. Share your entities and relationships, and I will review them.`,
    animate: false,
  },
];

export type ChatHistoryMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type ChatPanelProps = {
  /**
   * Send a message and resolve with the final assistant text. If the transport
   * streams, call `onToken` with the accumulated text as it arrives; the panel
   * renders it live (no typewriter). Non-streaming callers can ignore `onToken`.
   */
  onSendMessage?: (
    message: string,
    onToken?: (accumulatedText: string) => void,
  ) => Promise<string>;
  injectedAssistantMessage?: string | null;
  disabled?: boolean;
  onSendingChange?: (value: boolean) => void;
  /** Persisted transcript from previous turns; rendered once, without animation. */
  historyMessages?: ChatHistoryMessage[] | null;
};

const TYPEWRITER_INTERVAL_MS = 12;
const TYPEWRITER_CHARS_PER_TICK = 4;

const normalizeMessage = (value: string): string => value.replace(/\\n/g, "\n");

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
  historyMessages,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(seedMessages);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const lastInjectedMessageRef = useRef<string>("");
  const historyAppliedRef = useRef(false);
  const viewportRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (historyAppliedRef.current) return;
    if (!historyMessages || historyMessages.length === 0) return;
    historyAppliedRef.current = true;
    const restored: ChatMessage[] = historyMessages.map((m) => ({
      id: `history-${m.id}`,
      role: m.role,
      content: m.content,
      animate: false,
    }));
    // The transcript already ends with the tutor's latest reply, and the parent
    // passes that same text as `injectedAssistantMessage` (it also feeds the
    // Problem panel's feedback card). Record it as already shown so the
    // injection effect below does not append a second identical bubble.
    const lastAssistant = [...historyMessages].reverse().find((m) => m.role === "assistant");
    if (lastAssistant) {
      lastInjectedMessageRef.current = normalizeMessage(lastAssistant.content.trim());
    }
    // Greeting first, then the persisted transcript, then anything the user
    // already typed this session (normally nothing — history loads on mount).
    setMessages((prev) => [
      ...seedMessages,
      ...restored,
      ...prev.filter((m) => !seedMessages.some((s) => s.id === m.id)),
    ]);
  }, [historyMessages]);

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
    const assistantId = `assistant-${Date.now()}`;
    let streamed = false;
    try {
      // Live-render streamed tokens into a single assistant bubble (created on
      // the first token). Streamed content is not typewriter-animated — the
      // tokens themselves provide the incremental reveal.
      const handleToken = (accumulatedText: string) => {
        streamed = true;
        const content = normalizeMessage(accumulatedText);
        setMessages((prev) => {
          if (prev.some((m) => m.id === assistantId)) {
            return prev.map((m) => (m.id === assistantId ? { ...m, content } : m));
          }
          return [...prev, { id: assistantId, role: "assistant", content, animate: false }];
        });
      };

      const responseText = await onSendMessage(trimmed, handleToken);
      const finalContent = normalizeMessage(responseText || "No response.");
      setMessages((prev) => {
        // Streamed: finalize the existing bubble. Otherwise append with the
        // typewriter animation, preserving the original non-streaming behavior.
        if (streamed) {
          return prev.map((m) =>
            m.id === assistantId ? { ...m, content: finalContent, animate: false } : m,
          );
        }
        return [
          ...prev,
          { id: assistantId, role: "assistant", content: finalContent, animate: true },
        ];
      });
    } catch (err) {
      const error = err as { message?: string };
      const content = error.message || "Failed to send query.";
      setMessages((prev) => {
        // If a streaming bubble was already shown, replace it with the error.
        if (prev.some((m) => m.id === assistantId)) {
          return prev.map((m) =>
            m.id === assistantId ? { ...m, content, animate: false } : m,
          );
        }
        return [
          ...prev,
          { id: `assistant-error-${Date.now()}`, role: "assistant", content, animate: true },
        ];
      });
    } finally {
      setIsSending(false);
      onSendingChange?.(false);
    }
  };

  return (
    <Stack gap="sm" h="100%" style={{ minHeight: 0 }}>
      <Box
        ref={viewportRef}
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          padding: 16,
          border: "1px solid var(--mantine-color-gray-3)",
          borderRadius: 12,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Stack gap="sm" style={{ marginTop: "auto" }}>
          {messages.map((message) => (
            <Box
              key={message.id}
              style={{
                alignSelf: message.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "85%",
              }}
            >
              {message.role === "assistant" ? (
                <Group gap={6} align="center" mb={4}>
                  <BalooAvatar size={20} />
                  <Text size="xs" fw={600} c="dimmed">
                    {TUTOR_NAME}
                  </Text>
                </Group>
              ) : null}
              <Box
                style={{
                  padding: "10px 12px",
                  borderRadius: 12,
                  background:
                    message.role === "user"
                      // Follows the surrounding theme: blue by default, brand
                      // purple inside the ER-diagram workspace, which scopes it
                      // via DrawioTheme.module.css.
                      ? "var(--mantine-primary-color-filled)"
                      : "var(--mantine-color-gray-1)",
                  color:
                    message.role === "user"
                      ? "var(--mantine-color-white)"
                      : "var(--mantine-color-black)",
                }}
              >
                <TypewriterMessage message={message} onTextUpdate={scrollToLatest} />
              </Box>
            </Box>
          ))}
        </Stack>
      </Box>
      <Group align="stretch" gap="xs">
        <Textarea
          placeholder={`Ask ${TUTOR_NAME} about your ER diagram...`}
          autosize
          minRows={2}
          maxRows={6}
          value={input}
          onChange={(event) => setInput(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.ctrlKey &&
              !event.metaKey &&
              !event.altKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              void handleSend();
            }
          }}
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