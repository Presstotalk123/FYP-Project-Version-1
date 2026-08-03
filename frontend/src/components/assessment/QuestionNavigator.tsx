'use client';

import { useRouter, useParams } from 'next/navigation';
import { ActionIcon, Group, Tooltip } from '@mantine/core';
import { useAssessmentProgress } from '@/contexts/AssessmentProgressContext';
import { itemWorkspaceUrl } from '@/utils/assessmentItemUrl';

/**
 * Numbered circular jump-to-question nav for the assessment-taking workspaces.
 * Grey = not attempted, orange = attempted. Renders nothing outside an assessment
 * (AssessmentProgressContext defaults to inAssessment: false there).
 */
export function QuestionNavigator() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const progress = useAssessmentProgress();

  if (!progress.inAssessment || progress.items.length === 0) return null;

  const assessmentId = Number(params?.id) || progress.assessmentId;
  if (!assessmentId) return null;

  return (
    <Group gap={6} wrap="wrap" role="navigation" aria-label="Question navigator">
      {progress.items.map((item, index) => {
        const attempted = progress.attemptedIds.has(item.id);
        const isCurrent = progress.currentItemId === item.id;
        return (
          <Tooltip key={item.id} label={item.item_title} withArrow openDelay={300}>
            <ActionIcon
              radius="xl"
              size="lg"
              variant={attempted ? 'filled' : 'outline'}
              color={attempted ? 'orange' : 'gray'}
              onClick={() => router.push(itemWorkspaceUrl(assessmentId, item))}
              aria-label={`Question ${index + 1}${attempted ? ', attempted' : ', not attempted'}${isCurrent ? ', current' : ''}`}
              style={
                isCurrent
                  ? { boxShadow: '0 0 0 2px var(--mantine-color-blue-6)' }
                  : undefined
              }
            >
              {index + 1}
            </ActionIcon>
          </Tooltip>
        );
      })}
    </Group>
  );
}
