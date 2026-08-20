'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Stack,
  Group,
  TextInput,
  Textarea,
  NumberInput,
  PasswordInput,
  Switch,
  Button,
  Tabs,
  Text,
  Badge,
  ActionIcon,
  Loader,
  Alert,
  ScrollArea,
  Paper,
  Title,
  SimpleGrid,
  Divider,
  Input,
} from '@mantine/core';
import {
  IconAlertCircle,
  IconPlus,
  IconSearch,
} from '@tabler/icons-react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { notifications } from '@mantine/notifications';

import { SortableAssessmentItem, SortableItem } from './SortableAssessmentItem';
import {
  TimingGatewaySection,
  WindowRow,
  isoToSgtInput,
  buildGatewayWindows,
  gatewayHasErrors,
  nextRowKey,
} from './TimingGatewaySection';
import { AssessmentItemType, AssessmentDetail, AssessmentCreate, AssessmentUpdate } from '@/types/assessment.types';
import { Question } from '@/types/question.types';
import { ERDiagramQuestionListItem } from '@/types/er-diagram.types';
import { Lab } from '@/types/lab.types';
import { assessmentService } from '@/services/assessment.service';
import { questionService } from '@/services/question.service';
import { erDiagramService } from '@/services/er-diagram.service';
import { labService } from '@/services/lab.service';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _uidCounter = 0;
const nextUid = () => `item-${++_uidCounter}`;

// Integer percentages summing to 100, remainder given to the earliest items.
// n=1 -> [100], n=3 -> [34, 33, 33], n=4 -> [25, 25, 25, 25]. Mirrors the backend.
const equalWeights = (n: number): number[] => {
  if (n <= 0) return [];
  const base = Math.floor(100 / n);
  const remainder = 100 - base * n;
  return Array.from({ length: n }, (_, i) => (i < remainder ? base + 1 : base));
};

// Return a copy of the items with equal weights applied.
const withEqualWeights = (items: SortableItem[]): SortableItem[] => {
  const weights = equalWeights(items.length);
  return items.map((item, i) => ({ ...item, weight: weights[i] }));
};

const DIFFICULTY_COLOR: Record<string, string> = {
  easy: 'green', Easy: 'green',
  medium: 'yellow', Medium: 'yellow',
  hard: 'red', Hard: 'red',
};

// ---------------------------------------------------------------------------
// Pool row — a single selectable item in the Content Pool with a hover state
// so it reads like the app's interactive list rows.
// ---------------------------------------------------------------------------

interface PoolRowProps {
  title: string;
  badge?: { label: string; color: string };
  added: boolean;
  onAdd: () => void;
}

function PoolRow({ title, badge, added, onAdd }: PoolRowProps) {
  const [hovered, setHovered] = useState(false);
  return (
    <Group
      justify="space-between"
      wrap="nowrap"
      gap="xs"
      px="xs"
      py={6}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderRadius: 'var(--mantine-radius-sm)',
        backgroundColor: hovered ? 'var(--mantine-color-brand-0)' : 'transparent',
        transition: 'background-color 120ms ease',
      }}
    >
      <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
        {badge && (
          <Badge color={badge.color} variant="light" size="xs" style={{ flexShrink: 0 }}>
            {badge.label}
          </Badge>
        )}
        <Text size="sm" lineClamp={1}>{title}</Text>
      </Group>
      <ActionIcon
        size="sm"
        variant="light"
        color={added ? 'gray' : 'green'}
        onClick={() => !added && onAdd()}
        disabled={added}
        title={added ? 'Already added' : 'Add to assessment'}
      >
        <IconPlus size={14} />
      </ActionIcon>
    </Group>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  mode: 'create' | 'edit';
  initial?: AssessmentDetail;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AssessmentForm({ mode, initial }: Props) {
  const router = useRouter();

  // Once published, the question list is frozen: its items point to content clones, and
  // sending an `items` payload would delete/recreate those rows and break the clones.
  // So the content selector is read-only and `items` is omitted from the save payload;
  // title/description/password/timing/gateway stay editable.
  const itemsFrozen = mode === 'edit' && !!initial?.is_published;

  // Form state
  const [title, setTitle] = useState(initial?.title ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [password, setPassword] = useState(initial?.password ?? '');
  const [clearPassword, setClearPassword] = useState(false);
  // Empty string = no time limit (untimed). Whole minutes otherwise.
  const [timeLimit, setTimeLimit] = useState<number | ''>(initial?.time_limit_minutes ?? '');
  const [selectedItems, setSelectedItems] = useState<SortableItem[]>(() => {
    const items: SortableItem[] = (initial?.items ?? []).map((i) => ({
      uid: nextUid(),
      item_type: i.item_type,
      item_id: i.item_id,
      item_title: i.item_title,
      weight: i.weight ?? 0,
      hide_correctness: i.hide_correctness ?? false,
      max_queries: i.max_queries ?? null,
    }));
    // Legacy/unweighted assessments (weights don't total 100) get an equal split so the
    // editor opens in a valid state; staff can then fine-tune.
    const total = items.reduce((sum, i) => sum + (i.weight || 0), 0);
    return total === 100 ? items : withEqualWeights(items);
  });
  const [saving, setSaving] = useState(false);

  // Timing Gateway — buffered locally (like the content pool) and flushed on Save, so it
  // can be configured before the assessment exists (create mode has no id yet).
  const [gatewayEnabled, setGatewayEnabled] = useState(false);
  const [gatewayRows, setGatewayRows] = useState<WindowRow[]>([]);
  const [classGroups, setClassGroups] = useState<string[]>([]);
  const [gatewayLoading, setGatewayLoading] = useState(true);

  // Pool data
  const [sqlQuestions, setSqlQuestions] = useState<Question[]>([]);
  const [erQuestions, setErQuestions] = useState<ERDiagramQuestionListItem[]>([]);
  const [sqlLabs, setSqlLabs] = useState<Lab[]>([]);
  const [graphLabs, setGraphLabs] = useState<Lab[]>([]);
  const [poolLoading, setPoolLoading] = useState(true);
  const [poolError, setPoolError] = useState<string | null>(null);

  // Search
  const [search, setSearch] = useState('');

  // dnd-kit sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  // ---------------------------------------------------------------------------
  // Load pool
  // ---------------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setPoolLoading(true);
        setPoolError(null);
        const [qs, erqs, labs] = await Promise.all([
          questionService.getQuestions(),
          erDiagramService.getQuestions(),
          labService.getLabs(),
        ]);
        if (cancelled) return;
        setSqlQuestions(qs);
        setErQuestions(erqs);
        setSqlLabs(labs.filter((l) => l.lab_type === 'sql'));
        setGraphLabs(labs.filter((l) => l.lab_type === 'graph'));
      } catch {
        if (!cancelled) setPoolError('Failed to load content pool');
      } finally {
        if (!cancelled) setPoolLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  // ---------------------------------------------------------------------------
  // Load timing-gateway config + selectable class groups
  // ---------------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setGatewayLoading(true);
        if (mode === 'edit' && initial?.id != null) {
          const [config, groups] = await Promise.all([
            assessmentService.getGatewayConfig(initial.id),
            assessmentService.getClassGroups(initial.id),
          ]);
          if (cancelled) return;
          setGatewayEnabled(config.gateway_enabled);
          setClassGroups(groups);
          setGatewayRows(
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
        } else {
          // Create mode: no assessment id yet — start empty, list groups id-lessly.
          const groups = await assessmentService.getAllClassGroups();
          if (cancelled) return;
          setClassGroups(groups);
        }
      } catch {
        // Non-fatal: the section still works, staff can type group names manually.
      } finally {
        if (!cancelled) setGatewayLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [mode, initial?.id]);

  // ---------------------------------------------------------------------------
  // Add / Remove
  // ---------------------------------------------------------------------------

  const isAlreadySelected = useCallback(
    (type: AssessmentItemType, id: number) =>
      selectedItems.some((i) => i.item_type === type && i.item_id === id),
    [selectedItems]
  );

  const addItem = (type: AssessmentItemType, id: number, title: string) => {
    if (isAlreadySelected(type, id)) return;
    // Re-distribute equally so the total stays at 100% as items are added; staff can fine-tune.
    setSelectedItems((prev) =>
      withEqualWeights([
        ...prev,
        { uid: nextUid(), item_type: type, item_id: id, item_title: title, weight: 0, hide_correctness: false, max_queries: null },
      ])
    );
  };

  const removeItem = (uid: string) => {
    setSelectedItems((prev) => withEqualWeights(prev.filter((i) => i.uid !== uid)));
  };

  const updateWeight = (uid: string, weight: number) => {
    setSelectedItems((prev) =>
      prev.map((i) => (i.uid === uid ? { ...i, weight } : i))
    );
  };

  const updateHideCorrectness = (uid: string, value: boolean) => {
    setSelectedItems((prev) =>
      prev.map((i) => (i.uid === uid ? { ...i, hide_correctness: value } : i))
    );
  };

  const updateMaxQueries = (uid: string, value: number | null) => {
    setSelectedItems((prev) =>
      prev.map((i) => (i.uid === uid ? { ...i, max_queries: value } : i))
    );
  };

  const distributeEvenly = () => {
    setSelectedItems((prev) => withEqualWeights(prev));
  };

  const totalWeight = selectedItems.reduce((sum, i) => sum + (i.weight || 0), 0);
  const weightValid = selectedItems.length === 0 || totalWeight === 100;

  // ---------------------------------------------------------------------------
  // Drag-and-drop
  // ---------------------------------------------------------------------------

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      setSelectedItems((prev) => {
        const oldIndex = prev.findIndex((i) => i.uid === active.id);
        const newIndex = prev.findIndex((i) => i.uid === over.id);
        return arrayMove(prev, oldIndex, newIndex);
      });
    }
  };

  // ---------------------------------------------------------------------------
  // Save
  // ---------------------------------------------------------------------------

  const handleSave = async () => {
    if (!title.trim()) {
      notifications.show({ title: 'Validation', message: 'Title is required', color: 'orange' });
      return;
    }

    if (!itemsFrozen && selectedItems.length > 0 && totalWeight !== 100) {
      notifications.show({
        title: 'Validation',
        message: `Question weightage must total 100% (currently ${totalWeight}%)`,
        color: 'orange',
      });
      return;
    }

    if (gatewayHasErrors(gatewayEnabled, gatewayRows)) {
      notifications.show({
        title: 'Validation',
        message:
          gatewayRows.length === 0
            ? 'Add at least one class-group window to the Timing Gateway, or turn it off.'
            : 'Fix the highlighted Timing Gateway windows, or turn the gateway off.',
        color: 'orange',
      });
      return;
    }

    const items = selectedItems.map((item, idx) => ({
      item_type: item.item_type,
      item_id: item.item_id,
      order_index: idx,
      weight: item.weight,
      hide_correctness: item.hide_correctness,
      max_queries: item.item_type === 'sql_question' ? item.max_queries : null,
    }));

    setSaving(true);
    try {
      // Persist the assessment first to obtain its id, then flush the buffered gateway
      // config against that id (in edit mode the id already exists).
      let assessmentId: number;
      if (mode === 'create') {
        const payload: AssessmentCreate = {
          title: title.trim(),
          description: description.trim() || undefined,
          items,
          password: password.trim() || undefined,
          time_limit_minutes: timeLimit === '' ? null : timeLimit,
        };
        const created = await assessmentService.createAssessment(payload);
        assessmentId = created.id;
        notifications.show({ title: 'Success', message: 'Assessment created', color: 'green' });
      } else {
        const payload: AssessmentUpdate = {
          title: title.trim(),
          description: description.trim() || undefined,
          // Omit items when frozen so the backend skips _replace_items and leaves the
          // published clones untouched.
          items: itemsFrozen ? undefined : items,
          password: password.trim() || undefined,
          clear_password: clearPassword,
          time_limit_minutes: timeLimit === '' ? undefined : timeLimit,
          clear_time_limit: timeLimit === '',
        };
        await assessmentService.updateAssessment(initial!.id, payload);
        assessmentId = initial!.id;
        notifications.show({ title: 'Success', message: 'Assessment saved', color: 'green' });
      }

      // Flush the Timing Gateway. Skip the extra request only when there is nothing to
      // persist on create (disabled + no windows); always sync on edit so toggling off sticks.
      if (mode === 'edit' || gatewayEnabled || gatewayRows.length > 0) {
        const res = await assessmentService.updateGatewayConfig(assessmentId, {
          gateway_enabled: gatewayEnabled,
          windows: buildGatewayWindows(gatewayRows),
        });
        if (res.warnings.length) {
          notifications.show({
            title: 'Timing gateway',
            message: res.warnings.join(' '),
            color: 'yellow',
          });
        }
      }

      router.push('/admin/assessments');
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } };
      notifications.show({
        title: 'Error',
        message: e.response?.data?.detail || 'Failed to save assessment',
        color: 'red',
      });
    } finally {
      setSaving(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Pool row renderer
  // ---------------------------------------------------------------------------

  const renderPoolRow = (
    type: AssessmentItemType,
    id: number,
    title: string,
    badge?: { label: string; color: string }
  ) => {
    const added = isAlreadySelected(type, id);
    return (
      <PoolRow
        key={`${type}-${id}`}
        title={title}
        badge={badge}
        added={added}
        onAdd={() => addItem(type, id, title)}
      />
    );
  };

  const filtered = <T extends { title: string }>(arr: T[]) =>
    search.trim()
      ? arr.filter((i) => i.title.toLowerCase().includes(search.toLowerCase()))
      : arr;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Stack gap="lg">
      {/* Metadata */}
      <Paper withBorder p="md" radius="md" shadow="xs">
        <Title order={5} mb="sm">Details</Title>
        <Stack gap="sm">
          <TextInput
            label="Title"
            placeholder="Assessment title"
            value={title}
            onChange={(e) => setTitle(e.currentTarget.value)}
            required
          />
          <Textarea
            label="Description"
            placeholder="Optional description"
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
            minRows={3}
          />
          <NumberInput
            label="Time limit (minutes)"
            description="Optional. Leave blank for no time limit. Students are auto-submitted when time runs out; query execution time is credited back."
            placeholder="No time limit"
            value={timeLimit}
            onChange={(v) => setTimeLimit(v === '' || v === null ? '' : Number(v))}
            min={1}
            allowDecimal={false}
            allowNegative={false}
          />
          <PasswordInput
            label="Assessment Password"
            description="Optional. Students must enter this to join. Leave blank for no password."
            placeholder={
              mode === 'edit' && initial?.has_password
                ? '(password is set — enter new value to change)'
                : 'Leave blank for no password'
            }
            value={password}
            onChange={(e) => {
              setPassword(e.currentTarget.value);
              setClearPassword(false);
            }}
            disabled={clearPassword}
          />
          {mode === 'edit' && initial?.has_password && (
            <Switch
              label="Remove existing password"
              checked={clearPassword}
              onChange={(e) => {
                setClearPassword(e.currentTarget.checked);
                if (e.currentTarget.checked) setPassword('');
              }}
            />
          )}
        </Stack>
      </Paper>

      {/* Timing Gateway — per-class-group access windows. Buffered in local state and
          persisted with the main Save, so it can be configured before the assessment exists. */}
      <TimingGatewaySection
        enabled={gatewayEnabled}
        onEnabledChange={setGatewayEnabled}
        rows={gatewayRows}
        onRowsChange={setGatewayRows}
        classGroups={classGroups}
        loading={gatewayLoading}
      />

      {/* Content selector — read-only once published (question list is frozen) */}
      {itemsFrozen ? (
        <Paper withBorder p="md" radius="md" shadow="xs">
          <Title order={5} mb="sm">Questions</Title>
          <Alert icon={<IconAlertCircle size={14} />} color="blue" mb="sm">
            Questions are frozen after publishing and can&apos;t be changed. You can still edit
            the title, description, password, and timing above.
          </Alert>
          <Stack gap="xs">
            {selectedItems.map((item) => (
              <Group key={item.uid} justify="space-between" wrap="nowrap">
                <Text
                  size="sm"
                  style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {item.item_title}
                </Text>
                <Group gap="xs" wrap="nowrap">
                  <Badge variant="light" size="sm">{item.item_type}</Badge>
                  <Badge variant="light" size="sm" color="gray">{item.weight}%</Badge>
                </Group>
              </Group>
            ))}
          </Stack>
        </Paper>
      ) : (
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        {/* Left — pool */}
        <Paper withBorder p="md" radius="md" shadow="xs">
          <Title order={5} mb="sm">Content Pool</Title>

          <Input
            leftSection={<IconSearch size={14} />}
            placeholder="Search…"
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
            mb="sm"
            size="xs"
          />

          {poolLoading && <Group justify="center" py="md"><Loader size="sm" /></Group>}
          {poolError && (
            <Alert icon={<IconAlertCircle size={14} />} color="red" title="Error">
              {poolError}
            </Alert>
          )}

          {!poolLoading && !poolError && (
            <Tabs defaultValue="sql_question">
              <Tabs.List grow>
                <Tabs.Tab value="sql_question">SQL Q ({filtered(sqlQuestions).length})</Tabs.Tab>
                <Tabs.Tab value="er_question">ER Q ({filtered(erQuestions).length})</Tabs.Tab>
                <Tabs.Tab value="sql_lab">SQL Lab ({filtered(sqlLabs).length})</Tabs.Tab>
                <Tabs.Tab value="graph_lab">Graph Lab ({filtered(graphLabs).length})</Tabs.Tab>
              </Tabs.List>

              <Tabs.Panel value="sql_question" pt="xs">
                <ScrollArea h={320}>
                  {filtered(sqlQuestions).length === 0 && (
                    <Text size="sm" c="dimmed" ta="center" py="sm">No SQL questions found</Text>
                  )}
                  {filtered(sqlQuestions).map((q) =>
                    renderPoolRow('sql_question', q.id, q.title, {
                      label: q.difficulty,
                      color: DIFFICULTY_COLOR[q.difficulty] ?? 'gray',
                    })
                  )}
                </ScrollArea>
              </Tabs.Panel>

              <Tabs.Panel value="er_question" pt="xs">
                <ScrollArea h={320}>
                  {filtered(erQuestions).length === 0 && (
                    <Text size="sm" c="dimmed" ta="center" py="sm">No ER questions found</Text>
                  )}
                  {filtered(erQuestions).map((q) =>
                    renderPoolRow('er_question', q.id, q.title, {
                      label: q.difficulty_label,
                      color: DIFFICULTY_COLOR[q.difficulty_label] ?? 'gray',
                    })
                  )}
                </ScrollArea>
              </Tabs.Panel>

              <Tabs.Panel value="sql_lab" pt="xs">
                <ScrollArea h={320}>
                  {filtered(sqlLabs).length === 0 && (
                    <Text size="sm" c="dimmed" ta="center" py="sm">No SQL labs found</Text>
                  )}
                  {filtered(sqlLabs).map((l) =>
                    renderPoolRow('sql_lab', l.id, l.title)
                  )}
                </ScrollArea>
              </Tabs.Panel>

              <Tabs.Panel value="graph_lab" pt="xs">
                <ScrollArea h={320}>
                  {filtered(graphLabs).length === 0 && (
                    <Text size="sm" c="dimmed" ta="center" py="sm">No Graph labs found</Text>
                  )}
                  {filtered(graphLabs).map((l) =>
                    renderPoolRow('graph_lab', l.id, l.title)
                  )}
                </ScrollArea>
              </Tabs.Panel>
            </Tabs>
          )}
        </Paper>

        {/* Right — selected items */}
        <Paper withBorder p="md" radius="md" shadow="xs">
          <Group justify="space-between" mb="sm">
            <Title order={5}>Selected Items</Title>
            <Group gap="xs">
              <Badge variant="light">{selectedItems.length} item{selectedItems.length !== 1 ? 's' : ''}</Badge>
              <Badge variant="light" color={weightValid ? 'green' : 'red'} title="Total weightage">
                {totalWeight}%
              </Badge>
            </Group>
          </Group>
          {selectedItems.length > 0 && (
            <Group justify="space-between" mb="sm">
              <Text size="xs" c={weightValid ? 'dimmed' : 'red'}>
                Weightage must total 100%.
              </Text>
              <Button variant="subtle" size="compact-xs" onClick={distributeEvenly}>
                Distribute evenly
              </Button>
            </Group>
          )}
          <Divider mb="sm" />

          {selectedItems.length === 0 && (
            <Text size="sm" c="dimmed" ta="center" py="xl">
              Add items from the pool on the left. Drag to reorder.
            </Text>
          )}

          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}

          >
            <SortableContext
              items={selectedItems.map((i) => i.uid)}
              strategy={verticalListSortingStrategy}
            >
              {selectedItems.map((item) => (
                <SortableAssessmentItem
                  key={item.uid}
                  item={item}
                  onRemove={removeItem}
                  onWeightChange={updateWeight}
                  onHideCorrectnessChange={updateHideCorrectness}
                  onMaxQueriesChange={updateMaxQueries}
                />
              ))}
            </SortableContext>
          </DndContext>
        </Paper>
      </SimpleGrid>
      )}

      {/* Actions */}
      <Group justify="flex-end">
        <Button variant="default" size="md" onClick={() => router.push('/admin/assessments')}>
          Cancel
        </Button>
        <Button size="md" onClick={handleSave} loading={saving}>
          {mode === 'create' ? 'Create Assessment' : 'Save Changes'}
        </Button>
      </Group>
    </Stack>
  );
}
