
import requests
import json
from pathlib import Path
from typing import Any, List, Dict


COMMAND = 'bestpractices-checker'

def bestpractices_checker(project_url: str, res_payload: dict) -> None:
    """
    获取项目的OpenSSF Best Pactices,
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#cii-best-practices
    """
    api_url = "https://www.bestpractices.dev/projects.json"
    try:
        response = requests.get(api_url, params={"url": project_url}, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data and len(data) > 0:
            res_payload["scan_results"][COMMAND] = data[0]
        else:
            res_payload["scan_results"][COMMAND] = {}
    except Exception as e:
        res_payload["scan_results"][COMMAND] = {}
