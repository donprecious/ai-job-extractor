import asyncio

from langgraph.constants import END
from langgraph.graph import StateGraph

from agents.job_info_extractor_agent import job_info_extractor_agent
from agents.job_link_extractor_agent import job_link_extractor_agent
from model.models import AgentState
from util import is_job_detail_url
from dotenv import load_dotenv
import logging
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('job_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def route_decision_node(state: AgentState) -> AgentState:
    """Simple pass-through node for routing logic"""
    return state


def decide_next_action(state: AgentState) -> str:
    """Decide what to do next based on current state"""
    logger.info(f"🤔 Decision node - Jobs: {state.jobs_count}/{state.max_job}, Links: {len(state.links_to_visit)}, Complete: {state.is_complete}")

    if state.is_complete:
        return "complete"

    # If we have job detail links to process, extract job info
    if state.links_to_visit:
        # Check if any of the next few links are job detail URLs
        temp_queue = list(state.links_to_visit)[:5]  # Check first 5 links
        if any(is_job_detail_url(url) for url in temp_queue):
            return "extract_job_info"

    # If we have any links, try to find more job links
    if state.links_to_visit:
        return "find_more_links"

    # No more links to process
    return "complete"


def create_job_scraper_graph():
    """Create the LangGraph workflow for job scraping"""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("job_link_extractor", job_link_extractor_agent)
    workflow.add_node("job_info_extractor", job_info_extractor_agent)
    workflow.add_node("route_decision", route_decision_node)

    # Define entry point
    workflow.set_entry_point("job_link_extractor")

    # Define edges
    workflow.add_edge("job_link_extractor", "route_decision")
    workflow.add_edge("job_info_extractor", "route_decision")

    # Conditional edges from route_decision
    workflow.add_conditional_edges(
        "route_decision",
        decide_next_action,
        {
            "extract_job_info": "job_info_extractor",
            "find_more_links": "job_link_extractor",
            "complete": END
        }
    )

    return workflow.compile()


async def stream_job_scraper(website: str, user_job_preference: str, max_jobs: int = 5):
    """
    Stream the job scraper execution with real-time updates

    Args:
        website: Starting website URL
        user_job_preference: Natural language job preference
        max_jobs: Maximum number of jobs to collect
    """
    # Initialize state
    initial_state = AgentState(
        website=website,
        user_job_preference=user_job_preference,
        max_job=max_jobs
    )

    # Create the graph
    graph = create_job_scraper_graph()

    logger.info("🚀 Starting streaming job scraper...")
    logger.info(f"🎯 Target: {user_job_preference}")
    logger.info(f"🌐 Website: {website}")
    logger.info(f"📊 Max jobs: {max_jobs}")
    logger.info("=" * 80)

    try:
        # Stream the workflow execution
        async for event in graph.astream(initial_state):

            # Extract node name and state from event
            node_name = list(event.keys())[0] if event else "unknown"
            current_state = list(event.values())[0] if event else None

            if current_state:
                # Stream update with current status
                print(f"\n ✅ state: {current_state}")

                # Add delay for better readability
                #await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"❌ Streaming error: {str(e)}")
        print(f"\n❌ ERROR: {str(e)}")
        return []


