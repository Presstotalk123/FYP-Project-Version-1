"""Response schema for the cohort-level research export summary
(``GET /admin/export/summary``). The raw-csv endpoint streams text and has no schema.

Dict-typed sections (distributions, matrices, per-concept curves) carry dynamic key sets
driven by scaffolding_engine.LEVELS / solo_classifier.SOLO_LEVELS / concept ids, so they are
typed as open dicts rather than fixed fields.
"""
from typing import Dict, Optional

from pydantic import BaseModel, Field


class SystemScale(BaseModel):
    total_distinct_students: int = Field(..., description="Distinct students, test groups excluded")
    total_lab_sessions: int
    total_submissions: int = Field(..., description="Question attempts + graded lab-task submissions")


class AdaptiveEfficacy(BaseModel):
    scaffolding_level_distribution: Dict[str, int] = Field(
        ..., description="Count of conversations at each scaffolding level (full/guided/minimal/independent)"
    )
    restoration_event_count: int = Field(
        ..., description="Scaffolding changes moving toward more support (e.g. independent->guided)"
    )


class SoloArticulation(BaseModel):
    transition_matrix: Dict[str, Dict[str, int]] = Field(
        ..., description="matrix[from_level][to_level] = count of consecutive-classification transitions"
    )


class AiPerformance(BaseModel):
    fallback_rate: Optional[float] = Field(None, description="Fraction of SOLO classifications using the fallback")
    graceful_degradation_rate: Optional[float] = Field(
        None, description="Fraction with used_fallback OR confidence below threshold"
    )
    total_classifications: int


class ScaffoldingFrictionBucket(BaseModel):
    pass_rate: Optional[float] = Field(None, description="Fraction of (student,question) pairs ever passed")
    avg_attempt_frequency: Optional[float] = Field(None, description="Mean attempts per (student,question) pair")
    sample_size: int = Field(..., description="Number of (student,question) pairs in this bucket")


class ProductiveFriction(BaseModel):
    by_scaffolding_level: Dict[str, ScaffoldingFrictionBucket] = Field(
        ..., description="Pass rate and attempt frequency grouped by current scaffolding level"
    )


class LearningCurves(BaseModel):
    by_concept: Dict[str, Dict[str, float]] = Field(
        ..., description="by_concept[concept_id][opportunity_index] = average error rate"
    )
    max_opportunity_bucketed: int = Field(..., description="Opportunity index cap for the buckets")


class MisconceptionTaxonomy(BaseModel):
    category_counts: Dict[str, int] = Field(
        ..., description="Counts of classified error categories across attempts and lab attempts"
    )


class ResearchExportSummary(BaseModel):
    """Cohort-level aggregate of system usage for research analysis."""
    system_scale: SystemScale
    adaptive_efficacy: AdaptiveEfficacy
    solo_articulation: SoloArticulation
    ai_performance: AiPerformance
    productive_friction: ProductiveFriction
    learning_curves: LearningCurves
    misconception_taxonomy: MisconceptionTaxonomy
