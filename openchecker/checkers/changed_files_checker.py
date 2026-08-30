import os
import subprocess
from urllib.parse import urlparse
from typing import List
from common import get_project_dir_name
from logger import get_logger

logger = get_logger('openchecker.checkers.changed_files_checker')


def changed_files_detector(project_url: str, res_payload: dict, commit_hash: str) -> None:
    """
    Changed files detector
    
    Args:
        project_url: Project URL
        res_payload: Response payload
        commit_hash: Commit hash
    """
    if not commit_hash:
        logger.error("changed-files-since-commit-detector job failed: fail to get commit hash!")
        res_payload["scan_results"]["changed-files-since-commit-detector"] = {"error": "No commit hash provided"}
        return
    
    context_path = os.getcwd()
    try:
        repository_path = os.path.join(context_path, get_project_dir_name(project_url))
        os.chdir(repository_path)
        logger.info(f"change os path to git repository directory: {repository_path}")
    except OSError as e:
        logger.error(f"failed to change os path to git repository directory: {e}")
        res_payload["scan_results"]["changed-files-since-commit-detector"] = {"error": str(e)}
        return

    # Get different types of changed files
    changed_files = _get_diff_files(commit_hash, "ACDMRTUXB")
    new_files = _get_diff_files(commit_hash, "A")
    rename_files = _get_diff_files(commit_hash, "R")
    deleted_files = _get_diff_files(commit_hash, "D")
    modified_files = _get_diff_files(commit_hash, "M")

    os.chdir(context_path)

    res_payload["scan_results"]["changed-files-since-commit-detector"] = {
        "changed_files": changed_files,
        "new_files": new_files,
        "rename_files": rename_files,
        "deleted_files": deleted_files,
        "modified_files": modified_files
    }
    
    logger.info(f"changed-files-since-commit-detector job done: {project_url}")


def _get_diff_files(commit_hash: str, type: str = "ACDMRTUXB") -> List[str]:
    """
    Get changed files of specified type
    
    Args:
        commit_hash (str): Commit hash
        type (str): Change type, can be: [(A|C|D|M|R|T|U|X|B)…​[*]]
            Added (A), Copied (C), Deleted (D), Modified (M), Renamed (R),
            have their type changed (T), are Unmerged (U), are Unknown (X), 
            or have had their pairing Broken (B).
            
    Returns:
        list: Changed files list
    """
    try:
        result = subprocess.check_output(
            ["git", "diff", "--name-only", f"--diff-filter={type}", f"{commit_hash}..HEAD"],
            stderr=subprocess.STDOUT,
            text=True
        )
        return result.strip().split("\n") if result else []
    except subprocess.CalledProcessError as e:
        logger.error(f"failed to get {type} files: {e.output}")
        return [] 