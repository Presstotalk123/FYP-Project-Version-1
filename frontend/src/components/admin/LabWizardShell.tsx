'use client';

import { useState } from 'react';
import {
  Stack,
  Group,
  Title,
  Stepper,
  Loader,
  Paper,
  Button,
  Text,
  Container,
} from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { DashboardLayout } from '@/components/common/DashboardLayout';
import { LabForm } from '@/components/admin/LabForm';
import { LabWorkspace } from '@/components/workspace/LabWorkspace';
import { labService } from '@/services/lab.service';
import { LabDetail } from '@/types/lab.types';

interface LabWizardShellProps {
  initialLab?: LabDetail;
  title?: string;
}

export function LabWizardShell({ initialLab, title }: LabWizardShellProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const [savedLab, setSavedLab] = useState<LabDetail | null>(initialLab ?? null);
  const [transitioning, setTransitioning] = useState(false);

  const isEditFlow = initialLab != null;

  const handleLabSaved = async (labId: number) => {
    setTransitioning(true);
    try {
      const detail = await labService.getLabById(labId);
      setSavedLab(detail);
      setStep(2);
    } catch {
      notifications.show({
        title: 'Error',
        message: 'Lab saved but failed to load details. Please try again.',
        color: 'red',
      });
    } finally {
      setTransitioning(false);
    }
  };

  if (step === 2 && savedLab) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
        <Paper py="xs" px="md" withBorder style={{ borderRadius: 0, flexShrink: 0 }}>
          <Group justify="space-between" align="center">
            <Button
              variant="subtle"
              size="sm"
              leftSection={<IconArrowLeft size={14} />}
              onClick={() => setStep(1)}
            >
              Back to Template
            </Button>
            <Stepper active={1} allowNextStepsSelect={false} size="sm">
              <Stepper.Step label="Lab Template" />
              <Stepper.Step label="Set Up Tasks" />
            </Stepper>
            <Text size="sm" c="dimmed">Step 2 of 2</Text>
          </Group>
        </Paper>
        <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
          <LabWorkspace labId={savedLab.id} isStaffMode={true} />
        </div>
      </div>
    );
  }

  const wizardTitle = title ?? (isEditFlow ? 'Edit Lab' : 'Create New Lab');
  const submitLabel = savedLab
    ? 'Update & Next: Set Up Tasks →'
    : 'Next: Set Up Tasks →';

  return (
    <DashboardLayout>
      <Container size="lg">
        <Stack gap="lg">
          <Title order={2}>{wizardTitle}</Title>
          <Stepper active={0} allowNextStepsSelect={false}>
            <Stepper.Step label="Lab Template" description="Configure structure" />
            <Stepper.Step label="Set Up Tasks" description="Add tasks & answers" />
          </Stepper>
          {transitioning ? (
            <Group justify="center" py="xl">
              <Loader size="lg" />
            </Group>
          ) : (
            <LabForm
              key={savedLab?.id ?? 'new'}
              lab={savedLab ?? undefined}
              isEdit={savedLab != null}
              onSuccess={handleLabSaved}
              submitLabel={submitLabel}
            />
          )}
        </Stack>
      </Container>
    </DashboardLayout>
  );
}
