"""API v1 router — aggregates all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    certifications,
    files,
    health,
    jobs,
    profile,
    projects,
    resumes,
    skills,
    work_experience,
)

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(profile.router, prefix="/profile", tags=["profile"])
router.include_router(work_experience.router, prefix="/profile/experience", tags=["experience"])
router.include_router(projects.router, prefix="/profile/projects", tags=["projects"])
router.include_router(skills.router, prefix="/profile/skills", tags=["skills"])
router.include_router(certifications.router, prefix="/profile/certifications", tags=["certifications"])
router.include_router(files.router, prefix="/files", tags=["files"])
router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
