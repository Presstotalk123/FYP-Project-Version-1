from app.models.user import User, UserRole
from app.models.question import Question, Difficulty
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.attempt import Attempt
from app.models.progress import UserProgress
from app.models.lab import Lab
from app.models.lab_session import LabSession
from app.models.lab_attempt import LabAttempt
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_class_window import AssessmentClassWindow
from app.models.assessment_analytics import AssessmentAnalytics
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.erd_tutor_message import ErdTutorMessage
from app.models.erd_prompt_version import ErdPromptVersion
from app.models.er_submission import ErSubmission  # noqa: F401
from app.models.tutor_chat_conversation import TutorChatConversation
from app.models.tutor_chat_message import TutorChatMessage
from app.models.query_review import QueryReview
from app.models.login_activity import LoginActivity
# Akela multi-agent / learning-analytics models
from app.models.sql_concept import SqlConcept
from app.models.sql_concept_prerequisite import SqlConceptPrerequisite
from app.models.question_concept import QuestionConcept
from app.models.learning_event import LearningEvent
from app.models.concept_mastery import ConceptMastery
from app.models.solo_classification import SoloClassification
from app.models.sql_tutor_conversation import SqlTutorConversation
from app.models.sql_tutor_message import SqlTutorMessage
from app.models.user_preference import UserPreference

__all__ = ["User", "UserRole", "Question", "Difficulty", "ERDiagramQuestion", "Attempt", "UserProgress", "Lab", "LabSession", "LabAttempt", "LabTask", "LabTaskSubmission", "Assessment", "AssessmentItem", "AssessmentClassWindow", "ErdTutorConversation", "ErdTutorMessage", "ErdPromptVersion", "TutorChatConversation", "TutorChatMessage", "QueryReview", "LoginActivity", "SqlConcept", "SqlConceptPrerequisite", "QuestionConcept", "LearningEvent", "ConceptMastery", "SoloClassification", "SqlTutorConversation", "SqlTutorMessage", "UserPreference"]
