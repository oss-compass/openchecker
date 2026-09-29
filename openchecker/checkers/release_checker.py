import re
import requests
import zipfile
import io
import time
from typing import Dict, List, Tuple, Any
from platform_adapter import platform_manager
from logger import get_logger
import os

logger = get_logger('openchecker.checkers.release_checker')


def get_all_releases_with_assets(project_url: str) -> Tuple[List[Dict], str]:
    """
    Get all releases and their assets, supporting github.com, gitee.com and gitcode.com.
    
    Args:
        project_url: Project URL
        
    Returns:
        Tuple[List[Dict], str]: (releases_list, error_message)
    """
    return platform_manager.get_releases(project_url)


def check_release_contents(project_url: str, content_type: str = "notes", check_repo: bool = False) -> Tuple[Dict, str]:
    """
    Check if all release packages of the specified project contain content files of the specified type.

    Function description:
    - Supports GitHub and Gitee platforms.
    - Iterate through all releases, download the archive package (zipball) of each release.
    - Check different types of content according to the type parameter:
        - "notes": Check changelog, releasenotes, release_notes and other files
        - "sbom": Check SBOM files (CDX, SPDX format)
    - Returns whether each release contains the specified content and its filename list.

    Args:
        project_url (str): Repository address of the project, supports GitHub and Gitee.
        content_type (str): Check type, "notes" or "sbom", default is "notes".
        check_repo (bool): Whether to also check repository source code, default is False.

    Returns:
        Tuple[Dict, str]: (result_dict, error)
            result_dict: {
                "is_released": bool,  # Whether there are releases
                "release_contents": [
                    {
                        "tag": version number,
                        "release_name": release name,
                        "has_content": whether there are specified content files,
                        "content_files": filename list,
                        "error": None or error message
                    }, ...
                ]
            }
            error: None or error message string
    """
    try:
        if content_type not in ["notes", "sbom"]:
            return {"is_released": False, "release_contents": []}, f"Unsupported type: {content_type}"
        
        owner_match = re.match(r"https://(?:github|gitee|gitcode).com/([^/]+)/", project_url)
        if not owner_match:
            return {"is_released": False, "release_contents": []}, "Invalid project URL format"
        
        owner_name = owner_match.group(1)
        repo_name = re.sub(r'\.git$', '', os.path.basename(project_url))

        all_releases, error = get_all_releases_with_assets(project_url)
        if error:
            return {"is_released": False, "release_contents": []}, error

        if not all_releases:
            return {"is_released": False, "release_contents": []}, "No releases found"

        file_patterns = _get_file_patterns(content_type)
        
        results = []
        for rel in all_releases:
            if rel.get('draft', False) or rel.get('prerelease', False):
                continue
                
            tag = rel.get("tag_name", "")
            release_name = rel.get("name", tag)
            
            zip_url = _get_zipball_url(project_url, owner_name, repo_name, tag)
            if not zip_url:
                results.append(_create_result_entry(tag, release_name, False, [], "No zipball_url"))
                continue
            
            found_files, error_msg = _check_zip_contents(zip_url, file_patterns)
            results.append(_create_result_entry(tag, release_name, bool(found_files), found_files, error_msg))
            
        return {"is_released": bool(results), "release_contents": results}, None
        
    except Exception as e:
        logger.error(f"Release contents check failed for {project_url}: {e}")
        return {"is_released": False, "release_contents": []}, f"Internal error: {str(e)}"


def check_signed_release(project_url: str) -> Tuple[Dict, str]:
    """
    Check if all release assets contain signature files, supports github.com and gitee.com.
    
    Args:
        project_url: Project URL
        
    Returns:
        Tuple[Dict, str]: (result_dict, error)
            result_dict: {
                'is_released': bool,  # Whether there are releases
                'signed_files': [
                    {
                        'tag': tag,
                        'release_name': release_name,
                        'signature_files': [filename list],
                        'error': None or error message
                    }, ...
                ]
            }
            error: None or error message
    """
    signature_exts = [
        ".minisig", ".asc", ".sig", ".sign", ".sigstore", ".intoto.jsonl"
    ]
    
    all_releases, error = get_all_releases_with_assets(project_url)
    if error:
        return {"is_released": False, "signed_files": []}, error
    
    if not all_releases:
        return {"is_released": False, "signed_files": []}, "No releases found"

    results = []
    for rel in all_releases:
        if rel.get('draft', False) or rel.get('prerelease', False):
            continue
        tag = rel.get("tag_name", "")
        release_name = rel.get("name", tag)
        assets = rel.get("assets", [])
        found_files = [a['name'] for a in assets if any(a['name'].lower().endswith(ext) for ext in signature_exts)]
        results.append({
            "tag": tag,
            "release_name": release_name,
            "signature_files": found_files,
            "error": None
        })
    return {"is_released": bool(results), "signed_files": results}, None


def _get_file_patterns(content_type: str) -> List[str]:
    """
    Get file matching patterns based on content type.
    
    Args:
        content_type (str): Content type, "notes" or "sbom"
        
    Returns:
        list: List of file matching patterns
    """
    if content_type == "notes":
        return [r"(?:changelog|releasenotes|release[_-]?notes|release)(?:\.(?:md|markdown|rst|txt))?"]
    elif content_type == "sbom":
        return [r".+\.(?:cdx\.(?:json|xml)|spdx(?:\.(?:json|xml|ya?ml|rdf(?:\.xml)?))?)"]
    else:
        return []


def _get_zipball_url(project_url: str, owner_name: str, repo_name: str, tag: str) -> str:
    """
    Get zipball download URL.
    
    Args:
        project_url (str): Project URL
        owner_name (str): Owner name
        repo_name (str): Repository name
        tag (str): Tag name
        
    Returns:
        str: zipball URL, returns None if failed to get
    """
    return platform_manager.get_zipball_url(project_url, tag)


def _check_zip_contents(zip_url: str, file_patterns: List[str]) -> Tuple[List[str], str]:
    """
    Check contents in zip file.
    
    Args:
        zip_url (str): zip file download URL
        file_patterns (list): List of file matching patterns
        
    Returns:
        Tuple[List[str], str]: (found_files, error_msg)
            found_files: List of found files
            error_msg: Error message, None if no error
    """
    try:
        response = requests.get(zip_url, timeout=30)
        if response.status_code != 200:
            return [], f"Failed to download release zip: {response.status_code}"
        
        with zipfile.ZipFile(io.BytesIO(response.content), 'r') as zip_ref:
            found_files = []
            for file_name in zip_ref.namelist():
                base_name = os.path.basename(file_name)
                if any(re.fullmatch(pattern, base_name, re.IGNORECASE) for pattern in file_patterns):
                    found_files.append(file_name)
            
            return found_files, None
            
    except requests.exceptions.Timeout:
        return [], "Download timeout"
    except requests.exceptions.RequestException as e:
        return [], f"Download failed: {str(e)}"
    except zipfile.BadZipFile:
        return [], "Invalid zip file"
    except Exception as e:
        return [], f"Failed to check release zip: {str(e)}"


def _create_result_entry(tag: str, release_name: str, has_content: bool, content_files: List[str], error_msg: str) -> Dict:
    """
    Create result entry.
    
    Args:
        tag (str): Tag name
        release_name (str): Release name
        has_content (bool): Whether there is content
        content_files (list): List of content files
        error_msg (str): Error message
        
    Returns:
        dict: Result entry
    """
    return {
        "tag": tag,
        "release_name": release_name,
        "has_content": has_content,
        "content_files": content_files,
        "error": error_msg
    }


def release_checker(project_url: str, res_payload: dict) -> None:
    """
    Release checker - checks release contents and signed releases
    
    Args:
        project_url: Project URL
        res_payload: Response payload
    """
    res_payload["scan_results"]["release-checker"] = {}
    
    # Check release contents (notes and sbom)
    for task in ["notes", "sbom"]:
        content_check_result, error = check_release_contents(project_url, task)
        if error is None:
            logger.info(f"release-checker {task} job done: {project_url}")
            res_payload["scan_results"]["release-checker"][task] = content_check_result
        else:
            logger.error(f"release-checker {task} job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["release-checker"][task] = {"error": error}

    # Check signed release
    signed_release_result, error = check_signed_release(project_url)
    if error is None:
        logger.info(f"signed-release-checker job done: {project_url}")
        res_payload["scan_results"]["release-checker"]["signed-release-checker"] = signed_release_result
    else:
        logger.error(f"signed-release-checker job failed: {project_url}, error: {error}")
        res_payload["scan_results"]["release-checker"]["signed-release-checker"] = {"error": error} 