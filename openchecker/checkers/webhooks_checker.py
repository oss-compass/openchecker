import re
import requests
import os
from typing import Any, List, Dict


COMMAND = 'webhooks-checker'


def get_webhooks(project_url, access_token):
    """
    获取所有仓库webhooks, 支持github.com, gitee.com, gitcode.com。
    """

    owner_name = re.match(r"https://(?:github|gitee|gitcode).com/([^/]+)/", project_url).group(1)
    repo_name = re.sub(r'\.git$', '', os.path.basename(project_url))

    if "github.com" in project_url:
        base_url = f"https://api.github.com/repos/{owner_name}/{repo_name}/hooks"
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'Authorization': f'token {access_token}'
        }
        token_query = ""
    elif "gitee.com" in project_url or "gitcode.com" in project_url:
        host = "gitee.com" if "gitee.com" in project_url else "api.gitcode.com"
        base_url = f"https://{host}/api/v5/repos/{owner_name}/{repo_name}/hooks"
        headers = {'Accept': 'application/json'}
        token_query = f"access_token={access_token}&"
    else:
        return [], "Not supported platform."

    hooks = []
    page = 1
    try:
        while True:
            url = f"{base_url}?{token_query}page={page}&per_page=100"
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return [], f"Failed to fetch webhooks: HTTP {response.status_code}"
            page_hooks = response.json()
            if not isinstance(page_hooks, list):
                return [], "Invalid webhook response"
            hooks.extend(page_hooks)
            if len(page_hooks) < 100:
                return hooks, None
            page += 1
    except requests.RequestException as e:
        return [], f"Failed to fetch webhooks: {e}"
    except ValueError:
        return [], "Invalid webhook response"


def webhooks_checker(project_url: str, res_payload: dict, access_token: str) -> None:
    """
    检查项目webhooks,
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#webhooks
    """
    
    webhooks_hooks = []
    error_msg = None
    
    if access_token:
        hooks, error_msg = get_webhooks(project_url, access_token)
        if error_msg is None:
            webhooks_hooks = [
                {**hook, "password": "******"} 
                if hook.get("password") else hook for hook in hooks
            ]
    
    res_payload["scan_results"][COMMAND] = {
        "access_token": True if access_token else False,
        "error_msg": error_msg,
        "webhooks_hooks": webhooks_hooks
    }
