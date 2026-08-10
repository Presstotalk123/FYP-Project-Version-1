'use client';

import { TypographyStylesProvider } from '@mantine/core';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Renders a description field (SQL question, lab, lab task) written in Markdown.
 *
 * Mirrors CourseMarkdown (react-markdown + remark-gfm, no dangerouslySetInnerHTML,
 * no raw HTML) but tuned for the compact, muted description styling used in the
 * workspace panels. The wrapper caps font size / colour to match the previous
 * plain-<p> look, and lets wide content (fenced ASCII tables, GFM tables) scroll
 * horizontally instead of breaking the panel layout.
 *
 * Authors wrap pre-aligned ASCII tables in a fenced code block (```) so every
 * space and newline is preserved.
 */
export function DescriptionMarkdown({
  content,
  fontSize = 13,
}: {
  content: string;
  fontSize?: number;
}) {
  return (
    <TypographyStylesProvider
      style={{ fontSize, color: 'var(--text-muted)', overflowX: 'auto' }}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </TypographyStylesProvider>
  );
}
