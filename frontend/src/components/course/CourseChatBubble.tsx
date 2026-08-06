'use client';

import React, { useState, useRef, useEffect } from 'react';
import { chatbotService, ChatMessage } from '@/services/chatbot.service';

interface CourseChatBubbleProps {
  /** Plain-text course syllabus the assistant answers questions from. */
  courseContext: string;
}

/* ── Minimal SVG icons (matches ChatTab style, no Mantine dependency) ── */
const IconUser = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
    <circle cx="12" cy="7" r="4"/>
  </svg>
);

const IconSend = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
);

const IconClose = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="18" y1="6" x2="6" y2="18"/>
    <line x1="6" y1="6" x2="18" y2="18"/>
  </svg>
);

/** Circular wolf mascot avatar for the course assistant. */
function WolfAvatar({ size = 18 }: { size?: number }) {
  return (
    <img
      src="/wolf.png"
      alt="Course assistant"
      width={size}
      height={size}
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        objectFit: 'cover',
        border: '1px solid var(--border)',
        flexShrink: 0,
        display: 'block',
      }}
    />
  );
}

export function CourseChatBubble({ courseContext }: CourseChatBubbleProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, open]);

  const handleSend = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputValue('');
    setError(null);
    setIsLoading(true);

    try {
      const response = await chatbotService.streamCourseChat(courseContext, trimmed);

      if (!response.ok) {
        let errorDetail = 'Failed to get a response from the course assistant';
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
      setError(e.message || 'Failed to get a response from the course assistant');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* ── Launcher bubble ─────────────────────────────────────────────── */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Open course assistant"
          style={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            width: 60,
            height: 60,
            borderRadius: '50%',
            padding: 0,
            border: '2px solid var(--brand-lilac)',
            background: 'var(--brand-white, #fff)',
            cursor: 'pointer',
            boxShadow: '0 6px 20px rgba(132, 88, 179, 0.35)',
            zIndex: 1000,
            overflow: 'hidden',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <img
            src="/wolf.png"
            alt="Course assistant"
            style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' }}
          />
        </button>
      )}

      {/* ── Chat panel ──────────────────────────────────────────────────── */}
      {open && (
        <div
          role="dialog"
          aria-label="Course assistant"
          style={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            width: 360,
            maxWidth: 'calc(100vw - 32px)',
            height: 520,
            maxHeight: 'calc(100vh - 48px)',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 14,
            boxShadow: '0 12px 40px rgba(0, 0, 0, 0.18)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '12px 14px',
            borderBottom: '1px solid var(--border)',
            background: 'var(--brand-lilac)',
            color: '#fff',
            flexShrink: 0,
          }}>
            <WolfAvatar size={30} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.2 }}>Course Assistant</div>
              <div style={{ fontSize: 11, opacity: 0.85 }}>Ask about this course</div>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close course assistant"
              style={{
                background: 'none',
                border: 'none',
                color: '#fff',
                cursor: 'pointer',
                display: 'flex',
                padding: 4,
                borderRadius: 6,
              }}
            >
              <IconClose />
            </button>
          </div>

          {/* Message list */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px 0' }}>
            {messages.length === 0 ? (
              <div style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', height: '100%', gap: 10,
                color: 'var(--text-muted)', textAlign: 'center', padding: '24px 16px',
              }}>
                <WolfAvatar size={56} />
                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, maxWidth: 280 }}>
                  Ask me anything about this course — prerequisites, topics, or what
                  you&apos;ll learn.
                </p>
              </div>
            ) : (
              <div style={{ display: 'grid', gap: 10, paddingBottom: 8 }}>
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    }}
                  >
                    {/* Role label */}
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3,
                      color: 'var(--text-muted)', fontSize: 11,
                    }}>
                      {msg.role === 'user' ? <IconUser /> : <WolfAvatar />}
                      <span>{msg.role === 'user' ? 'You' : 'Assistant'}</span>
                    </div>

                    {/* Bubble */}
                    <div style={{
                      maxWidth: '85%',
                      background: msg.role === 'user' ? '#eff6ff' : 'var(--surface-muted)',
                      border: '1px solid',
                      borderColor: msg.role === 'user' ? '#bfdbfe' : 'var(--border)',
                      borderRadius: msg.role === 'user'
                        ? '12px 12px 2px 12px'
                        : '12px 12px 12px 2px',
                      padding: '8px 12px',
                      fontSize: 13,
                      lineHeight: 1.6,
                      color: 'var(--text)',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}>
                      {msg.content}
                    </div>

                    {/* Timestamp */}
                    <span style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                ))}

                {/* Typing indicator */}
                {isLoading && (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 5,
                      color: 'var(--text-muted)', fontSize: 11, marginBottom: 3,
                    }}>
                      <WolfAvatar />
                      <span>Assistant</span>
                    </div>
                    <div style={{
                      background: 'var(--surface-muted)', border: '1px solid var(--border)',
                      borderRadius: '12px 12px 12px 2px', padding: '8px 14px',
                      display: 'flex', gap: 4, alignItems: 'center',
                    }}>
                      {[0, 1, 2].map((i) => (
                        <span
                          key={i}
                          style={{
                            width: 6, height: 6, borderRadius: '50%',
                            background: 'var(--text-muted)',
                            animation: `wolf-dot-bounce 1.2s infinite ${i * 0.2}s`,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="da-alert alert-error" style={{ margin: '0 12px 8px', fontSize: 12 }}>
              {error}
              <button
                onClick={() => setError(null)}
                style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: 'inherit' }}
                aria-label="Dismiss error"
              >
                ✕
              </button>
            </div>
          )}

          {/* Input bar */}
          <div style={{
            padding: '10px 12px',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            gap: 8,
            alignItems: 'flex-end',
            flexShrink: 0,
          }}>
            <textarea
              style={{
                flex: 1,
                resize: 'none',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '7px 10px',
                fontSize: 13,
                fontFamily: 'inherit',
                lineHeight: 1.5,
                maxHeight: 100,
                minHeight: 36,
                background: 'var(--surface)',
                color: 'var(--text)',
                outline: 'none',
              }}
              placeholder="Ask about this course… (Shift+Enter for new line)"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKey}
              disabled={isLoading}
              rows={1}
              aria-label="Message to course assistant"
            />
            <button
              className="btn btn-brand"
              style={{ minHeight: 36, padding: '0 12px', flexShrink: 0 }}
              onClick={handleSend}
              disabled={!inputValue.trim() || isLoading}
              aria-label="Send message"
            >
              <IconSend />
              Send
            </button>
          </div>

          {/* Dot bounce animation */}
          <style>{`
            @keyframes wolf-dot-bounce {
              0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
              40% { transform: translateY(-5px); opacity: 1; }
            }
          `}</style>
        </div>
      )}
    </>
  );
}
