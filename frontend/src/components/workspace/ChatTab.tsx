'use client';

import { useState, useRef, useEffect } from 'react';
import {
  Stack,
  TextInput,
  Button,
  Text,
  Paper,
  ScrollArea,
  Loader,
  Alert,
  Group,
} from '@mantine/core';
import { IconSend, IconAlertCircle, IconRobot, IconUser } from '@tabler/icons-react';
import { chatbotService, ChatMessage } from '@/services/chatbot.service';
import { QuestionDetail } from '@/types/question.types';
import { ExecuteResponse } from '@/types/attempt.types';

interface ChatTabProps {
  questionId: number;
  question: QuestionDetail;
  currentQuery: string;
  result: ExecuteResponse | null;
}

export function ChatTab({ questionId }: ChatTabProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (viewportRef.current) {
      viewportRef.current.scrollTo({
        top: viewportRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages]);

  // Clear messages when question changes
  useEffect(() => {
    setMessages([]);
    setError(null);
  }, [questionId]);

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue,
      timestamp: new Date().toISOString(),
    };

    // Add user message immediately
    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setError(null);
    setIsLoading(true);

    try {
      const response = await chatbotService.streamQuestionChat(questionId, userMessage.content);

      if (!response.ok) {
        let errorDetail = 'Failed to get response from AI tutor';
        try {
          const errData = await response.json();
          errorDetail = errData.detail || errorDetail;
        } catch {
          // Ignore JSON parse error
        }
        throw new Error(errorDetail);
      }

      if (!response.body) {
        throw new Error('No response body stream available.');
      }

      const aiMsgId = `assistant-${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        {
          id: aiMsgId,
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
        },
      ]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let done = false;
      let aiContent = '';

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          aiContent += decoder.decode(value, { stream: true });
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === aiMsgId ? { ...msg, content: aiContent } : msg
            )
          );
        }
      }
    } catch (err) {
      const e = err as Error;
      setError(e.message || 'Failed to get response from AI tutor');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <Stack gap="md" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Messages Area */}
      <ScrollArea
        style={{ flex: 1 }}
        viewportRef={viewportRef}
      >
        {messages.length === 0 ? (
          <Stack align="center" justify="center" style={{ height: '100%' }} gap="md" p="xl">
            <IconRobot size={48} stroke={1.5} color="var(--mantine-color-gray-5)" />
            <Text c="dimmed" ta="center">
              Ask the AI tutor for help with this SQL question.
              <br />
              I can help explain concepts, debug queries, and guide you toward the solution.
            </Text>
          </Stack>
        ) : (
          <Stack gap="sm" p="md">
            {messages.map((message) => (
              <Paper
                key={message.id}
                p="md"
                withBorder
                style={{
                  alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '80%',
                  backgroundColor:
                    message.role === 'user'
                      ? 'var(--mantine-color-blue-0)'
                      : 'var(--mantine-color-gray-0)',
                }}
              >
                <Group gap="xs" mb="xs">
                  {message.role === 'user' ? (
                    <IconUser size={16} />
                  ) : (
                    <IconRobot size={16} />
                  )}
                  <Text size="sm" fw={500}>
                    {message.role === 'user' ? 'You' : 'AI Tutor'}
                  </Text>
                </Group>
                <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                  {message.content}
                </Text>
                <Text size="xs" c="dimmed" mt="xs">
                  {new Date(message.timestamp).toLocaleTimeString()}
                </Text>
              </Paper>
            ))}
            {isLoading && (
              <Paper p="md" withBorder style={{ alignSelf: 'flex-start', maxWidth: '80%' }}>
                <Group gap="xs">
                  <Loader size="sm" />
                  <Text size="sm" c="dimmed">
                    AI Tutor is thinking...
                  </Text>
                </Group>
              </Paper>
            )}
          </Stack>
        )}
      </ScrollArea>

      {/* Error Alert */}
      {error && (
        <Alert icon={<IconAlertCircle size={16} />} color="red" onClose={() => setError(null)} withCloseButton>
          {error}
        </Alert>
      )}

      {/* Input Area */}
      <Group gap="xs" p="md" style={{ borderTop: '1px solid var(--mantine-color-gray-3)' }}>
        <TextInput
          flex={1}
          placeholder="Ask the AI tutor..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          disabled={isLoading}
        />
        <Button
          onClick={handleSendMessage}
          loading={isLoading}
          disabled={!inputValue.trim()}
          leftSection={<IconSend size={16} />}
        >
          Send
        </Button>
      </Group>
    </Stack>
  );
}
