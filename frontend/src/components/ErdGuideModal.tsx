"use client";

import { useState, type ReactNode } from "react";
import Image from "next/image";
import {
  Alert,
  Box,
  Button,
  Code,
  Flex,
  Group,
  Kbd,
  List,
  Modal,
  Paper,
  SimpleGrid,
  Stack,
  Stepper,
  Text,
} from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { TUTOR_NAME } from "@/components/ChatPanel";
import drawioTheme from "@/components/DrawioTheme.module.css";

/**
 * First-run guide for the draw.io focus mode.
 *
 * WHY
 * The grader does not look at the picture — it parses the draw.io XML
 * (backend drawio_parser.py) and reads shapes by their style: rectangle =
 * entity, rhombus = relationship, ellipse = attribute, triangle = ISA, and
 * connectors only count when they are attached (source/target set). A student
 * who builds a diagram from plain boxes + separate Text labels + lines that
 * merely touch produces XML with unnamed entities and no participants, and the
 * tutor's feedback then looks like nonsense to them. Every step below exists to
 * head off one of those specific misreads, so keep the instructions in step
 * with what the parser actually recognises.
 */

type ErdGuideModalProps = {
  opened: boolean;
  onClose: () => void;
  /** False once the student has chosen "Don't remind me again". */
  canDismissForever: boolean;
  onDismissForever: () => void;
};

const BRAND_THEME_CLASS = drawioTheme.drawioTheme;
const LAST_STEP = 3;

// ---------------------------------------------------------------------------
// Illustrations. Plain inline SVG so they need no assets, follow the text
// colour in either colour scheme, and stay crisp at any size.
// ---------------------------------------------------------------------------

const INK = "var(--mantine-color-text)";
const ACCENT = "var(--mantine-color-blue-6)"; // brand purple inside the drawio theme
const GOOD = "var(--mantine-color-green-6)";
const BAD = "var(--mantine-color-red-6)";

type FigureProps = { viewBox: string; maxWidth?: number; label: string; children: ReactNode };

function Figure({ viewBox, maxWidth = 120, label, children }: FigureProps) {
  return (
    <svg
      viewBox={viewBox}
      role="img"
      aria-label={label}
      fill="none"
      stroke={INK}
      strokeWidth={1.5}
      style={{ width: "100%", maxWidth, height: "auto", display: "block" }}
    >
      {children}
    </svg>
  );
}

type LabelProps = { x: number; y: number; children: ReactNode; size?: number; color?: string; underline?: boolean };

function Label({ x, y, children, size = 11, color = INK, underline = false }: LabelProps) {
  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      dominantBaseline="middle"
      fontSize={size}
      fontFamily="inherit"
      fill={color}
      stroke="none"
      textDecoration={underline ? "underline" : undefined}
    >
      {children}
    </text>
  );
}

const EntityFigure = () => (
  <Figure viewBox="0 0 120 60" label="Entity: a rectangle with its name inside">
    <rect x={15} y={12} width={90} height={36} />
    <Label x={60} y={30}>Student</Label>
  </Figure>
);

const WeakEntityFigure = () => (
  <Figure viewBox="0 0 120 60" label="Weak entity: a double-bordered rectangle">
    <rect x={15} y={12} width={90} height={36} />
    <rect x={19} y={16} width={82} height={28} />
    <Label x={60} y={30}>Dependant</Label>
  </Figure>
);

const RelationshipFigure = () => (
  <Figure viewBox="0 0 120 60" label="Relationship: a diamond with its name inside">
    <polygon points="60,4 114,30 60,56 6,30" />
    <Label x={60} y={30}>Enrols</Label>
  </Figure>
);

const IdentifyingRelationshipFigure = () => (
  <Figure viewBox="0 0 120 60" label="Identifying relationship: a double-bordered diamond">
    <polygon points="60,4 114,30 60,56 6,30" />
    <polygon points="60,11 100,30 60,49 20,30" />
    <Label x={60} y={30}>Has</Label>
  </Figure>
);

const AttributeFigure = () => (
  <Figure viewBox="0 0 120 60" label="Attribute: an ellipse with its name inside">
    <ellipse cx={60} cy={30} rx={46} ry={20} />
    <Label x={60} y={30}>name</Label>
  </Figure>
);

const KeyAttributeFigure = () => (
  <Figure viewBox="0 0 120 60" label="Key attribute: an ellipse whose name text is underlined">
    <ellipse cx={60} cy={30} rx={46} ry={20} />
    <Label x={60} y={30} underline>
      student_id
    </Label>
  </Figure>
);

const IsaFigure = () => (
  <Figure viewBox="0 0 120 60" label="Specialisation: a triangle, supertype above and subtypes below">
    <line x1={60} y1={0} x2={60} y2={10} />
    <polygon points="60,10 104,52 16,52" />
    <Label x={60} y={40}>ISA</Label>
    <line x1={40} y1={52} x2={30} y2={60} />
    <line x1={80} y1={52} x2={90} y2={60} />
  </Figure>
);

const FloatingTextFigure = () => (
  <Figure viewBox="0 0 120 60" label="Not read: an empty box with a separate text label floating over it">
    <rect x={10} y={16} width={70} height={36} />
    <rect x={52} y={4} width={62} height={20} strokeDasharray="3 3" stroke={BAD} />
    <Label x={83} y={14} color={BAD}>
      Student
    </Label>
    <Label x={104} y={44} size={18} color={BAD}>
      ✗
    </Label>
  </Figure>
);

const AttachedFigure = () => (
  <Figure viewBox="0 0 220 64" maxWidth={220} label="Attached connector: it starts on the entity border and ends on the diamond">
    <rect x={6} y={14} width={70} height={36} />
    <Label x={41} y={32}>Student</Label>
    <polygon points="160,4 214,32 160,60 106,32" />
    <Label x={160} y={32}>Enrols</Label>
    <line x1={76} y1={32} x2={106} y2={32} />
    <circle cx={76} cy={32} r={3} fill={GOOD} stroke="none" />
    <circle cx={106} cy={32} r={3} fill={GOOD} stroke="none" />
  </Figure>
);

const FloatingLineFigure = () => (
  <Figure viewBox="0 0 220 64" maxWidth={220} label="Floating line: it stops short of both shapes and links nothing">
    <rect x={6} y={14} width={70} height={36} />
    <Label x={41} y={32}>Student</Label>
    <polygon points="160,4 214,32 160,60 106,32" />
    <Label x={160} y={32}>Enrols</Label>
    <line x1={82} y1={36} x2={100} y2={36} />
    <circle cx={82} cy={36} r={3} stroke={BAD} />
    <circle cx={100} cy={36} r={3} stroke={BAD} />
  </Figure>
);

const CardinalityFigure = () => (
  <Figure viewBox="0 0 340 80" maxWidth={340} label="Two endpoints marked in the course notation">
    <rect x={6} y={22} width={64} height={36} />
    <Label x={38} y={40}>A</Label>
    <polygon points="170,12 210,40 170,68 130,40" />
    <Label x={170} y={40}>R</Label>
    <rect x={270} y={22} width={64} height={36} />
    <Label x={302} y={40}>B</Label>
    {/* A end: ">=1" text + curve at the entity, drawn "(—": its back to the
        entity, its opening toward the diamond. */}
    <line x1={70} y1={40} x2={130} y2={40} />
    <path d="M 80 26 Q 61 40 80 54" stroke={ACCENT} strokeWidth={2} />
    <Label x={104} y={30} color={ACCENT}>
      {">=1"}
    </Label>
    {/* B end: ">=0" text, plain end */}
    <line x1={210} y1={40} x2={270} y2={40} />
    <Label x={236} y={30} color={ACCENT}>
      {">=0"}
    </Label>
  </Figure>
);

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

type ShapeCardProps = { figure: ReactNode; name: string; hint: string; bad?: boolean };

function ShapeCard({ figure, name, hint, bad = false }: ShapeCardProps) {
  return (
    <Paper
      withBorder
      radius="md"
      p="xs"
      style={bad ? { borderColor: "var(--mantine-color-red-4)" } : undefined}
    >
      <Stack gap={4} align="center">
        {figure}
        <Text size="xs" fw={600} ta="center" c={bad ? "red" : undefined}>
          {name}
        </Text>
        <Text size="xs" c="dimmed" ta="center" lh={1.3}>
          {hint}
        </Text>
      </Stack>
    </Paper>
  );
}

function ShapesStep() {
  return (
    <Stack gap="sm">
      <Text size="sm">
        {TUTOR_NAME} does not look at the picture — it reads <b>which shapes</b> you used and how
        they are joined. Build everything from the <b>Entity Relation</b> section of the{" "}
        <b>Shapes</b> panel, pictured on the left: <b>①</b> if the panel is hidden, open it from{" "}
        <b>Shapes</b> in the top toolbar; <b>②</b> scroll to the bottom and click{" "}
        <b>Entity Relation</b> to expand it, then drag the shapes below onto the canvas.
      </Text>
      <Flex direction={{ base: "column", sm: "row" }} gap="md" align="flex-start">
        <Stack gap={4} align="center" style={{ flexShrink: 0 }}>
          <Image
            src="/erd-guide/shapes-panel.png"
            alt="The draw.io Shapes panel: the Shapes menu in the top toolbar (1) and the Entity Relation section at the bottom of the panel (2)"
            width={508}
            height={940}
            style={{ width: 210, height: "auto", borderRadius: 8, border: "1px solid var(--mantine-color-gray-3)" }}
          />
          <Text size="xs" c="dimmed" ta="center">
            ① Shapes menu · ② Entity Relation
          </Text>
        </Stack>
        <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="xs" style={{ flex: 1, minWidth: 0 }}>
          <ShapeCard figure={<EntityFigure />} name="Entity" hint="Rectangle. Type the name inside." />
          <ShapeCard figure={<WeakEntityFigure />} name="Weak entity" hint="Double-bordered rectangle." />
          <ShapeCard figure={<RelationshipFigure />} name="Relationship" hint="Diamond. Type the name inside." />
          <ShapeCard figure={<IdentifyingRelationshipFigure />} name="Identifying relationship" hint="Double-bordered diamond." />
          <ShapeCard figure={<AttributeFigure />} name="Attribute" hint="Ellipse, connected to its entity or relationship." />
          <ShapeCard figure={<KeyAttributeFigure />} name="Key attribute" hint="Ellipse with the name text underlined." />
          <ShapeCard figure={<IsaFigure />} name="Specialisation" hint="Triangle from General; supertype above, subtypes below." />
          <ShapeCard figure={<FloatingTextFigure />} name="Not read" hint="An empty box with a separate Text label on top." bad />
        </SimpleGrid>
      </Flex>
      <Alert icon={<IconAlertTriangle size={16} />} color="yellow" variant="light" py="xs">
        <Text size="sm">
          <b>Type names inside the shape.</b> Double-click a shape and type. A separate <i>Text</i>{" "}
          box laid over an empty box is not its name — {TUTOR_NAME} sees an unnamed box plus a stray
          label.
        </Text>
      </Alert>
      <Text size="sm">
        For a <b>key attribute</b>, double-click the attribute, select its name and press{" "}
        <Kbd size="xs">Ctrl</Kbd>+<Kbd size="xs">U</Kbd> so the <i>text itself</i> is underlined.
        Underlining the whole shape from the Format panel, or the palette&apos;s ready-made
        &ldquo;Key Attribute&rdquo;, is not picked up.
      </Text>
    </Stack>
  );
}

function ConnectStep() {
  return (
    <Stack gap="sm">
      <Text size="sm">
        Join shapes with connectors that are <b>attached at both ends</b>. A line that only sits on
        top of two shapes links nothing.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <Paper withBorder radius="md" p="sm">
          <Stack gap={4} align="center">
            <AttachedFigure />
            <Text size="xs" fw={600} c="green">
              Attached — moves with the shapes
            </Text>
          </Stack>
        </Paper>
        <Paper withBorder radius="md" p="sm" style={{ borderColor: "var(--mantine-color-red-4)" }}>
          <Stack gap={4} align="center">
            <FloatingLineFigure />
            <Text size="xs" fw={600} c="red">
              Just touching — nothing is linked
            </Text>
          </Stack>
        </Paper>
      </SimpleGrid>
      <List size="sm" spacing={4}>
        <List.Item>
          Hover a shape and drag one of the <b>blue arrows</b> onto the target shape; drop when the
          target lights up. Or drag from a connection point (<b>×</b>) on the shape&apos;s border.
        </List.Item>
        <List.Item>
          <b>Test it:</b> move a shape. If the line follows, it is attached. If it stays behind, it
          was only drawn on top and {TUTOR_NAME} sees no connection.
        </List.Item>
        <List.Item>
          Entities join to relationship diamonds; each attribute joins to the entity or relationship
          it describes.
        </List.Item>
      </List>
    </Stack>
  );
}

function CardinalityStep() {
  return (
    <Stack gap="sm">
      <Text size="sm">
        Mark each connector at the <b>entity end</b>, in the notation the course uses:
      </Text>
      <Paper withBorder radius="md" p="sm">
        <Stack gap={6} align="center">
          <CardinalityFigure />
          <Group gap="lg" justify="center">
            <Text size="xs" c="dimmed">
              A end: <Code>{">=1"}</Code> + curve → 1..N, total
            </Text>
            <Text size="xs" c="dimmed">
              B end: <Code>{">=0"}</Code>, plain → 0..1, partial
            </Text>
          </Group>
        </Stack>
      </Paper>
      <Stack gap={4} align="center">
        <Image
          src="/erd-guide/arc-cue.png"
          alt="Adding the curve in draw.io: type arc in the Shapes search box (1), drag the plain Arc shape (2) and drop it on the connector against the entity, opening toward the diamond (3)"
          width={1300}
          height={600}
          style={{ width: "100%", maxWidth: 600, height: "auto", borderRadius: 8, border: "1px solid var(--mantine-color-gray-3)" }}
        />
        <Text size="xs" c="dimmed" ta="center">
          Adding the curve: ① type <Code>arc</Code> in the Shapes search · ② drag the plain <b>Arc</b>{" "}
          · ③ drop it on the line against the entity, opening toward the diamond
        </Text>
      </Stack>
      <List size="sm" spacing={4}>
        <List.Item>
          <b>Minimum / participation</b> — a text label on the line, next to the entity:{" "}
          <Code>{">=1"}</Code> (total), <Code>{">=0"}</Code> (partial), <Code>{"<=1"}</Code>,{" "}
          <Code>=1</Code>, or a range such as <Code>0..1</Code> or <Code>1..N</Code>. Double-click
          the connector near that end and type.
        </List.Item>
        <List.Item>
          <b>Many</b> — a curve at the entity end, like <Code>(—</Code> (pictured above). Type{" "}
          <Code>arc</Code> in the Shapes search box, drag the plain <b>Arc</b> onto the line right
          beside the entity, with its back to the entity and its opening toward the diamond — flip it
          horizontally (Arrange ▸ Flip) for an entity on the right. The stock size is fine.
        </List.Item>
        <List.Item>
          <b>One</b> — leave the end plain. In this notation a plain line end already means
          &ldquo;at most one&rdquo;.
        </List.Item>
        <List.Item>
          <b>Weak entity / identifying relationship</b> — use the double-bordered shapes; the extra
          border is what gets read.
        </List.Item>
      </List>
    </Stack>
  );
}

function SubmitStep() {
  return (
    <Stack gap="sm">
      <List size="sm" spacing={6}>
        <List.Item>
          <b>Autosave</b> — every change is saved as you draw. The status left of Submit says where:{" "}
          <i>Saved 10:32:05</i> means on your account (any device); <i>Saved on this device only</i>{" "}
          means this browser only, so also download a copy; <i>Not auto-saved yet</i> means nothing
          is stored yet.
        </List.Item>
        <List.Item>
          <b>File ▸ Save to file</b> (<Kbd size="xs">Ctrl</Kbd>+<Kbd size="xs">S</Kbd>) downloads a{" "}
          <Code>.drawio</Code> copy you can keep or bring to another computer; <b>File ▸ Load from
          file…</b> puts it back on the canvas.
        </List.Item>
        <List.Item>
          <b>Problem</b> re-opens the question; <b>{TUTOR_NAME}</b> lets you ask the tutor while you
          draw.
        </List.Item>
        <List.Item>
          <b>Submit</b> grades the diagram. You can add an optional note first (use it for anything
          hard to read — for example which line a label belongs to); then {TUTOR_NAME}&apos;s
          feedback opens on the right with your score at the top. Submitting is what records your
          attempt — leaving focus mode does not.
        </List.Item>
        <List.Item>
          Reopen this guide any time with the <b>?</b> button in the toolbar.
        </List.Item>
      </List>
    </Stack>
  );
}

// ---------------------------------------------------------------------------

type GuideBodyProps = Omit<ErdGuideModalProps, "opened">;

/**
 * Lives inside the Modal, which unmounts its children when closed — so the
 * step counter starts from the first step on every open, and re-reading via
 * the ? button never lands mid-way through.
 */
function GuideBody({ onClose, canDismissForever, onDismissForever }: GuideBodyProps) {
  const [step, setStep] = useState(0);

  return (
    <Stack gap="md">
      <Stepper active={step} onStepClick={setStep} size="sm" iconSize={28}>
        <Stepper.Step label="Shapes">
          <ShapesStep />
        </Stepper.Step>
        <Stepper.Step label="Connect">
          <ConnectStep />
        </Stepper.Step>
        <Stepper.Step label="Cardinality">
          <CardinalityStep />
        </Stepper.Step>
        <Stepper.Step label="Save & submit">
          <SubmitStep />
        </Stepper.Step>
      </Stepper>

      <Group justify="space-between" gap="sm">
        {canDismissForever ? (
          <Button variant="subtle" size="xs" onClick={onDismissForever} data-testid="erd-guide-dismiss-forever">
            Don&apos;t remind me again
          </Button>
        ) : (
          <Box />
        )}
        <Group gap="sm">
          <Button variant="default" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
            Back
          </Button>
          {step < LAST_STEP ? (
            <Button onClick={() => setStep((s) => Math.min(LAST_STEP, s + 1))}>Next</Button>
          ) : (
            <Button onClick={onClose}>Got it</Button>
          )}
        </Group>
      </Group>
    </Stack>
  );
}

export function ErdGuideModal({ opened, onClose, canDismissForever, onDismissForever }: ErdGuideModalProps) {
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="How to draw and submit your ER diagram"
      size={720}
      // Top-anchored, not centred: the steps differ in height, and a centred
      // modal would shift its header (and the Back/Next buttons) on every step.
      withinPortal
      classNames={{ root: BRAND_THEME_CLASS }}
      data-testid="erd-guide-modal"
    >
      <GuideBody
        onClose={onClose}
        canDismissForever={canDismissForever}
        onDismissForever={onDismissForever}
      />
    </Modal>
  );
}
