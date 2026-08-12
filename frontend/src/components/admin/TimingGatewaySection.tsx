'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  Paper,
  Title,
  Stack,
  Group,
  Switch,
  Button,
  TextInput,
  Autocomplete,
  ActionIcon,
  Badge,
  Alert,
  Text,
  Loader,
  Divider,
} from '@mantine/core';
import {
  IconPlus,
  IconTrash,
  IconAlertTriangle,
  IconClockHour4,
  IconInfoCircle,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';

import { assessmentService } from '@/services/assessment.service';
import { ClassWindowStatus, ClassWindowIn } from '@/types/assessment.types';

// A "class group" window is scheduled in Singapore local time (the platform's civil
// timezone). <input type="datetime-local"> works in the browser's local zone, so we
// convert explicitly to/from a fixed +08:00 offset to stay correct on any machine.
const SGT_OFFSET_MS = 8 * 3600 * 1000;

/** UTC ISO -> "YYYY-MM-DDTHH:mm" showing the SGT wall-clock for a datetime-local input. */
function isoToSgtInput(iso: string): string {
  const ms = new Date(iso).getTime() + SGT_OFFSET_MS;
  return new Date(ms).toISOString().slice(0, 16);
}

/** datetime-local value (interpreted as SGT wall-clock) -> UTC ISO. */
function sgtInputToIso(value: string): string {
  return new Date(`${value}:00+08:00`).toISOString();
}

interface WindowRow {
  key: string;
  class_group: string;
  startInput: string; // SGT wall-clock for the datetime-local input
  endInput: string;
  is_enabled: boolean;
  status?: ClassWindowStatus;
  active_session_count?: number;
}

const STATUS_COLOR: Record<ClassWindowStatus, string> = {
  upcoming: 'blue',
  active: 'green',
  completed: 'gray',
};

let _rowCounter = 0;
const nextRowKey = () => `win-${++_rowCounter}`;

export function TimingGatewaySection({ assessmentId }: { assessmentId: number }) {
  const [enabled, setEnabled] = useState(false);
  const [rows, setRows] = useState<WindowRow[]>([]);
  const [classGroups, setClassGroups] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [config, groups] = await Promise.all([
        assessmentService.getGatewayConfig(assessmentId),
        assessmentService.getClassGroups(assessmentId),
      ]);
      setEnabled(config.gateway_enabled);
      setClassGroups(groups);
      setRows(
        config.windows.map((w) => ({
          key: nextRowKey(),
          class_group: w.class_group,
          startInput: isoToSgtInput(w.start_at),
          endInput: isoToSgtInput(w.end_at),
          is_enabled: w.is_enabled,
          status: w.status,
          active_session_count: w.active_session_count,
        }))
      );
    } catch {
      setError('Failed to load timing gateway configuration.');
    } finally {
      setLoading(false);
    }
  }, [assessmentId]);

  useEffect(() => {
    load();
  }, [load]);

  const updateRow = (key: string, patch: Partial<WindowRow>) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  };

  const addRow = () => {
    setRows((prev) => [
      ...prev,
      { key: nextRowKey(), class_group: '', startInput: '', endInput: '', is_enabled: true },
    ]);
  };

  const removeRow = (key: string) => {
    setRows((prev) => prev.filter((r) => r.key !== key));
  };

  // Per-row validation errors (only when the gateway is enabled — a disabled gateway
  // ignores its windows, so half-filled rows shouldn't block saving the toggle off).
  const rowError = (r: WindowRow): string | null => {
    if (!enabled) return null;
    if (!r.class_group.trim()) return 'Select a class group.';
    if (!r.startInput) return 'Set a start time.';
    if (!r.endInput) return 'Set an end time.';
    if (r.endInput <= r.startInput) return 'End time must be after start time.';
    return null;
  };

  const duplicateGroups = (() => {
    const seen = new Set<string>();
    const dups = new Set<string>();
    for (const r of rows) {
      const g = r.class_group.trim();
      if (!g) continue;
      if (seen.has(g)) dups.add(g);
      seen.add(g);
    }
    return dups;
  })();

  const hasErrors =
    enabled &&
    (rows.some((r) => rowError(r) !== null) || duplicateGroups.size > 0 || rows.length === 0);

  const handleSave = async () => {
    setError(null);
    if (hasErrors) {
      setError(
        rows.length === 0
          ? 'Add at least one class-group window, or turn the gateway off.'
          : 'Fix the highlighted windows before saving.'
      );
      return;
    }
    setSaving(true);
    try {
      const windows: ClassWindowIn[] = rows
        .filter((r) => r.class_group.trim() && r.startInput && r.endInput)
        .map((r) => ({
          class_group: r.class_group.trim(),
          start_at: sgtInputToIso(r.startInput),
          end_at: sgtInputToIso(r.endInput),
          is_enabled: r.is_enabled,
        }));
      const res = await assessmentService.updateGatewayConfig(assessmentId, {
        gateway_enabled: enabled,
        windows,
      });
      notifications.show({
        title: 'Timing gateway saved',
        message: res.warnings.length
          ? res.warnings.join(' ')
          : 'Access windows updated.',
        color: res.warnings.length ? 'yellow' : 'green',
      });
      // Reload to pick up computed statuses / active-session counts.
      await load();
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || 'Failed to save timing gateway.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Paper withBorder p="md" radius="md" shadow="xs">
      <Group justify="space-between" align="center" mb="xs">
        <Group gap="xs">
          <IconClockHour4 size={18} />
          <Title order={5}>Timing Gateway</Title>
        </Group>
        <Switch
          label="Enable"
          checked={enabled}
          onChange={(e) => setEnabled(e.currentTarget.checked)}
        />
      </Group>

      <Text size="sm" c="dimmed" mb="sm">
        Give each class group its own scheduled access window. When enabled, the schedule
        opens and closes the assessment per group automatically — you no longer press Start/Stop.
        Students are force-submitted at their window end (or their personal timer, whichever is
        earlier). Times are Singapore time (SGT).
      </Text>

      {loading ? (
        <Group justify="center" py="md"><Loader size="sm" /></Group>
      ) : (
        <Stack gap="sm">
          {error && (
            <Alert icon={<IconAlertTriangle size={14} />} color="red">{error}</Alert>
          )}

          {enabled && (
            <Alert icon={<IconInfoCircle size={14} />} color="blue" variant="light">
              While the gateway is enabled, manual Start/Stop is disabled for this assessment.
              A student whose class group has no window here cannot access the assessment.
            </Alert>
          )}

          {rows.length === 0 && (
            <Text size="sm" c="dimmed">No windows configured yet.</Text>
          )}

          {rows.map((r) => {
            const err = rowError(r);
            const isDup = duplicateGroups.has(r.class_group.trim());
            return (
              <Paper key={r.key} withBorder p="sm" radius="sm">
                <Group align="flex-end" wrap="wrap" gap="sm">
                  <Autocomplete
                    label="Class group"
                    placeholder="e.g. SC5001-A"
                    data={classGroups}
                    value={r.class_group}
                    onChange={(v) => updateRow(r.key, { class_group: v })}
                    error={isDup ? 'Duplicate group' : undefined}
                    style={{ minWidth: 160, flex: 1 }}
                  />
                  <TextInput
                    label="Access start (SGT)"
                    type="datetime-local"
                    value={r.startInput}
                    onChange={(e) => updateRow(r.key, { startInput: e.currentTarget.value })}
                  />
                  <TextInput
                    label="Access end (SGT)"
                    type="datetime-local"
                    value={r.endInput}
                    onChange={(e) => updateRow(r.key, { endInput: e.currentTarget.value })}
                    error={err && err.includes('End') ? err : undefined}
                  />
                  <Switch
                    label="Enabled"
                    checked={r.is_enabled}
                    onChange={(e) => updateRow(r.key, { is_enabled: e.currentTarget.checked })}
                    mb={6}
                  />
                  {r.status && (
                    <Badge color={STATUS_COLOR[r.status]} variant="light" mb={6}>
                      {r.status}
                    </Badge>
                  )}
                  <ActionIcon
                    color="red"
                    variant="subtle"
                    onClick={() => removeRow(r.key)}
                    aria-label="Remove window"
                    mb={6}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>

                {err && !err.includes('End') && (
                  <Text size="xs" c="red" mt={4}>{err}</Text>
                )}
                {(r.active_session_count ?? 0) > 0 && (
                  <Text size="xs" c="orange" mt={4}>
                    <IconAlertTriangle size={12} style={{ verticalAlign: 'middle' }} />{' '}
                    {r.active_session_count} student(s) currently mid-attempt in this group —
                    editing this window will change their deadline.
                  </Text>
                )}
              </Paper>
            );
          })}

          <Group justify="space-between">
            <Button
              variant="light"
              leftSection={<IconPlus size={16} />}
              onClick={addRow}
              size="sm"
            >
              Add class-group window
            </Button>
            <Button onClick={handleSave} loading={saving} size="sm">
              Save timing gateway
            </Button>
          </Group>
        </Stack>
      )}
      <Divider mt="md" />
    </Paper>
  );
}
