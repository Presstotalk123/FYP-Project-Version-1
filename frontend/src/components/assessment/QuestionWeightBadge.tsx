'use client';

import { Badge, MantineSize } from '@mantine/core';
import { IconPercentage } from '@tabler/icons-react';

interface Props {
  /** Integer percentage this question contributes to the assessment total. */
  weight?: number | null;
  size?: MantineSize;
}

/**
 * Compact badge showing a question's weightage toward the assessment total.
 * Renders nothing for unweighted (0 / null) items so it stays out of the way in
 * practice mode and for legacy assessments.
 */
export function QuestionWeightBadge({ weight, size = 'sm' }: Props) {
  if (!weight) return null;
  return (
    <Badge
      color="indigo"
      variant="light"
      size={size}
      leftSection={<IconPercentage size={12} />}
      title="Weightage toward the assessment total"
    >
      {weight}% weightage
    </Badge>
  );
}
