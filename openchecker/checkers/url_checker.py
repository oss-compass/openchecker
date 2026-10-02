import requests
from typing import Dict
from logger import get_logger

logger = get_logger('openchecker.checkers.url_checker')


def url_checker(project_url: str, res_payload: dict) -> None:
    """
    URL accessibility checker
    
    Args:
        project_url: Project URL
        res_payload: Response payload
    """
    try:
        response = requests.get(project_url, timeout=10)
        res_payload["scan_results"]["url-checker"] = {
            "status_code": response.status_code,
            "is_accessible": 200 <= response.status_code < 300
        }
        logger.info(f"url-checker job done: {project_url}")
    except Exception as e:
        logger.error(f"url-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["url-checker"] = {"error": str(e)}
