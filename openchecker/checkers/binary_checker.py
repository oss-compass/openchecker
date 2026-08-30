import os
from typing import Dict, List, Tuple
from common import shell_exec, get_project_dir_name
from shlex import quote as shell_quote
from logger import get_logger

logger = get_logger('openchecker.checkers.binary_checker')


def binary_checker(project_url: str, res_payload: dict) -> None:
    """
    Binary file checker
    
    Args:
        project_url: Project URL
        res_payload: Response payload
    """
    try:
        file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(file_dir))
        binary_checker_script = os.path.join(project_root, "scripts", "binary_checker.sh")

        # 两个位置参数（$1=URL, $2=目录名）都必须转义：project_url 在此分支
        # 尚未经过 API 层校验，目录名也从 URL 派生
        result, error = shell_exec(
            binary_checker_script,
            f"{shell_quote(project_url)} {shell_quote(get_project_dir_name(project_url))}"
        )
        if error is None:
            logger.info(f"binary-checker job done: {project_url}")
            # Process special output format of binary checker
            result_str = result.decode('utf-8') if result else ""
            data_list = result_str.split('\n')
            binary_file_list = []
            binary_archive_list = []
            for data in data_list[:-1]:
                if "Binary file found:" in data:
                    binary_file_list.append(data.split(": ")[1])
                elif "Binary archive found:" in data:
                    binary_archive_list.append(data.split(": ")[1])
            binary_result = {"binary_file_list": binary_file_list, "binary_archive_list": binary_archive_list}
            res_payload["scan_results"]["binary-checker"] = binary_result
        else:
            logger.error(f"binary-checker job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["binary-checker"] = {"error": error.decode("utf-8")}
    except Exception as e:
        logger.error(f"binary-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["binary-checker"] = {"error": str(e)} 