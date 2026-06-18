'use client';

import { Box, NavLink, Text } from '@mantine/core';
import { ProblemCounts, ProblemType } from '@/types/problem.types';

interface CategorySidebarProps {
  counts: ProblemCounts;
  selected: ProblemType | 'all';
  onSelect: (value: ProblemType | 'all') => void;
}

export function CategorySidebar({ counts, selected, onSelect }: CategorySidebarProps) {
  const categories: { value: ProblemType | 'all'; label: string; count: number }[] = [
    { value: 'all', label: 'All problems', count: counts.all },
    { value: 'sql', label: 'SQL', count: counts.sql },
    { value: 'erd', label: 'ERD', count: counts.erd },
    { value: 'sqllab', label: 'SQL Lab', count: counts.sqllab },
  ];

  return (
    <Box style={{ width: 200, flexShrink: 0 }}>
      <Text size="xs" tt="uppercase" c="dimmed" fw={600} px="sm" mb={6}>
        Categories
      </Text>
      {categories.map((category) => (
        <NavLink
          key={category.value}
          active={selected === category.value}
          label={category.label}
          rightSection={
            <Text size="xs" c="dimmed">
              {category.count}
            </Text>
          }
          onClick={() => onSelect(category.value)}
        />
      ))}
    </Box>
  );
}
