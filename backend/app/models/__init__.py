"""Model registry — import all models here so Alembic can discover them."""

from app.models.ai_call_log import AICallLog, AICallType
from app.models.audit_log import AuditLog
from app.models.certification import Certification
from app.models.job_analysis import JobAnalysis, MatchedRequirement, MatchType, MissingRequirement
from app.models.job_description import JobDescription
from app.models.profile import Profile
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.resume import EvidenceLink, Resume, ResumeBullet, ResumeVersion
from app.models.skill import Skill
from app.models.uploaded_file import FileStatus, UploadedFile
from app.models.user import User, UserTier
from app.models.work_experience import WorkExperience

__all__ = [
    "User",
    "UserTier",
    "Profile",
    "RefreshToken",
    "WorkExperience",
    "Project",
    "Skill",
    "Certification",
    "UploadedFile",
    "FileStatus",
    "JobDescription",
    "JobAnalysis",
    "MatchedRequirement",
    "MissingRequirement",
    "MatchType",
    "Resume",
    "ResumeVersion",
    "ResumeBullet",
    "EvidenceLink",
    "AICallLog",
    "AICallType",
    "AuditLog",
]
