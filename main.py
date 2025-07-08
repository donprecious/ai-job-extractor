# =============================================================================
# MAIN EXECUTION
# =============================================================================
import asyncio

from graph import create_job_scraper_graph, stream_job_scraper
from model.models import AgentState
import logging

from util import setup_logging, validate_environment

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('job_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def run_job_scraper(website: str, user_job_preference: str, max_jobs: int = 5, stream: bool = True):
    """
    Main function to run the job scraper with optional streaming

    Args:
        website: Starting website URL
        user_job_preference: Natural language job preference
        max_jobs: Maximum number of jobs to collect
        stream: Whether to stream real-time updates
    """
    if stream:
        return await stream_job_scraper(website, user_job_preference, max_jobs)
    else:
        # Non-streaming version (original)
        initial_state = AgentState(
            website=website,
            user_job_preference=user_job_preference,
            max_job=max_jobs
        )

        graph = create_job_scraper_graph()

        logger.info(f"🚀 Starting job scraper for: {user_job_preference}")
        logger.info(f"🌐 Target website: {website}")
        logger.info(f"🎯 Max jobs to find: {max_jobs}")
        logger.info("-" * 60)

        try:
            final_state = await graph.ainvoke(initial_state)

            logger.info("-" * 60)
            logger.info(f"✅ Scraping completed!")
            logger.info(f"📊 Jobs found: {len(final_state.jobs_found)}")
            logger.info(f"🔗 Pages visited: {len(final_state.links_visited)}")
            logger.info(f"❌ Errors encountered: {final_state.error_count}")

            return final_state.jobs_found

        except Exception as e:
            logger.error(f"❌ Error running job scraper: {str(e)}")
            return []


# Example usage
if __name__ == "__main__":
    # Example run
    try:
        setup_logging()
        validate_environment()
        jobs = asyncio.run(run_job_scraper(
            website="https://weworkremotely.com/",
            user_job_preference="I want a remote Python developer position focusing on machine learning or data science",
            max_jobs=5
        ))
    except Exception as e:
        logger.error(f"❌ Error running job scraper: {str(e)}")
