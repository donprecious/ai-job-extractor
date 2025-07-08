import asyncio
from collections import deque
from datetime import datetime
from typing import List, Set, Deque, Optional, Any

from pydantic import BaseModel, Field
import logging
logger = logging.getLogger(__name__)

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class JobInfo(BaseModel):
    title: str
    description: str
    application_info: str
    company: str
    posted_date: Optional[datetime] = None
    source_url: Optional[str] = None


class AgentState(BaseModel):
    # ── static inputs ───────────────────────────────────────
    website: str
    user_job_preference: str
    max_job: int = 5

    # ── rate limiting & error handling ──────────────────────
    delay_between_requests: float = 2.0
    max_retries: int = 3
    max_errors: int = 10

    # ── dynamic / mutable slices ────────────────────────────
    links_to_visit: Deque[str] = Field(default_factory=deque)
    links_visited: Set[str] = Field(default_factory=set)
    jobs_found: List[JobInfo] = Field(default_factory=list)

    # ── tracking fields ──────────────────────────────────────
    current_page_url: Optional[str] = None
    error_count: int = 0
    retry_count: int = 0
    last_request_time: Optional[datetime] = None
    status_message: str = "Initializing..."
    step_count: int = 0

    class Config:
        arbitrary_types_allowed = True

    def model_post_init(self, __context: Any) -> None:
        """Initialize with main website URL"""
        if self.website not in self.links_visited:
            self.links_to_visit.append(self.website)
            logger.info(f"🌐 Added starting website to queue: {self.website}")

    @property
    def jobs_count(self) -> int:
        return len(self.jobs_found)

    @property
    def is_complete(self) -> bool:
        complete = (self.jobs_count >= self.max_job or
                    len(self.links_to_visit) == 0 or
                    self.error_count >= self.max_errors)
        if complete:
            reason = []
            if self.jobs_count >= self.max_job:
                reason.append(f"reached max jobs ({self.jobs_count}/{self.max_job})")
            if len(self.links_to_visit) == 0:
                reason.append("no more links to visit")
            if self.error_count >= self.max_errors:
                reason.append(f"too many errors ({self.error_count}/{self.max_errors})")
            logger.info(f"🏁 Workflow complete: {', '.join(reason)}")
        return complete

    async def rate_limit_delay(self) -> None:
        """Ensure respectful delay between requests"""
        import asyncio
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            if elapsed < self.delay_between_requests:
                wait_time = self.delay_between_requests - elapsed
                logger.debug(f"⏱️ Rate limiting: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
        self.last_request_time = datetime.now()

    def add_job(self, job: JobInfo) -> None:
        """Add job if not duplicate and under limit"""
        if job.source_url not in [j.source_url for j in self.jobs_found]:
            self.jobs_found.append(job)
            logger.info(f"✅ Job added: {job.title} at {job.company}")
        else:
            logger.warning(f"⚠️ Duplicate job skipped: {job.title}")

    def add_links_to_visit(self, links: List[str]) -> None:
        """Add new links to queue, avoiding duplicates"""
        new_count = 0
        for link in links:
            if link not in self.links_visited and link not in self.links_to_visit:
                self.links_to_visit.append(link)
                new_count += 1
        if new_count > 0:
            logger.info(f"🔗 Added {new_count} new links to queue")

    def mark_visited(self, url: str) -> None:
        """Mark URL as visited"""
        self.links_visited.add(url)
        if url in self.links_to_visit:
            temp_deque = deque()
            while self.links_to_visit:
                item = self.links_to_visit.popleft()
                if item != url:
                    temp_deque.append(item)
            self.links_to_visit = temp_deque
        logger.debug(f"✓ Marked as visited: {url}")

    def record_error(self, error: str) -> None:
        """Record an error occurrence"""
        self.error_count += 1
        logger.error(f"❌ Error {self.error_count}/{self.max_errors}: {error}")

    def reset_retry_count(self) -> None:
        """Reset retry counter after successful operation"""
        self.retry_count = 0

    def update_status(self, message: str) -> None:
        """Update current status for streaming"""
        self.step_count += 1
        self.status_message = message
        logger.info(f"📊 Step {self.step_count}: {message}")
        logger.info(
            f"📈 Progress: {self.jobs_count}/{self.max_job} jobs, {len(self.links_to_visit)} links queued, {len(self.links_visited)} visited")


# =============================================================================
# EXTRACTION SCHEMAS
# =============================================================================

class JobExtraction(BaseModel):
    """Schema for extracting job information using structured output"""
    job_title: str = Field(description="The job title or position name")
    company_name: str = Field(description="The name of the hiring company")
    job_description: str = Field(description="Summary of job responsibilities and requirements")
    application_method: Optional[str] = Field(description="How to apply - URL, email, or instructions")
    posted_date: Optional[str] = Field(description="When the job was posted")
    location: Optional[str] = Field(description="Job location")
    employment_type: Optional[str] = Field(description="Full-time, part-time, contract, etc.")
    salary_range: Optional[str] = Field(description="Salary information if available")


class LinkCategorization(BaseModel):
    """Schema for categorizing extracted links"""
    job_detail_links: List[str] = Field(
        description="URLs that lead to individual job posting details",
        default=[]
    )
    job_listing_pages: List[str] = Field(
        description="URLs that contain lists of multiple job postings",
        default=[]
    )
    navigation_links: List[str] = Field(
        description="Pagination or navigation links to more job content",
        default=[]
    )