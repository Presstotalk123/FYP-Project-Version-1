"use client";

import { useState } from "react";
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
};

const seedMessages: ChatMessage[] = [
  {
    id: "assistant-1",
    role: "assistant",
    content: "Hi! Share your entities and relationships, and I will review them.",
  },
];

export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>(seedMessages);
  const [input, setInput] = useState("");

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
  };

  return (
    <Stack gap="sm" h="100%">
      <Title order={4}>AI Chat</Title>
      <Box
        style={{
          flex: 1,
          minHeight: 300,
          border: "1px solid var(--mantine-color-gray-3)",
          borderRadius: 12,
        }}
      >
        <ScrollArea h="100%" p="md">
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
                <Text size="sm">{message.content}</Text>
              </Box>
            ))}
          </Stack>
        </ScrollArea>
      </Box>
      <Group align="flex-end" gap="xs">
        <Textarea
          placeholder="Ask the AI about your ER diagram..."
          autosize
          minRows={2}
          maxRows={6}
          value={input}
          onChange={(event) => setInput(event.currentTarget.value)}
          style={{ flex: 1 }}
        />
        <Button onClick={handleSend}>Send</Button>
      </Group>
    </Stack>
  );
}
