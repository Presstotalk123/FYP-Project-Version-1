'use client';

import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Group,
  Loader,
  SegmentedControl,
  Text,
  Textarea,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconAlertCircle } from '@tabler/icons-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { courseService } from '@/services/course.service';
import { queryKeys } from '@/services/query-keys';
import { getApiErrorMessage } from '@/utils/api-error';
import { CourseMarkdown } from '@/components/course/CourseMarkdown';

/**
 * Staff editor for the student-facing course syllabus (Markdown). Lives in the
 * "Course Info" tab of the Settings page. Saving overwrites the single stored
 * record and invalidates the shared `courseInfo` query so the student page
 * refetches the new content.
 */
export function CourseInfoSettings() {
  const queryClient = useQueryClient();
  const courseQuery = useQuery({
    queryKey: queryKeys.courseInfo,
    queryFn: () => courseService.get(),
  });

  const [value, setValue] = useState('');
  const [view, setView] = useState<'edit' | 'preview'>('edit');
  const [saving, setSaving] = useState(false);

  // Seed the editor once data arrives (and after a save resets the query data).
  const loaded = courseQuery.data?.content;
  useEffect(() => {
    if (loaded !== undefined) setValue(loaded);
  }, [loaded]);

  const dirty = loaded !== undefined && value !== loaded;

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const updated = await courseService.update(value);
      // Update the shared cache so the student page shows the new content, and
      // reset the baseline so `dirty` clears.
      queryClient.setQueryData(queryKeys.courseInfo, updated);
      notifications.show({
        color: 'green',
        title: 'Course info saved',
        message: 'Students will see the updated syllabus.',
      });
    } catch (err) {
      notifications.show({ color: 'red', title: 'Save failed', message: getApiErrorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  if (courseQuery.isLoading) return <Loader />;
  if (courseQuery.error) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="red" title="Failed to load course info">
        {getApiErrorMessage(courseQuery.error)}
      </Alert>
    );
  }

  return (
    <Card withBorder>
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Text fw={700}>Course Info</Text>
          <Text size="xs" c="dimmed">
            Markdown shown on the student Course Info page. Changes go live on save.
          </Text>
        </div>
        <SegmentedControl
          value={view}
          onChange={(v) => setView(v as 'edit' | 'preview')}
          data={[
            { label: 'Edit', value: 'edit' },
            { label: 'Preview', value: 'preview' },
          ]}
        />
      </Group>

      {view === 'edit' ? (
        <Textarea
          value={value}
          onChange={(e) => setValue(e.currentTarget.value)}
          disabled={saving}
          autosize
          minRows={16}
          maxRows={30}
          styles={{ input: { fontFamily: 'ui-monospace, Consolas, monospace', fontSize: 13 } }}
        />
      ) : (
        <Card withBorder bg="var(--mantine-color-gray-0)">
          <CourseMarkdown content={value} />
        </Card>
      )}

      <Text size="xs" c="dimmed" ta="right" mt={4}>
        {value.length.toLocaleString()} characters{dirty ? ' · unsaved changes' : ''}
      </Text>

      <Group mt="sm" gap="xs">
        <Button onClick={handleSave} loading={saving} disabled={!dirty}>
          Save (goes live immediately)
        </Button>
        <Button
          variant="default"
          disabled={!dirty || saving}
          onClick={() => setValue(loaded ?? '')}
        >
          Discard changes
        </Button>
      </Group>
    </Card>
  );
}
