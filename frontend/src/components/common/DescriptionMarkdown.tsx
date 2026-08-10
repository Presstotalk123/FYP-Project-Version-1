'use client';

import { TypographyStylesProvider } from '@mantine/core';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
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
 *
 * remark-breaks is what makes a single newline a line break. Plain Markdown
 * folds one into a space and only starts a new block on a blank line, which
 * silently ran descriptions together — most are typed as prose, not authored
 * as Markdown, and nobody expects the line they pressed Enter on to vanish.
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
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{content}</ReactMarkdown>
    </TypographyStylesProvider>
  );
}
