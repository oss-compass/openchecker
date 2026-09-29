import os
import subprocess
from urllib.parse import urlparse
from typing import List
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
    
    repository_path = os.path.join(os.getcwd(), os.path.splitext(os.path.basename(urlparse(project_url).path))[0])
    if not os.path.isdir(repository_path):
        error = f"Repository directory does not exist: {repository_path}"
        logger.error(error)
        res_payload["scan_results"]["changed-files-since-commit-detector"] = {"error": error}
        return

    # Get different types of changed files
    changed_files = _get_diff_files(commit_hash, "ACDMRTUXB", repository_path)
    new_files = _get_diff_files(commit_hash, "A", repository_path)
    rename_files = _get_diff_files(commit_hash, "R", repository_path)
    deleted_files = _get_diff_files(commit_hash, "D", repository_path)
    modified_files = _get_diff_files(commit_hash, "M", repository_path)

    res_payload["scan_results"]["changed-files-since-commit-detector"] = {
        "changed_files": changed_files,
        "new_files": new_files,
        "rename_files": rename_files,
        "deleted_files": deleted_files,
        "modified_files": modified_files
    }
    
    logger.info(f"changed-files-since-commit-detector job done: {project_url}")


def _get_diff_files(commit_hash: str, type: str = "ACDMRTUXB", repository_path: str = ".") -> List[str]:
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
            ["git", "-C", repository_path, "diff", "--name-only", f"--diff-filter={type}", f"{commit_hash}..HEAD"],
            stderr=subprocess.STDOUT,
            text=True
        )
        return result.strip().split("\n") if result else []
    except subprocess.CalledProcessError as e:
        logger.error(f"failed to get {type} files: {e.output}")
        return [] 