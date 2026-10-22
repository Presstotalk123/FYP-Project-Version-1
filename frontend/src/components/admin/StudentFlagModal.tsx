'use client';

import { useEffect, useState } from 'react';
import { Button, Group, Modal, Stack, Text, Textarea } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import type { QueryClient } from '@tanstack/react-query';
import { assessmentService } from '@/services/assessment.service';
import { AssessmentStudentFlag } from '@/types/assessment.types';

// Mirrors AssessmentStudentFlagIn.max_length on the backend.
export const FLAG_REASON_MAX = 500;

export interface StudentFlagTarget {
  assessmentId: number;
  studentId: number;
  /** Name or email, shown in the dialog title. */
  studentLabel: string;
  /** The current flag, or null when the student is not flagged yet. */
  existing: AssessmentStudentFlag | null;
}

interface StudentFlagModalProps {
  /** Which student the dialog is about. null closes the dialog. */
  target: StudentFlagTarget | null;
  onClose: () => void;
  onSaved: (studentId: number, flag: AssessmentStudentFlag) => void;
  onCleared: (studentId: number) => void;
}

/** Every cached student list that carries this assessment's flags. The dashboard
 *  keeps them for the whole session (staleTime: Infinity, refetchOnMount: false),
 *  so a flag set in one view must refresh them or the other views show the old
 *  state. A list that is on screen refetches in place. A list that is not on
 *  screen is dropped instead: with refetchOnMount off, an invalidated entry would
 *  come back unchanged the next time its view opens. */
export function invalidateAssessmentStudentQueries(queryClient: QueryClient, assessmentId: number) {
  const keys = [
    ['assessmentStudents', assessmentId],
    ['assessmentItemStudents', assessmentId],
  ];
  for (const queryKey of keys) {
    queryClient.removeQueries({ queryKey, type: 'inactive' });
    void queryClient.invalidateQueries({ queryKey, type: 'active' });
  }
}

/** Set, edit or remove the staff flag on one student for one assessment. */
export function StudentFlagModal({ target, onClose, onSaved, onCleared }: StudentFlagModalProps) {
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);

  // A new target brings its own reason; the text from the last student must not
  // leak into the next dialog.
  useEffect(() => {
    setReason(target?.existing?.reason ?? '');
  }, [target]);

  const busy = saving || clearing;
  const editing = !!target?.existing;

  const handleSave = async () => {
    if (!target) return;
    setSaving(true);
    try {
      const flag = await assessmentService.flagStudent(
        target.assessmentId,
        target.studentId,
        reason.trim() || null,
      );
      onSaved(target.studentId, flag);
      onClose();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        color: 'red',
        title: 'Could not save the flag',
        message: e.response?.data?.detail || 'Please try again.',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    if (!target) return;
    setClearing(true);
    try {
      await assessmentService.unflagStudent(target.assessmentId, target.studentId);
      onCleared(target.studentId);
      onClose();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        color: 'red',
        title: 'Could not remove the flag',
        message: e.response?.data?.detail || 'Please try again.',
      });
    } finally {
      setClearing(false);
    }
  };

  return (
    <Modal
      opened={target !== null}
      onClose={() => (busy ? null : onClose())}
      title={
        <Text fw={600}>
          {editing ? 'Edit flag' : 'Flag student'} — <span className="pii">{target?.studentLabel}</span>
        </Text>
      }
      centered
    >
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          The flag marks this student for attention on this assessment. Only staff see it.
        </Text>
        <Textarea
          label="Reason"
          placeholder="Optional. Why does this student need attention?"
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value)}
          maxLength={FLAG_REASON_MAX}
          description={`${reason.length}/${FLAG_REASON_MAX}`}
          autosize
          minRows={3}
          data-autofocus
        />
        {target?.existing && (
          <Text size="xs" c="dimmed">
            Flagged by {target.existing.flagged_by_email ?? 'staff'}
            {target.existing.flagged_at
              ? ` on ${new Date(target.existing.flagged_at).toLocaleString()}`
              : ''}
          </Text>
        )}
        <Group justify="space-between">
          <div>
            {editing && (
              <Button
                variant="light"
                color="red"
                loading={clearing}
                disabled={saving}
                onClick={handleClear}
              >
                Remove flag
              </Button>
            )}
          </div>
          <Group gap="sm">
            <Button variant="default" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button color="orange" loading={saving} disabled={clearing} onClick={handleSave}>
              {editing ? 'Save' : 'Flag student'}
            </Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  );
}
