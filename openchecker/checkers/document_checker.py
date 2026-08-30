import os
import subprocess
import json
from typing import List, Tuple, Any
from common import get_project_dir_name
from exponential_backoff import completion_with_backoff
from logger import get_logger

logger = get_logger('openchecker.checkers.document_checker')


def check_doc_content(project_url: str, doc_type: str) -> Tuple[List[str], str]:
    """
    Check document content for specified type
    
    Args:
        project_url: Project URL
        doc_type: Document type ("api-doc" or "build-doc")
        
    Returns:
        Tuple[List[str], str]: (satisfied_doc_files, error_message)
    """
    project_name = get_project_dir_name(project_url)

    if not os.path.exists(project_name):
        subprocess.run(["git", "clone", project_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    dir_list = [project_name, project_name + '/' + 'doc', project_name + '/' + 'docs']

    def get_documents_in_directory(path):
        documents = []
        if not os.path.exists(path):
            return documents
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isfile(full_path) and item.endswith(('.md', '.markdown')):
                documents.append(full_path)
        return documents

    documents = []
    for dir in dir_list:
        documents.extend(get_documents_in_directory(dir))

    if doc_type == "build-doc":
        do_link_include_check = True
        templates = """
            You are a professional programmer, please assess whether the provided text offers a thorough and in-depth introduction to the processes of software compilation and packaging.
            If the text segment introduce the software compilation and packaging completely, please return 'YES'; otherwise, return 'NO'.
            You need to ensure the accuracy of your answers as much as possible, and if unsure, please simply answer NO. Your response must not include other content.

            Text content as below:

            {text}

        """
    elif doc_type == "api-doc":
        do_link_include_check = False
        templates = """
            You are a professional programmer, please assess whether the provided text offer a comprehensive introduction to the use of software API.
            If the text segment introduce the software API completely, please return 'YES'; otherwise, return 'NO'.
            You need to ensure the accuracy of your answers as much as possible, and if unsure, please simply answer NO. Your response must not include other content.

            Text content as below:

            {text}

        """
    else:
        logger.info("Unsupported type: {}".format(doc_type))
        return [], "Unsupported document type"

    satisfied_doc_file = []
    for document in documents:
        with open(document, 'r') as file:
            markdown_text = file.read()
            chunk_size = 3000
            chunks = [markdown_text[i:i+chunk_size] for i in range(0, len(markdown_text), chunk_size)]

        for _, chunk in enumerate(chunks):
            messages = [
                {
                    "role": "user",
                    "content": templates.format(text=chunk)
                }
            ]

            external_build_doc_link = "https://gitee.com/openharmony-tpc/docs/blob/master/OpenHarmony_har_usage.md"
            if do_link_include_check and external_build_doc_link.lower() in chunk.lower():
                return satisfied_doc_file, None

            result = completion_with_backoff(messages=messages, temperature=0.2)
            if result == "YES":
                satisfied_doc_file.append(document)
                return satisfied_doc_file, None
    return satisfied_doc_file, None


def check_readme_opensource(project_url: str) -> Tuple[bool, str]:
    """
    Check if README.OpenSource file exists and is properly formatted
    
    Args:
        project_url: Project URL
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    project_name = get_project_dir_name(project_url)

    if not os.path.exists(project_name):
        subprocess.run(["git", "clone", project_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    readme_file = os.path.join(project_name, "README.OpenSource")
    if os.path.isfile(readme_file):
        with open(readme_file, 'r', encoding='utf-8') as file:
            try:
                content = json.load(file)

                if isinstance(content, list):
                    required_keys = [
                        "Name", "License", "License File",
                        "Version Number", "Owner", "Upstream URL", "Description"
                    ]

                    all_entries_valid = True
                    for entry in content:
                        if not isinstance(entry, dict) or not all(key in entry for key in required_keys):
                            all_entries_valid = False
                            break

                    if all_entries_valid:
                        return True, None
                    else:
                        return False, "The README.OpenSource file exists and is not properly formatted."

            except json.JSONDecodeError:
                return False, "README.OpenSource is not properly formatted."
    else:
        return False, "README.OpenSource does not exist."


def api_doc_checker(project_url: str, res_payload: dict) -> None:
    """
    API document checker
    
    Args:
        project_url: Project URL
        res_payload: Response payload
    """
    try:
        result, error = check_doc_content(project_url, "api-doc")
        if error is None:
            logger.info(f"api-doc-checker job done: {project_url}")
            res_payload["scan_results"]["api-doc-checker"] = result
        else:
            logger.error(f"api-doc-checker job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["api-doc-checker"] = {"error": error}
    except Exception as e:
        logger.error(f"api-doc-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["api-doc-checker"] = {"error": str(e)}


def build_doc_checker(project_url: str, res_payload: dict) -> None:
    """
    Build document checker
    
    Args:
        project_url: Project URL
        res_payload: Response payload
    """
    try:
        result, error = check_doc_content(project_url, "build-doc")
        if error is None:
            logger.info(f"build-doc-checker job done: {project_url}")
            res_payload["scan_results"]["build-doc-checker"] = {"build-doc-checker": result} if result else {}
        else:
            logger.error(f"build-doc-checker job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["build-doc-checker"] = {"error": error}
    except Exception as e:
        logger.error(f"build-doc-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["build-doc-checker"] = {"error": str(e)}


def readme_opensource_checker(project_url: str, res_payload: dict) -> None:
    """
    README.OpenSource checker
    
    Args:
        project_url: Project URL
        res_payload: Response payload
    """
    try:
        result, error = check_readme_opensource(project_url)
        if error is None:
            logger.info(f"readme-opensource-checker job done: {project_url}")
            res_payload["scan_results"]["readme-opensource-checker"] = {"readme-opensource-checker": result} if result else {}
        else:
            logger.error(f"readme-opensource-checker job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["readme-opensource-checker"] = {"error": error}
    except Exception as e:
        logger.error(f"readme-opensource-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["readme-opensource-checker"] = {"error": str(e)} 