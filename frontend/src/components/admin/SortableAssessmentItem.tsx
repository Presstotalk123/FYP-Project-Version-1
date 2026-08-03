'use client';

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Group, Text, Badge, ActionIcon, NumberInput, Switch } from '@mantine/core';
import { IconGripVertical, IconTrash } from '@tabler/icons-react';
import { AssessmentItemType } from '@/types/assessment.types';

const TYPE_COLORS: Record<AssessmentItemType, string> = {
  sql_question: 'blue',
  er_question: 'violet',
  sql_lab: 'teal',
  graph_lab: 'grape',
};

const TYPE_LABELS: Record<AssessmentItemType, string> = {
  sql_question: 'SQL Question',
  er_question: 'ER Question',
  sql_lab: 'SQL Lab',
  graph_lab: 'Graph Lab',
};

export interface SortableItem {
  uid: string;
  item_type: AssessmentItemType;
  item_id: number;
  item_title: string;
  weight: number;
  hide_correctness: boolean;
}

interface Props {
  item: SortableItem;
  onRemove: (uid: string) => void;
  onWeightChange: (uid: string, weight: number) => void;
  onHideCorrectnessChange: (uid: string, value: boolean) => void;
}

export function SortableAssessmentItem({
  item,
  onRemove,
  onWeightChange,
  onHideCorrectnessChange,
}: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.uid });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    background: 'var(--mantine-color-body)',
    border: '1px solid var(--mantine-color-default-border)',
    borderRadius: 'var(--mantine-radius-sm)',
    padding: '8px 12px',
    marginBottom: 6,
    cursor: isDragging ? 'grabbing' : 'default',
  };

  return (
    <div ref={setNodeRef} style={style}>
      <Group gap="xs" wrap="nowrap">
        <ActionIcon
          variant="transparent"
          color="gray"
          size="sm"
          {...attributes}
          {...listeners}
          style={{ cursor: 'grab', touchAction: 'none' }}
        >
          <IconGripVertical size={16} />
        </ActionIcon>
        <Badge color={TYPE_COLORS[item.item_type]} variant="light" size="sm">
          {TYPE_LABELS[item.item_type]}
        </Badge>
        <Text size="sm" style={{ flex: 1 }} lineClamp={1}>
          {item.item_title}
        </Text>
        {item.item_type !== 'er_question' && (
          <Switch
            size="xs"
            checked={item.hide_correctness}
            onChange={(e) => onHideCorrectnessChange(item.uid, e.currentTarget.checked)}
            label="Hide result"
            labelPosition="left"
            styles={{ label: { whiteSpace: 'nowrap' } }}
            aria-label={`Hide correctness for ${item.item_title}`}
            title="Hide correctness feedback from students — they see a neutral 'Submitted' result"
          />
        )}
        <NumberInput
          value={item.weight}
          onChange={(v) =>
            onWeightChange(item.uid, v === '' || v === null ? 0 : Number(v))
          }
          min={0}
          max={100}
          allowDecimal={false}
          allowNegative={false}
          suffix="%"
          size="xs"
          w={72}
          styles={{ input: { textAlign: 'right' } }}
          aria-label={`Weight for ${item.item_title}`}
          title="Weightage (%)"
        />
        <ActionIcon
          color="red"
          variant="light"
          size="sm"
          onClick={() => onRemove(item.uid)}
        >
          <IconTrash size={14} />
        </ActionIcon>
      </Group>
    </div>
  );
}
