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

const DIFFICULTY_COLOR: Record<string, string> = {
  easy: 'green', Easy: 'green',
  medium: 'yellow', Medium: 'yellow',
  hard: 'red', Hard: 'red',
};

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

  // Form state
  const [title, setTitle] = useState(initial?.title ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [password, setPassword] = useState(initial?.password ?? '');
  const [clearPassword, setClearPassword] = useState(false);
  // Empty string = no time limit (untimed). Whole minutes otherwise.
  const [timeLimit, setTimeLimit] = useState<number | ''>(initial?.time_limit_minutes ?? '');
  const [selectedItems, setSelectedItems] = useState<SortableItem[]>(() =>
    (initial?.items ?? []).map((i) => ({
      uid: nextUid(),
      item_type: i.item_type,
      item_id: i.item_id,
      item_title: i.item_title,
    }))
  );
  const [saving, setSaving] = useState(false);

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
  // Add / Remove
  // ---------------------------------------------------------------------------

  const isAlreadySelected = useCallback(
    (type: AssessmentItemType, id: number) =>
      selectedItems.some((i) => i.item_type === type && i.item_id === id),
    [selectedItems]
  );

  const addItem = (type: AssessmentItemType, id: number, title: string) => {
    if (isAlreadySelected(type, id)) return;
    setSelectedItems((prev) => [
      ...prev,
      { uid: nextUid(), item_type: type, item_id: id, item_title: title },
    ]);
  };

  const removeItem = (uid: string) => {
    setSelectedItems((prev) => prev.filter((i) => i.uid !== uid));
  };

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

    const items = selectedItems.map((item, idx) => ({
      item_type: item.item_type,
      item_id: item.item_id,
      order_index: idx,
    }));

    setSaving(true);
    try {
      if (mode === 'create') {
        const payload: AssessmentCreate = {
          title: title.trim(),
          description: description.trim() || undefined,
          items,
          password: password.trim() || undefined,
          time_limit_minutes: timeLimit === '' ? null : timeLimit,
        };
        await assessmentService.createAssessment(payload);
        notifications.show({ title: 'Success', message: 'Assessment created', color: 'green' });
      } else {
        const payload: AssessmentUpdate = {
          title: title.trim(),
          description: description.trim() || undefined,
          items,
          password: password.trim() || undefined,
          clear_password: clearPassword,
          time_limit_minutes: timeLimit === '' ? undefined : timeLimit,
          clear_time_limit: timeLimit === '',
        };
        await assessmentService.updateAssessment(initial!.id, payload);
        notifications.show({ title: 'Success', message: 'Assessment saved', color: 'green' });
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
      <Group key={`${type}-${id}`} justify="space-between" wrap="nowrap" py={4}
        style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>
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
          onClick={() => !added && addItem(type, id, title)}
          disabled={added}
          title={added ? 'Already added' : 'Add to assessment'}
        >
          <IconPlus size={14} />
        </ActionIcon>
      </Group>
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
      <Paper withBorder p="md" radius="sm">
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

      {/* Content selector */}
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        {/* Left — pool */}
        <Paper withBorder p="md" radius="sm">
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
        <Paper withBorder p="md" radius="sm">
          <Group justify="space-between" mb="sm">
            <Title order={5}>Selected Items</Title>
            <Badge variant="light">{selectedItems.length} item{selectedItems.length !== 1 ? 's' : ''}</Badge>
          </Group>
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
                <SortableAssessmentItem key={item.uid} item={item} onRemove={removeItem} />
              ))}
            </SortableContext>
          </DndContext>
        </Paper>
      </SimpleGrid>

      {/* Actions */}
      <Group justify="flex-end">
        <Button variant="default" onClick={() => router.push('/admin/assessments')}>
          Cancel
        </Button>
        <Button onClick={handleSave} loading={saving}>
          {mode === 'create' ? 'Create Assessment' : 'Save Changes'}
        </Button>
      </Group>
    </Stack>
  );
}
