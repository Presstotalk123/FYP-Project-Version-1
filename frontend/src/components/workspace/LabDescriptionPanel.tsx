'use client';

import { useState } from 'react';
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { notifications } from '@mantine/notifications';
import { LabDetail, LabTask, LabTaskCreate, LabTaskProgress, LabQueryHistoryResponse } from '@/types/lab.types';
import { StudentQueryReviewPanel } from './StudentQueryReviewPanel';
import { DescriptionMarkdown } from '@/components/common/DescriptionMarkdown';
import { MarkdownDescriptionField } from '@/components/common/MarkdownDescriptionField';

/* ── SVG icons ── */
const IconPlus = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
  </svg>
);
const IconTrash = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
    <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
  </svg>
);
const IconPencil = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
  </svg>
);
const IconGripVertical = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="9" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="19" r="1"/>
    <circle cx="15" cy="5" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="19" r="1"/>
  </svg>
);

interface LabDescriptionPanelProps {
  lab: LabDetail | null;
  sessionId: number | null;
  isStaffMode: boolean;
  tasks: LabTask[];
  isLoadingTasks: boolean;
  taskProgress: Record<number, LabTaskProgress>;
  onCreateTask: (taskData: LabTaskCreate) => Promise<void>;
  onDeleteTask: (taskId: number) => Promise<void>;
  onEditTask: (taskId: number, data: { title: string; description: string }) => Promise<void>;
  onReorderTasks: (reorderedTasks: LabTask[]) => void;
  reviewMode?: boolean;
  studentQueries?: LabQueryHistoryResponse[];
  currentQueryIndex?: number;
  executedIndices?: Set<number>;
  onSelectQuery?: (index: number) => void;
  onExecuteNext?: () => void;
  isLoadingStudentHistory?: boolean;
  studentEmail?: string;
}

interface SortableTaskCardProps {
  task: LabTask;
  index: number;
  isStaffMode: boolean;
  reviewMode: boolean;
  taskProgress: Record<number, LabTaskProgress>;
  onDeleteTask: (taskId: number) => Promise<void>;
  onEditTask: (taskId: number, data: { title: string; description: string }) => void;
}

function SortableTaskCard({
  task,
  index,
  isStaffMode,
  reviewMode,
  taskProgress,
  onDeleteTask,
  onEditTask,
}: SortableTaskCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  const progress = taskProgress[task.id];

  const getTaskBadge = () => {
    if (reviewMode) {
      if (progress?.is_completed) return <span className="badge badge-success">✓ Correct</span>;
      if (progress?.attempt_count > 0) return <span className="badge badge-danger">✗ Incorrect ({progress.attempt_count})</span>;
      return <span className="badge badge-warn">Incomplete</span>;
    }
    if (!isStaffMode && progress) {
      if (progress.is_completed) return <span className="badge badge-success">✓ Completed</span>;
      if (progress.attempt_count > 0) return <span className="badge neutral">{progress.attempt_count} attempt{progress.attempt_count !== 1 ? 's' : ''}</span>;
    }
    if (isStaffMode && !reviewMode) {
      if (task.has_answer) return <span className="badge badge-success">Has Answer</span>;
      return <span className="badge badge-warn">No Answer</span>;
    }
    return null;
  };

  return (
    <div ref={setNodeRef} style={style}>
      <div className="card" style={{ padding: '10px 12px', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, flex: 1, minWidth: 0 }}>
            {isStaffMode && !reviewMode && (
              <button
                {...attributes}
                {...listeners}
                style={{
                  background: 'none', border: 'none', cursor: isDragging ? 'grabbing' : 'grab',
                  color: 'var(--text-muted)', padding: '2px', flexShrink: 0, marginTop: 2,
                }}
                aria-label="Drag to reorder"
              >
                <IconGripVertical />
              </button>
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--text)' }}>
                  {index + 1}. {task.title}
                </span>
                {getTaskBadge()}
              </div>
              <DescriptionMarkdown content={task.description} fontSize={12} />
            </div>
          </div>
          {isStaffMode && !reviewMode && (
            <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
              <button
                className="icon-btn"
                style={{ color: 'var(--info)' }}
                onClick={() => onEditTask(task.id, { title: task.title, description: task.description })}
                title="Edit task"
              >
                <IconPencil />
              </button>
              <button
                className="icon-btn"
                style={{ color: 'var(--error)' }}
                onClick={() => onDeleteTask(task.id)}
                title="Delete task"
              >
                <IconTrash />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
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
  onEditTask,
  onReorderTasks,
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
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDescription, setTaskDescription] = useState('');

  // Edit modal state
  const [editingTask, setEditingTask] = useState<LabTask | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  const handleOpenEdit = (taskId: number, data: { title: string; description: string }) => {
    const task = tasks.find(t => t.id === taskId)!;
    setEditingTask(task);
    setEditTitle(data.title);
    setEditDescription(data.description);
  };

  const handleSaveEdit = async () => {
    if (!editingTask || !editTitle.trim() || !editDescription.trim()) return;
    setIsSavingEdit(true);
    try {
      await onEditTask(editingTask.id, { title: editTitle, description: editDescription });
      setEditingTask(null);
    } finally {
      setIsSavingEdit(false);
    }
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = tasks.findIndex(t => t.id === active.id);
    const newIndex = tasks.findIndex(t => t.id === over.id);
    onReorderTasks(arrayMove(tasks, oldIndex, newIndex));
  };

  const handleSubmitTask = async () => {
    if (!taskTitle.trim() || !taskDescription.trim()) {
      notifications.show({ title: 'Validation Error', message: 'Please fill in all fields', color: 'yellow' });
      return;
    }
    setIsCreatingTask(true);
    try {
      await onCreateTask({ title: taskTitle, description: taskDescription, order_index: tasks.length });
      setTaskTitle('');
      setTaskDescription('');
    } finally {
      setIsCreatingTask(false);
    }
  };

  if (!lab) {
    return (
      <div className="loading-center" style={{ height: '100%' }}>
        <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>Loading lab…</span>
      </div>
    );
  }

  const tabs = [
    { id: 'description', label: 'Description' },
    { id: 'tasks', label: `Tasks${tasks.length > 0 ? ` (${tasks.length})` : ''}` },
    ...(reviewMode ? [{ id: 'review', label: `Student Queries${studentQueries.length > 0 ? ` (${studentQueries.length})` : ''}` }] : []),
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Tab bar */}
      <div className="tabs" style={{ margin: 0, padding: '0 12px', flexShrink: 0 }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {/* Description Tab */}
        {activeTab === 'description' && (
          <div style={{ padding: 16, display: 'grid', gap: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>{lab.title}</h3>
              {sessionId && <span className="badge badge-success">Active Session</span>}
            </div>

            <DescriptionMarkdown content={lab.description} fontSize={13} />

            <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />

            <div>
              <p style={{ margin: '0 0 6px', fontSize: 12, fontWeight: 700, color: 'var(--brand-charcoal)' }}>Database Schema</p>
              <pre style={{
                margin: 0, fontSize: 11, lineHeight: 1.6,
                background: '#1e1e1e', color: '#d4d4d4',
                padding: 12, borderRadius: 'var(--radius)',
                overflow: 'auto', maxHeight: 200,
                fontFamily: 'var(--font-geist-mono)',
              }}>
                {lab.schema_sql}
              </pre>
            </div>

            <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: 0 }} />

            <div>
              <p style={{ margin: '0 0 6px', fontSize: 12, fontWeight: 700, color: 'var(--brand-charcoal)' }}>Sample Data</p>
              <pre style={{
                margin: 0, fontSize: 11, lineHeight: 1.6,
                background: '#1e1e1e', color: '#d4d4d4',
                padding: 12, borderRadius: 'var(--radius)',
                overflow: 'auto', maxHeight: 200,
                fontFamily: 'var(--font-geist-mono)',
              }}>
                {lab.sample_data_sql}
              </pre>
            </div>
          </div>
        )}

        {/* Tasks Tab */}
        {activeTab === 'tasks' && (
          <div style={{ padding: 12, display: 'grid', gap: 12 }}>
            {isLoadingTasks ? (
              <div className="loading-center" style={{ minHeight: 120 }}>
                <div className="spinner" style={{ width: 20, height: 20 }} />
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Loading tasks…</span>
              </div>
            ) : (
              <>
                {tasks.length === 0 && !isStaffMode && (
                  <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, padding: '24px 0' }}>
                    No tasks available yet.
                  </p>
                )}

                {isStaffMode && !reviewMode ? (
                  <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
                    <SortableContext items={tasks.map(t => t.id)} strategy={verticalListSortingStrategy}>
                      {tasks.map((task, index) => (
                        <SortableTaskCard
                          key={task.id}
                          task={task}
                          index={index}
                          isStaffMode={isStaffMode}
                          reviewMode={reviewMode}
                          taskProgress={taskProgress}
                          onDeleteTask={onDeleteTask}
                          onEditTask={handleOpenEdit}
                        />
                      ))}
                    </SortableContext>
                  </DndContext>
                ) : (
                  tasks.map((task, index) => (
                    <SortableTaskCard
                      key={task.id}
                      task={task}
                      index={index}
                      isStaffMode={isStaffMode}
                      reviewMode={reviewMode}
                      taskProgress={taskProgress}
                      onDeleteTask={onDeleteTask}
                      onEditTask={handleOpenEdit}
                    />
                  ))
                )}

                {/* Task Creation Form (Staff Only) */}
                {isStaffMode && !reviewMode && (
                  <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, display: 'grid', gap: 10 }}>
                    <p style={{ margin: 0, fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Create New Task
                    </p>

                    <div style={{ display: 'grid', gap: 6 }}>
                      <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
                        Task Title <span style={{ color: 'var(--error)' }}>*</span>
                      </label>
                      <input
                        className="da-input"
                        style={{ width: '100%', fontSize: 13 }}
                        placeholder="e.g., Find all students with grade > 80"
                        value={taskTitle}
                        onChange={(e) => setTaskTitle(e.target.value)}
                      />
                    </div>

                    <MarkdownDescriptionField
                      id="task-description"
                      label="Task Description"
                      required
                      placeholder="Describe what students need to accomplish..."
                      value={taskDescription}
                      onChange={setTaskDescription}
                      minHeight={70}
                    />

                    <div className="da-alert alert-info" style={{ fontSize: 12 }}>
                      After creating the task, execute a query and assign its result as the correct answer from the Results panel.
                    </div>

                    <button
                      className="btn btn-brand"
                      style={{ width: '100%', justifyContent: 'center' }}
                      onClick={handleSubmitTask}
                      disabled={isCreatingTask}
                    >
                      <IconPlus />
                      {isCreatingTask ? 'Creating…' : 'Create Task'}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Review Tab */}
        {activeTab === 'review' && reviewMode && (
          <StudentQueryReviewPanel
            queries={studentQueries}
            currentIndex={currentQueryIndex}
            executedIndices={executedIndices}
            onSelectQuery={onSelectQuery}
            onExecuteNext={onExecuteNext}
            isLoading={isLoadingStudentHistory}
            studentEmail={studentEmail}
          />
        )}
      </div>

      {/* Edit Task Modal */}
      {editingTask !== null && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="edit-task-title">
          <div className="modal">
            <h3 id="edit-task-title" style={{ margin: '0 0 16px' }}>Edit Task</h3>

            <div style={{ display: 'grid', gap: 12 }}>
              <div style={{ display: 'grid', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--brand-charcoal)' }}>
                  Task Title <span style={{ color: 'var(--error)' }}>*</span>
                </label>
                <input
                  className="da-input"
                  style={{ width: '100%' }}
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.currentTarget.value)}
                  required
                />
              </div>

              <MarkdownDescriptionField
                id="edit-task-description"
                label="Task Description"
                required
                value={editDescription}
                onChange={setEditDescription}
                minHeight={80}
              />
            </div>

            <div className="button-row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setEditingTask(null)} disabled={isSavingEdit}>
                Cancel
              </button>
              <button className="btn btn-brand" onClick={handleSaveEdit} disabled={isSavingEdit}>
                {isSavingEdit ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
