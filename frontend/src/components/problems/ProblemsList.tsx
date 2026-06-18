'use client';

import { ActionIcon, Badge, Group, Menu, Table, Text } from '@mantine/core';
import {
  IconCircle,
  IconCircleCheck,
  IconDots,
  IconEdit,
  IconSchool,
  IconTrash,
  IconUser,
} from '@tabler/icons-react';
import { ProblemListItem, ProblemType, ProblemDifficulty } from '@/types/problem.types';

export interface ProblemRow extends ProblemListItem {
  completed: boolean;
}

interface ProblemsListProps {
  rows: ProblemRow[];
  isStaff: boolean;
  currentUserId: number | null;
  deletingId: string | null; // `${type}-${id}` of the row being deleted
  onOpen: (row: ProblemRow) => void;
  onEdit: (row: ProblemRow) => void;
  onDelete: (row: ProblemRow) => void;
}

const TYPE_BADGE: Record<ProblemType, { label: string; color: string }> = {
  sql: { label: 'SQL', color: 'blue' },
  erd: { label: 'ERD', color: 'grape' },
  sqllab: { label: 'SQL Lab', color: 'teal' },
};

const DIFFICULTY_COLOR: Record<ProblemDifficulty, string> = {
  easy: 'green',
  medium: 'yellow',
  hard: 'red',
};

function rowKey(row: ProblemListItem): string {
  return `${row.type}-${row.id}`;
}

function canDelete(row: ProblemListItem, isStaff: boolean, currentUserId: number | null): boolean {
  if (row.type === 'sql') return isStaff;
  return isStaff || row.created_by === currentUserId;
}

function canEdit(row: ProblemListItem, isStaff: boolean): boolean {
  // ERD bank questions have no edit page today; only staff edit SQL questions.
  return row.type === 'sql' && isStaff;
}

export function ProblemsList({
  rows,
  isStaff,
  currentUserId,
  deletingId,
  onOpen,
  onEdit,
  onDelete,
}: ProblemsListProps) {
  if (rows.length === 0) {
    return (
      <Text c="dimmed" ta="center" mt="xl">
        No problems match your filters.
      </Text>
    );
  }

  return (
    <Table highlightOnHover withTableBorder verticalSpacing="sm">
      <Table.Thead>
        <Table.Tr>
          <Table.Th style={{ width: 48 }}>#</Table.Th>
          <Table.Th style={{ width: 40 }} />
          <Table.Th>Title</Table.Th>
          <Table.Th style={{ width: 80 }}>Type</Table.Th>
          <Table.Th style={{ width: 110 }}>Difficulty</Table.Th>
          <Table.Th style={{ width: 48 }} />
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {rows.map((row, index) => {
          const showDelete = canDelete(row, isStaff, currentUserId);
          const showEdit = canEdit(row, isStaff);
          const showMenu = showDelete || showEdit;
          return (
            <Table.Tr key={rowKey(row)} style={{ cursor: 'pointer' }} onClick={() => onOpen(row)}>
              <Table.Td>
                <Text c="dimmed" size="sm">
                  {index + 1}
                </Text>
              </Table.Td>
              <Table.Td>
                {row.completed ? (
                  <IconCircleCheck size={18} color="var(--mantine-color-green-6)" />
                ) : (
                  <IconCircle size={18} color="var(--mantine-color-gray-4)" />
                )}
              </Table.Td>
              <Table.Td>
                <Group gap={8} wrap="nowrap">
                  <Text>{row.title}</Text>
                  {row.type === 'erd' && (
                    <Badge
                      variant="light"
                      color={row.created_by_role === 'staff' ? 'teal' : 'gray'}
                      leftSection={
                        row.created_by_role === 'staff' ? (
                          <IconSchool size={12} />
                        ) : (
                          <IconUser size={12} />
                        )
                      }
                    >
                      {row.created_by_role === 'staff' ? 'Staff' : 'Student'}
                    </Badge>
                  )}
                </Group>
              </Table.Td>
              <Table.Td>
                <Badge variant="light" color={TYPE_BADGE[row.type].color}>
                  {TYPE_BADGE[row.type].label}
                </Badge>
              </Table.Td>
              <Table.Td>
                <Badge variant="light" color={DIFFICULTY_COLOR[row.difficulty]}>
                  {row.difficulty.charAt(0).toUpperCase() + row.difficulty.slice(1)}
                </Badge>
              </Table.Td>
              <Table.Td>
                {showMenu && (
                  <Menu position="bottom-end" withinPortal>
                    <Menu.Target>
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        aria-label="Row actions"
                        loading={deletingId === rowKey(row)}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <IconDots size={16} />
                      </ActionIcon>
                    </Menu.Target>
                    <Menu.Dropdown>
                      {showEdit && (
                        <Menu.Item
                          leftSection={<IconEdit size={14} />}
                          onClick={(e) => {
                            e.stopPropagation();
                            onEdit(row);
                          }}
                        >
                          Edit
                        </Menu.Item>
                      )}
                      {showDelete && (
                        <Menu.Item
                          color="red"
                          leftSection={<IconTrash size={14} />}
                          onClick={(e) => {
                            e.stopPropagation();
                            onDelete(row);
                          }}
                        >
                          Delete
                        </Menu.Item>
                      )}
                    </Menu.Dropdown>
                  </Menu>
                )}
              </Table.Td>
            </Table.Tr>
          );
        })}
      </Table.Tbody>
    </Table>
  );
}
