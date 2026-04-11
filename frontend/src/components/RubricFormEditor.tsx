"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { IconChevronDown, IconChevronRight, IconPlus, IconTrash } from "@tabler/icons-react";
import type { RubricJsonObject, RubricJsonPrimitive, RubricJsonValue } from "@/types/er-diagram.types";
import {
  RUBRIC_TOP_LEVEL_SECTION_ORDER,
  addRubricDraftArrayItem,
  addRubricDraftObjectField,
  cloneRubricJsonObject,
  getRubricArrayItemLabel,
  getRubricFieldConfig,
  getRubricFieldLabel,
  getRubricObjectKeys,
  getRubricSectionLabel,
  isRubricJsonObject,
  removeRubricDraftValueAtPath,
  setRubricDraftValueAtPath,
  type RubricPath,
} from "@/utils/er-rubric-authoring";

export type RubricFormEditorHandle = {
  commitDraft: () => RubricJsonObject;
  resetDraft: (nextValue: RubricJsonObject) => void;
};

type RubricFormEditorProps = {
  value: RubricJsonObject;
  onDirtyChange?: (dirty: boolean) => void;
  onErrorStateChange?: (hasErrors: boolean) => void;
  disabled?: boolean;
};

type RubricNodeEditorProps = {
  value: RubricJsonValue;
  path: RubricPath;
  revision: number;
  isCollapsed: (path: RubricPath) => boolean;
  hasPathError: (path: RubricPath) => boolean;
  getPathError: (path: RubricPath) => string | null;
  onSetPathError: (path: RubricPath, message: string | null) => void;
  onToggleCollapse: (path: RubricPath) => void;
  onValueChange: (path: RubricPath, nextValue: RubricJsonPrimitive) => void;
  onRemoveValue: (path: RubricPath) => void;
  onAddArrayItem: (path: RubricPath) => void;
  onAddObjectField: (path: RubricPath, key: string) => void;
  disabled?: boolean;
};

type RubricArrayEditorProps = Omit<RubricNodeEditorProps, "value"> & {
  value: RubricJsonValue[];
};

type RubricPrimitiveFieldProps = {
  fieldKey: string;
  value: RubricJsonPrimitive;
  path: RubricPath;
  onValueChange: (path: RubricPath, nextValue: RubricJsonPrimitive) => void;
  onRemove?: () => void;
  disabled?: boolean;
};

type RubricObjectEditorProps = Omit<RubricNodeEditorProps, "value"> & {
  value: RubricJsonObject;
  allowAddField?: boolean;
};

const isPrimitive = (value: RubricJsonValue | undefined): value is RubricJsonPrimitive =>
  value === null || ["string", "number", "boolean"].includes(typeof value);

const getAddItemLabel = (path: RubricPath): string => {
  const lastSegment = path[path.length - 1];
  if (lastSegment === "checks") return "Add Check";
  if (lastSegment === "cardinalities") return "Add Cardinality";
  if (lastSegment === "keys_constraints") return "Add Key Constraint";
  if (lastSegment === "endpoints") return "Add Endpoint";
  if (lastSegment === "equivalence_options") return "Add Equivalence Option";
  if (lastSegment === "keys_required") return "Add Key Requirement";
  if (lastSegment === "entities") return "Add Entity";
  if (lastSegment === "relationships") return "Add Relationship";
  if (lastSegment === "attributes_required") return "Add Attribute";
  return "Add Item";
};

const getSelectData = (options: string[]): Array<{ value: string; label: string }> =>
  options.map((option) => ({
    value: option,
    label: getRubricFieldLabel(option),
  }));

const ROOT_ERROR_KEY = "__root__";
const getPathKey = (path: RubricPath): string => path.map((segment) => String(segment)).join(".");
const getErrorKey = (path: RubricPath): string => (path.length === 0 ? ROOT_ERROR_KEY : getPathKey(path));
const hiddenBodyStyle = { display: "none" } as const;
const errorBorderStyle = { borderColor: "var(--mantine-color-red-4)" } as const;
const errorTitleProps = { c: "red" as const };

type CollapseToggleButtonProps = {
  collapsed: boolean;
  onToggle: () => void;
  label: string;
  hasError?: boolean;
  disabled?: boolean;
};

function CollapseToggleButton({ collapsed, onToggle, label, hasError, disabled }: CollapseToggleButtonProps) {
  return (
    <ActionIcon
      variant="subtle"
      color={hasError ? "red" : "gray"}
      onClick={onToggle}
      disabled={disabled}
      aria-label={collapsed ? `Expand ${label}` : `Collapse ${label}`}
    >
      {collapsed ? <IconChevronRight size={16} /> : <IconChevronDown size={16} />}
    </ActionIcon>
  );
}

function RubricPrimitiveField({
  fieldKey,
  value,
  path,
  onValueChange,
  onRemove,
  disabled,
}: RubricPrimitiveFieldProps) {
  const [draftValue, setDraftValue] = useState<RubricJsonPrimitive>(value);

  const config = getRubricFieldConfig(path.slice(0, -1), fieldKey, draftValue);
  const label = getRubricFieldLabel(fieldKey);

  const handleScalarChange = (nextValue: RubricJsonPrimitive) => {
    setDraftValue(nextValue);
    onValueChange(path, nextValue);
  };

  return (
    <Stack gap={4}>
      <Group justify="space-between" align="center" gap="xs">
        <Text size="sm" fw={500}>
          {label}
        </Text>
        {onRemove ? (
          <ActionIcon
            variant="subtle"
            color="red"
            onClick={onRemove}
            disabled={disabled}
            aria-label={`Remove ${label}`}
          >
            <IconTrash size={16} />
          </ActionIcon>
        ) : null}
      </Group>

      {config.control === "switch" ? (
        <Switch
          checked={Boolean(draftValue)}
          onChange={(event) => handleScalarChange(event.currentTarget.checked)}
          disabled={disabled}
        />
      ) : null}

      {config.control === "number" ? (
        <NumberInput
          value={typeof draftValue === "number" ? draftValue : 0}
          onChange={(nextValue) => handleScalarChange(typeof nextValue === "number" ? nextValue : 0)}
          disabled={disabled}
        />
      ) : null}

      {config.control === "select" ? (
        <Select
          data={getSelectData(config.options || [])}
          value={typeof draftValue === "string" ? draftValue : null}
          onChange={(nextValue) => handleScalarChange(nextValue ?? null)}
          clearable={config.clearable}
          searchable
          disabled={disabled}
        />
      ) : null}

      {config.control === "textarea" ? (
        <Textarea
          value={typeof draftValue === "string" ? draftValue : ""}
          onChange={(event) => handleScalarChange(event.currentTarget.value)}
          placeholder={draftValue === null ? "Null" : undefined}
          rows={config.rows || 4}
          disabled={disabled}
        />
      ) : null}

      {config.control === "text" ? (
        <TextInput
          value={typeof draftValue === "string" ? draftValue : ""}
          onChange={(event) => handleScalarChange(event.currentTarget.value)}
          placeholder={draftValue === null ? "Null" : undefined}
          disabled={disabled}
        />
      ) : null}
    </Stack>
  );
}

function RubricArrayEditor({
  value,
  path,
  revision,
  isCollapsed,
  hasPathError,
  getPathError,
  onSetPathError,
  onToggleCollapse,
  onValueChange,
  onRemoveValue,
  onAddArrayItem,
  onAddObjectField,
  disabled,
}: RubricArrayEditorProps) {
  return (
    <Stack gap="sm">
      {value.length === 0 ? (
        <Text size="sm" c="dimmed">
          No items yet.
        </Text>
      ) : null}

      {value.map((item, index) => (
        <Paper
          withBorder
          radius="md"
          p="sm"
          key={`${String(path[path.length - 1] || "item")}-${index}`}
          style={isRubricJsonObject(item) && hasPathError([...path, index]) ? errorBorderStyle : undefined}
        >
          <Stack gap="sm">
            <Group justify="space-between" align="center" gap="sm">
              <Badge
                variant="outline"
                radius="xl"
                color={isRubricJsonObject(item) && hasPathError([...path, index]) ? "red" : "gray"}
              >
                {getRubricArrayItemLabel(path, item, index)}
              </Badge>
              <Group gap={4}>
                {isRubricJsonObject(item) ? (
                  <CollapseToggleButton
                    collapsed={isCollapsed([...path, index])}
                    onToggle={() => onToggleCollapse([...path, index])}
                    label={`item ${index + 1}`}
                    hasError={hasPathError([...path, index])}
                    disabled={disabled}
                  />
                ) : null}
                <ActionIcon
                  variant="subtle"
                  color="red"
                  onClick={() => onRemoveValue([...path, index])}
                  disabled={disabled}
                  aria-label={`Remove item ${index + 1}`}
                >
                  <IconTrash size={16} />
                </ActionIcon>
              </Group>
            </Group>

            {isPrimitive(item) ? (
              <RubricPrimitiveField
                key={`${getPathKey([...path, index])}-${revision}`}
                fieldKey={`item_${index + 1}`}
                value={item}
                path={[...path, index]}
                onValueChange={onValueChange}
                disabled={disabled}
              />
            ) : (
              <div style={isCollapsed([...path, index]) ? hiddenBodyStyle : undefined} aria-hidden={isCollapsed([...path, index])}>
                <RubricNodeEditor
                  value={item}
                  path={[...path, index]}
                  revision={revision}
                  isCollapsed={isCollapsed}
                  hasPathError={hasPathError}
                  getPathError={getPathError}
                  onSetPathError={onSetPathError}
                  onToggleCollapse={onToggleCollapse}
                  onValueChange={onValueChange}
                  onRemoveValue={onRemoveValue}
                  onAddArrayItem={onAddArrayItem}
                  onAddObjectField={onAddObjectField}
                  disabled={disabled}
                />
              </div>
            )}
          </Stack>
        </Paper>
      ))}

      <Button
        variant="light"
        leftSection={<IconPlus size={16} />}
        onClick={() => onAddArrayItem(path)}
        disabled={disabled}
        fullWidth
      >
        {getAddItemLabel(path)}
      </Button>
    </Stack>
  );
}

function RubricObjectEditor({
  value,
  path,
  revision,
  isCollapsed,
  hasPathError,
  getPathError,
  onSetPathError,
  onToggleCollapse,
  onValueChange,
  onRemoveValue,
  onAddArrayItem,
  onAddObjectField,
  disabled,
  allowAddField = true,
}: RubricObjectEditorProps) {
  const [newFieldName, setNewFieldName] = useState("");
  const addFieldError = getPathError(path);
  const keys = getRubricObjectKeys(path, value);

  const handleAddField = () => {
    const trimmed = newFieldName.trim();
    if (!trimmed) {
      onSetPathError(path, "Field name is required.");
      return;
    }
    if (Object.prototype.hasOwnProperty.call(value, trimmed)) {
      onSetPathError(path, "That field already exists.");
      return;
    }

    onAddObjectField(path, trimmed);
    setNewFieldName("");
    onSetPathError(path, null);
  };

  return (
    <Stack gap="sm">
      {keys.length === 0 ? (
        <Text size="sm" c="dimmed">
          No fields yet.
        </Text>
      ) : null}

      {keys.map((fieldKey) => {
        const nestedValue = value[fieldKey];
        if (typeof nestedValue === "undefined") {
          return null;
        }

        const removeField = () => onRemoveValue([...path, fieldKey]);

        if (isPrimitive(nestedValue)) {
          return (
            <RubricPrimitiveField
              key={`${getPathKey([...path, fieldKey])}-${revision}`}
              fieldKey={fieldKey}
              value={nestedValue}
              path={[...path, fieldKey]}
              onValueChange={onValueChange}
              onRemove={path.length > 0 ? removeField : undefined}
              disabled={disabled}
            />
          );
        }

        return (
          <Paper
            withBorder
            radius="md"
            p="sm"
            key={fieldKey}
            style={hasPathError([...path, fieldKey]) ? errorBorderStyle : undefined}
          >
            <Stack gap="sm">
              <Group justify="space-between" align="center" gap="sm">
                <Text size="sm" fw={600} {...(hasPathError([...path, fieldKey]) ? errorTitleProps : {})}>
                  {getRubricFieldLabel(fieldKey)}
                </Text>
                <Group gap={4}>
                  {isRubricJsonObject(nestedValue) ? (
                    <CollapseToggleButton
                      collapsed={isCollapsed([...path, fieldKey])}
                      onToggle={() => onToggleCollapse([...path, fieldKey])}
                      label={getRubricFieldLabel(fieldKey)}
                      hasError={hasPathError([...path, fieldKey])}
                      disabled={disabled}
                    />
                  ) : null}
                  {path.length > 0 ? (
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      onClick={removeField}
                      disabled={disabled}
                      aria-label={`Remove ${fieldKey}`}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  ) : null}
                </Group>
              </Group>
              <div
                style={isRubricJsonObject(nestedValue) && isCollapsed([...path, fieldKey]) ? hiddenBodyStyle : undefined}
                aria-hidden={isRubricJsonObject(nestedValue) ? isCollapsed([...path, fieldKey]) : undefined}
              >
                <RubricNodeEditor
                  value={nestedValue}
                  path={[...path, fieldKey]}
                  revision={revision}
                  isCollapsed={isCollapsed}
                  hasPathError={hasPathError}
                  getPathError={getPathError}
                  onSetPathError={onSetPathError}
                  onToggleCollapse={onToggleCollapse}
                  onValueChange={onValueChange}
                  onRemoveValue={onRemoveValue}
                  onAddArrayItem={onAddArrayItem}
                  onAddObjectField={onAddObjectField}
                  disabled={disabled}
                />
              </div>
            </Stack>
          </Paper>
        );
      })}

      {allowAddField ? (
        <>
          <Divider label="Add Custom Field" labelPosition="center" />
          <Group align="flex-start" gap="sm">
            <TextInput
              value={newFieldName}
              onChange={(event) => {
                setNewFieldName(event.currentTarget.value);
                if (addFieldError) {
                  onSetPathError(path, null);
                }
              }}
              placeholder="Field name"
              disabled={disabled}
              style={{ flex: 1 }}
            />
            <Button
              variant="light"
              leftSection={<IconPlus size={16} />}
              onClick={handleAddField}
              disabled={disabled}
            >
              Add Field
            </Button>
          </Group>
          {addFieldError ? (
            <Text size="xs" c="red">
              {addFieldError}
            </Text>
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}

function RubricNodeEditor(props: RubricNodeEditorProps) {
  if (Array.isArray(props.value)) {
    return <RubricArrayEditor {...props} value={props.value} />;
  }

  if (isRubricJsonObject(props.value)) {
    return <RubricObjectEditor {...props} value={props.value} />;
  }

  return (
    <RubricPrimitiveField
      key={`${getPathKey(props.path)}-${props.revision}`}
      fieldKey={String(props.path[props.path.length - 1] || "value")}
      value={props.value}
      path={props.path}
      onValueChange={props.onValueChange}
      disabled={props.disabled}
    />
  );
}

const RubricFormEditor = forwardRef<RubricFormEditorHandle, RubricFormEditorProps>(function RubricFormEditor(
  { value, onDirtyChange, onErrorStateChange, disabled },
  ref,
) {
  const draftRef = useRef<RubricJsonObject>(cloneRubricJsonObject(value));
  const [renderValue, setRenderValue] = useState<RubricJsonObject>(() => cloneRubricJsonObject(value));
  const [collapsedPaths, setCollapsedPaths] = useState<Set<string>>(() => new Set());
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [revision, setRevision] = useState(0);
  const [newTopLevelField, setNewTopLevelField] = useState("");
  const topLevelError = validationErrors[ROOT_ERROR_KEY] ?? null;

  const syncDraftView = useCallback(() => {
    setRenderValue(cloneRubricJsonObject(draftRef.current));
    setRevision((current) => current + 1);
  }, []);

  const resetDraft = useCallback((nextValue: RubricJsonObject) => {
    draftRef.current = cloneRubricJsonObject(nextValue);
    setRenderValue(cloneRubricJsonObject(nextValue));
    setCollapsedPaths(new Set());
    setValidationErrors({});
    setRevision((current) => current + 1);
  }, []);

  useImperativeHandle(ref, () => ({
    commitDraft: () => cloneRubricJsonObject(draftRef.current),
    resetDraft,
  }));

  useEffect(() => {
    onErrorStateChange?.(Object.keys(validationErrors).length > 0);
  }, [onErrorStateChange, validationErrors]);

  const markDirty = () => {
    onDirtyChange?.(true);
  };

  const setPathError = useCallback((path: RubricPath, message: string | null) => {
    const pathKey = getErrorKey(path);
    setValidationErrors((current) => {
      if (!message) {
        if (!(pathKey in current)) {
          return current;
        }
        const next = { ...current };
        delete next[pathKey];
        return next;
      }

      if (current[pathKey] === message) {
        return current;
      }

      return {
        ...current,
        [pathKey]: message,
      };
    });
  }, []);

  const clearPathErrors = useCallback((path: RubricPath) => {
    const pathKey = getErrorKey(path);
    setValidationErrors((current) => {
      const nextEntries = Object.entries(current).filter(([key]) => {
        if (pathKey === ROOT_ERROR_KEY) {
          return false;
        }
        return key !== pathKey && !key.startsWith(`${pathKey}.`);
      });
      if (nextEntries.length === Object.keys(current).length) {
        return current;
      }
      return Object.fromEntries(nextEntries);
    });
  }, []);

  const getPathError = useCallback(
    (path: RubricPath) => validationErrors[getErrorKey(path)] ?? null,
    [validationErrors],
  );

  const hasPathError = useCallback(
    (path: RubricPath) => {
      const pathKey = getErrorKey(path);
      const errorKeys = Object.keys(validationErrors);
      if (pathKey === ROOT_ERROR_KEY) {
        return errorKeys.length > 0;
      }
      return errorKeys.some((key) => key === pathKey || key.startsWith(`${pathKey}.`));
    },
    [validationErrors],
  );

  const handleValueChange = (path: RubricPath, nextValue: RubricJsonPrimitive) => {
    setRubricDraftValueAtPath(draftRef.current, path, nextValue);
    markDirty();
  };

  const handleRemoveValue = (path: RubricPath) => {
    removeRubricDraftValueAtPath(draftRef.current, path);
    markDirty();
    if (typeof path[path.length - 1] === "number") {
      setValidationErrors({});
    } else {
      clearPathErrors(path);
    }
    if (typeof path[path.length - 1] === "number") {
      setCollapsedPaths(new Set());
    } else {
      const pathKey = getPathKey(path);
      setCollapsedPaths((current) => {
        const next = new Set([...current].filter((key) => key !== pathKey && !key.startsWith(`${pathKey}.`)));
        return next;
      });
    }
    syncDraftView();
  };

  const handleAddArrayItem = (path: RubricPath) => {
    addRubricDraftArrayItem(draftRef.current, path);
    markDirty();
    setCollapsedPaths(new Set());
    syncDraftView();
  };

  const handleAddObjectField = (path: RubricPath, key: string) => {
    addRubricDraftObjectField(draftRef.current, path, key);
    markDirty();
    setPathError(path, null);
    syncDraftView();
  };

  const isCollapsed = useCallback(
    (path: RubricPath) => collapsedPaths.has(getPathKey(path)),
    [collapsedPaths],
  );

  const handleToggleCollapse = (path: RubricPath) => {
    const pathKey = getPathKey(path);
    setCollapsedPaths((current) => {
      const next = new Set(current);
      if (next.has(pathKey)) {
        next.delete(pathKey);
      } else {
        next.add(pathKey);
      }
      return next;
    });
  };

  const existingKeys = Object.keys(renderValue);
  const preferredKeys = RUBRIC_TOP_LEVEL_SECTION_ORDER.filter((key) => existingKeys.includes(key));
  const additionalKeys = existingKeys
    .filter((key) => !RUBRIC_TOP_LEVEL_SECTION_ORDER.includes(key as typeof RUBRIC_TOP_LEVEL_SECTION_ORDER[number]))
    .sort((left, right) => left.localeCompare(right));
  const orderedSectionKeys = [...preferredKeys, ...additionalKeys];

  const handleAddTopLevelField = () => {
    const trimmed = newTopLevelField.trim();
    if (!trimmed) {
      setPathError([], "Field name is required.");
      return;
    }
    if (Object.prototype.hasOwnProperty.call(renderValue, trimmed)) {
      setPathError([], "That field already exists.");
      return;
    }

    handleAddObjectField([], trimmed);
    setNewTopLevelField("");
    setPathError([], null);
  };

  return (
    <Stack gap="md">
      {orderedSectionKeys.map((sectionKey) => {
        const sectionValue = renderValue[sectionKey];
        if (typeof sectionValue === "undefined") {
          return null;
        }

        const isKnownSection = RUBRIC_TOP_LEVEL_SECTION_ORDER.includes(
          sectionKey as typeof RUBRIC_TOP_LEVEL_SECTION_ORDER[number],
        );

        return (
          <Card
            withBorder
            radius="md"
            padding="md"
            key={sectionKey}
            style={hasPathError([sectionKey]) ? errorBorderStyle : undefined}
          >
            <Stack gap="md">
              <Group justify="space-between" align="center" gap="sm">
                <div>
                  <Title order={5} {...(hasPathError([sectionKey]) ? errorTitleProps : {})}>
                    {getRubricSectionLabel(sectionKey)}
                  </Title>
                  <Text size="sm" c="dimmed">
                    {isKnownSection ? "Edit the generated rubric fields below." : "Additional rubric section."}
                  </Text>
                </div>
                <Group gap={4}>
                  <CollapseToggleButton
                    collapsed={isCollapsed([sectionKey])}
                    onToggle={() => handleToggleCollapse([sectionKey])}
                    label={getRubricSectionLabel(sectionKey)}
                    hasError={hasPathError([sectionKey])}
                    disabled={disabled}
                  />
                  {!isKnownSection ? (
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      onClick={() => handleRemoveValue([sectionKey])}
                      disabled={disabled}
                      aria-label={`Remove section ${sectionKey}`}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  ) : null}
                </Group>
              </Group>
              <div style={isCollapsed([sectionKey]) ? hiddenBodyStyle : undefined} aria-hidden={isCollapsed([sectionKey])}>
                <RubricNodeEditor
                  value={sectionValue}
                  path={[sectionKey]}
                  revision={revision}
                  isCollapsed={isCollapsed}
                  hasPathError={hasPathError}
                  getPathError={getPathError}
                  onSetPathError={setPathError}
                  onToggleCollapse={handleToggleCollapse}
                  onValueChange={handleValueChange}
                  onRemoveValue={handleRemoveValue}
                  onAddArrayItem={handleAddArrayItem}
                  onAddObjectField={handleAddObjectField}
                  disabled={disabled}
                />
              </div>
            </Stack>
          </Card>
        );
      })}

      <Card withBorder radius="md" padding="md">
        <Stack gap="sm">
          <Title order={6}>Add Top-Level Field</Title>
          <Text size="sm" c="dimmed">
            Use this for rubric sections or custom metadata that are not already present.
          </Text>
          <Group align="flex-start" gap="sm">
            <TextInput
              value={newTopLevelField}
              onChange={(event) => {
                setNewTopLevelField(event.currentTarget.value);
                if (topLevelError) {
                  setPathError([], null);
                }
              }}
              placeholder="Top-level field name"
              disabled={disabled}
              style={{ flex: 1 }}
            />
            <Button
              variant="light"
              leftSection={<IconPlus size={16} />}
              onClick={handleAddTopLevelField}
              disabled={disabled}
            >
              Add Field
            </Button>
          </Group>
          {topLevelError ? (
            <Text size="xs" c="red">
              {topLevelError}
            </Text>
          ) : null}
        </Stack>
      </Card>
    </Stack>
  );
});

export default RubricFormEditor;
