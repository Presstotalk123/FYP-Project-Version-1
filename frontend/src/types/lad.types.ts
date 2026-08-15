// Types for the Learning Analytics Dashboard (LAD).

export type MasteryBand = 'untouched' | 'novice' | 'developing' | 'proficient' | 'mastered';
export type ScaffoldingLevel = 'full' | 'guided' | 'minimal' | 'independent';

export interface ConceptNode {
  id: number;
  slug: string;
  display_name: string;
  category: string;
  mastery_level: number | null;
  mastery_band: MasteryBand;
}

export interface ConceptEdge {
  from: number; // prerequisite concept id
  to: number;   // dependent concept id
}

export interface ConceptGraph {
  nodes: ConceptNode[];
  edges: ConceptEdge[];
}

export interface PeerBenchmarkEntry {
  concept_id: number;
  avg_mastery: number;
}

export interface PeerBenchmark {
  suppressed: boolean;
  reason: string | null;
  averages: PeerBenchmarkEntry[];
  cohort_size: number;
}

export interface ScaffoldingState {
  question_id: number;
  scaffolding_level: ScaffoldingLevel;
  levels: ScaffoldingLevel[];
}

// Concept taxonomy + question tagging (staff)
export interface Concept {
  id: number;
  slug: string;
  display_name: string;
  category: string;
}

export interface QuestionConceptTag {
  concept_id: number;
  weight: number;
}
