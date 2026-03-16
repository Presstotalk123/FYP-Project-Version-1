'use client';

import { useState } from 'react';
import {
  Stack,
  Title,
  Text,
  Badge,
  Group,
  Divider,
  Code,
  Tabs,
  TextInput,
  Textarea,
  Button,
  Card,
  ActionIcon,
  Loader,
  Alert,
} from '@mantine/core';
import {
  IconPlus,
  IconTrash,
  IconCheck,
  IconAlertCircle,
  IconChecks,
  IconX,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { LabDetail, LabTask, LabTaskCreate, LabTaskProgress, LabQueryHistoryResponse } from '@/types/lab.types';
import { StudentQueryReviewPanel } from './StudentQueryReviewPanel';

interface LabDescriptionPanelProps {
  lab: LabDetail | null;
  sessionId: number | null;
  isStaffMode: boolean;
  tasks: LabTask[];
  isLoadingTasks: boolean;
  taskProgress: Record<number, LabTaskProgress>;
  onCreateTask: (taskData: LabTaskCreate) => Promise<void>;
  onDeleteTask: (taskId: number) => Promise<void>;
  reviewMode?: boolean;
  studentQueries?: LabQueryHistoryResponse[];
  currentQueryIndex?: number;
  executedIndices?: Set<number>;
  onSelectQuery?: (index: number) => void;
  onExecuteNext?: () => void;
  isLoadingStudentHistory?: boolean;
  studentEmail?: string;
}

export function LabDescriptionPanel({
  lab,
  sessionId,
  isStaffMode,
  tasks,
  isLoadingTasks,
  taskProgress,
  onCreateTask,
  onDeleteTask,
  reviewMode = false,
  studentQueries = [],
  currentQueryIndex = 0,
  executedIndices = new Set(),
  onSelectQuery = () => {},
  onExecuteNext = () => {},
  isLoadingStudentHistory = false,
  studentEmail = '',
}: LabDescriptionPanelProps) {
  const [activeTab, setActiveTab] = useState<string>(reviewMode ? 'review' : 'description');

  // Task creation form state
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDescription, setTaskDescription] = useState('');

  if (!lab) {
    return (
      <Stack align="center" justify="center" p="md" style={{ height: '100%' }}>
        <Text c="dimmed">Loading lab...</Text>
      </Stack>
    );
  }

  const handleSubmitTask = async () => {
    if (!taskTitle.trim() || !taskDescription.trim()) {
      notifications.show({
        title: 'Validation Error',
        message: 'Please fill in all fields',
        color: 'yellow',
      });
      return;
    }

    setIsCreatingTask(true);
    try {
      await onCreateTask({
        title: taskTitle,
        description: taskDescription,
        order_index: tasks.length,
      });

      // Reset form
      setTaskTitle('');
      setTaskDescription('');
    } finally {
      setIsCreatingTask(false);
    }
  };

  return (
    <Tabs
      value={activeTab}
      onChange={(value) => setActiveTab(value || 'description')}
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
    >
      <Tabs.List>
        <Tabs.Tab value="description">Description</Tabs.Tab>
        <Tabs.Tab value="tasks">
          Tasks
          {tasks.length > 0 && (
            <Badge size="xs" ml="xs" circle>
              {tasks.length}
            </Badge>
          )}
        </Tabs.Tab>
        {reviewMode && (
          <Tabs.Tab value="review">
            Student Queries
            {studentQueries.length > 0 && (
              <Badge size="xs" ml="xs" circle>
                {studentQueries.length}
              </Badge>
            )}
          </Tabs.Tab>
        )}
      </Tabs.List>

      {/* Description Tab */}
      <Tabs.Panel value="description" style={{ flex: 1, overflow: 'auto' }}>
        <Stack gap="md" p="md">
          <Group justify="space-between" align="flex-start">
            <Title order={3}>{lab.title}</Title>
            {sessionId && <Badge color="green">Active Session</Badge>}
          </Group>

          <Text size="sm" c="dimmed">
            {lab.description}
          </Text>

          <Divider />

          <div>
            <Text size="sm" fw={500} mb="xs">
              Database Schema
            </Text>
            <Code block style={{ fontSize: '12px', maxHeight: '200px', overflow: 'auto' }}>
              {lab.schema_sql}
            </Code>
          </div>

          <Divider />

          <div>
            <Text size="sm" fw={500} mb="xs">
              Sample Data
            </Text>
            <Code block style={{ fontSize: '12px', maxHeight: '200px', overflow: 'auto' }}>
              {lab.sample_data_sql}
            </Code>
          </div>
        </Stack>
      </Tabs.Panel>

      {/* Tasks Tab */}
      <Tabs.Panel value="tasks" style={{ flex: 1, overflow: 'auto' }}>
        <Stack gap="md" p="md">
          {isLoadingTasks ? (
            <Stack align="center" py="xl">
              <Loader size="sm" />
              <Text size="sm" c="dimmed">
                Loading tasks...
              </Text>
            </Stack>
          ) : (
            <>
              {/* Task List */}
              {tasks.length === 0 && !isStaffMode && (
                <Text size="sm" c="dimmed" ta="center" py="xl">
                  No tasks available yet.
                </Text>
              )}

              {tasks.map((task, index) => (
                <Card key={task.id} withBorder padding="sm" radius="md">
                  <Stack gap="xs">
                    <Group justify="space-between">
                      <Group gap="xs">
                        <Text fw={600} size="sm">
                          {index + 1}. {task.title}
                        </Text>

                        {/* Review mode: Show student's task progress */}
                        {reviewMode && (
                          taskProgress[task.id]?.is_completed ? (
                            <Badge color="green" size="xs" leftSection={<IconCheck size={12} />}>
                              Correct
                            </Badge>
                          ) : taskProgress[task.id]?.attempt_count > 0 ? (
                            <Badge color="red" size="xs" leftSection={<IconX size={12} />}>
                              Incorrect ({taskProgress[task.id].attempt_count} attempt{taskProgress[task.id].attempt_count !== 1 ? 's' : ''})
                            </Badge>
                          ) : (
                            <Badge color="yellow" size="xs">
                              Incomplete
                            </Badge>
                          )
                        )}

                        {/* Student mode: Show current student progress */}
                        {!reviewMode && !isStaffMode && taskProgress[task.id] && (
                          taskProgress[task.id].is_completed ? (
                            <Badge color="green" size="xs" leftSection={<IconCheck size={12} />}>
                              Completed
                            </Badge>
                          ) : taskProgress[task.id].attempt_count > 0 ? (
                            <Badge color="yellow" size="xs">
                              {taskProgress[task.id].attempt_count} attempt{taskProgress[task.id].attempt_count !== 1 ? 's' : ''}
                            </Badge>
                          ) : null
                        )}

                        {/* Staff testing mode: Show has_answer status */}
                        {!reviewMode && isStaffMode && (
                          task.has_answer ? (
                            <Badge color="green" size="xs" leftSection={<IconChecks size={12} />}>
                              Has Answer
                            </Badge>
                          ) : (
                            <Badge color="yellow" size="xs" leftSection={<IconAlertCircle size={12} />}>
                              No Answer
                            </Badge>
                          )
                        )}
                      </Group>
                      {isStaffMode && (
                        <ActionIcon
                          color="red"
                          variant="subtle"
                          onClick={() => onDeleteTask(task.id)}
                          size="sm"
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed">
                      {task.description}
                    </Text>
                  </Stack>
                </Card>
              ))}

              {/* Task Creation Form (Staff Only - Not in Review Mode) */}
              {isStaffMode && !reviewMode && (
                <>
                  <Divider label="Create New Task" labelPosition="center" />

                  <Stack gap="sm">
                    <TextInput
                      label="Task Title"
                      placeholder="e.g., Find all students with grade > 80"
                      value={taskTitle}
                      onChange={(e) => setTaskTitle(e.target.value)}
                      required
                    />

                    <Textarea
                      label="Task Description"
                      placeholder="Describe what students need to accomplish..."
                      value={taskDescription}
                      onChange={(e) => setTaskDescription(e.target.value)}
                      minRows={3}
                      required
                    />

                    <Alert color="blue" icon={<IconAlertCircle size={16} />}>
                      After creating the task, execute a query and assign its result as the
                      correct answer from the Results panel.
                    </Alert>

                    <Button
                      leftSection={<IconPlus size={16} />}
                      onClick={handleSubmitTask}
                      loading={isCreatingTask}
                      fullWidth
                    >
                      Create Task
                    </Button>
                  </Stack>
                </>
              )}
            </>
          )}
        </Stack>
      </Tabs.Panel>

      {/* Review Tab - Staff Review Mode */}
      {reviewMode && (
        <Tabs.Panel value="review" style={{ flex: 1, overflow: 'hidden' }}>
          <StudentQueryReviewPanel
            queries={studentQueries}
            currentIndex={currentQueryIndex}
            executedIndices={executedIndices}
            onSelectQuery={onSelectQuery}
            onExecuteNext={onExecuteNext}
            isLoading={isLoadingStudentHistory}
            studentEmail={studentEmail}
          />
        </Tabs.Panel>
      )}
    </Tabs>
  );
}
