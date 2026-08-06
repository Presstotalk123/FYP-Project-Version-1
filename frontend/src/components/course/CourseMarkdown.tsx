'use client';

import { TypographyStylesProvider } from '@mantine/core';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Renders course-info Markdown as styled HTML. react-markdown outputs React
 * elements (no dangerouslySetInnerHTML), and Mantine's TypographyStylesProvider
 * styles the resulting headings/lists/paragraphs to match the app.
 */
export function CourseMarkdown({ content }: { content: string }) {
  return (
    <TypographyStylesProvider>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </TypographyStylesProvider>
  );
}
