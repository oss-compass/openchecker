#!/usr/bin/env python3
"""
SBOM检查的Python实现
基于OpenSSF Scorecard的SBOM检查逻辑
"""

import os
import re
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from logger import get_logger

logger = get_logger('openchecker.sbom.sbom_checker')


class FileType(Enum):
    """文件类型枚举"""
    NONE = 0
    SOURCE = 1
    BINARY = 2
    TEXT = 3
    URL = 4
    BINARY_VERIFIED = 5


class Outcome(Enum):
    """检查结果枚举"""
    TRUE = "True"
    FALSE = "False"
    ERROR = "Error"


@dataclass
class Location:
    """位置信息"""
    path: str
    type: FileType
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    snippet: Optional[str] = None


@dataclass
class File:
    """文件信息"""
    path: str
    type: FileType
    offset: int = 0
    end_offset: int = 0
    snippet: str = ""
    file_size: int = 0

    def location(self) -> Location:
        """获取位置信息"""
        return Location(
            path=self.path,
            type=self.type,
            line_start=self.offset if self.offset > 0 else None,
            line_end=self.end_offset if self.end_offset > 0 else None,
            snippet=self.snippet if self.snippet else None
        )


@dataclass
class SBOM:
    """SBOM文件信息"""
    name: str
    file: File


@dataclass
class SBOMData:
    """SBOM数据"""
    sbom_files: List[SBOM] = field(default_factory=list)


@dataclass
class Finding:
    """检查发现"""
    probe: str
    outcome: Outcome
    message: str
    location: Optional[Location] = None
    values: Dict[str, str] = field(default_factory=dict)


@dataclass
class CheckResult:
    """检查结果"""
    name: str
    score: int
    reason: str
    findings: List[Finding] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class Release:
    """发布信息"""
    assets: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class CheckRequest:
    """检查请求"""
    repo_client: Any = None
    logger: Any = None


class SBOMChecker:
    """SBOM检查器"""
    
    def __init__(self):
        # SBOM文件正则表达式
        self.sbom_file_pattern = re.compile(
            r'(?i).+\.(cdx\.json|cdx\.xml|spdx|spdx\.json|spdx\.xml|spdx\.y[a?]ml|spdx\.rdf|spdx\.rdf\.xml)'
        )
        # 根文件正则表达式
        self.root_file_pattern = re.compile(r'^[^.]([^//]*)$')
        # 发布查找回退数量
        self.release_look_back = 5

    def check_sbom(self, request: CheckRequest) -> CheckResult:
        """执行SBOM检查"""
        # 检查实验性功能标志
        if not os.getenv("SCORECARD_EXPERIMENTAL"):
            logger.warning("SCORECARD_EXPERIMENTAL is not set, not running the SBOM check")
            return CheckResult(
                name="SBOM",
                score=0,
                reason="SCORECARD_EXPERIMENTAL is not set, not running the SBOM check",
                error="Unsupported check"
            )

        try:
            # 获取原始数据
            raw_data = self._get_sbom_raw_data(request)
            
            # 运行探针
            findings = self._run_probes(raw_data)
            
            # 评估结果
            result = self._evaluate_sbom("SBOM", findings, request.logger)
            result.findings = findings
            
            return result
            
        except Exception as e:
            logger.exception(f"SBOM check failed: {e}")
            return CheckResult(
                name="SBOM",
                score=0,
                reason=f"Internal error: {e}",
                error="Scorecard internal error"
            )

    def _get_sbom_raw_data(self, request: CheckRequest) -> SBOMData:
        """获取SBOM原始数据"""
        results = SBOMData()
        
        try:
            # 检查发布中的SBOM
            if hasattr(request.repo_client, 'list_releases'):
                releases = request.repo_client.list_releases()
                results.sbom_files.extend(self._check_sbom_releases(releases))
            
            # 检查源码中的SBOM
            if hasattr(request.repo_client, 'list_files'):
                repo_files = request.repo_client.list_files(self._is_sbom_file)
                results.sbom_files.extend(self._check_sbom_source(repo_files))
                
        except Exception as e:
            logger.exception(f"Error getting SBOM raw data: {e}")
            raise
            
        return results

    def _is_sbom_file(self, file_path: str) -> bool:
        """判断是否为SBOM文件"""
        return (self.sbom_file_pattern.match(file_path) and 
                self.root_file_pattern.match(file_path))

    def _check_sbom_releases(self, releases: List[Release]) -> List[SBOM]:
        """检查发布中的SBOM文件"""
        found_sboms = []
        
        for i, release in enumerate(releases):
            if i >= self.release_look_back:
                break
                
            for asset in release.assets:
                if not self.sbom_file_pattern.match(asset.get('name', '')):
                    continue
                    
                found_sboms.append(SBOM(
                    name=asset.get('name', ''),
                    file=File(
                        path=asset.get('url', ''),
                        type=FileType.URL
                    )
                ))
                
                # 每个发布只取一个SBOM
                break
                
        return found_sboms

    def _check_sbom_source(self, file_list: List[str]) -> List[SBOM]:
        """检查源码中的SBOM文件"""
        found_sboms = []
        
        for file_path in file_list:
            found_sboms.append(SBOM(
                name=file_path,
                file=File(
                    path=file_path,
                    type=FileType.SOURCE
                )
            ))
            
        return found_sboms

    def _run_probes(self, raw_data: SBOMData) -> List[Finding]:
        """运行探针"""
        findings = []
        
        # 运行hasSBOM探针
        findings.extend(self._run_has_sbom_probe(raw_data))
        
        # 运行hasReleaseSBOM探针
        findings.extend(self._run_has_release_sbom_probe(raw_data))
        
        return findings

    def _run_has_sbom_probe(self, raw_data: SBOMData) -> List[Finding]:
        """运行hasSBOM探针"""
        findings = []
        
        if not raw_data.sbom_files:
            findings.append(Finding(
                probe="hasSBOM",
                outcome=Outcome.FALSE,
                message="Project does not have a SBOM file"
            ))
        else:
            for sbom in raw_data.sbom_files:
                findings.append(Finding(
                    probe="hasSBOM",
                    outcome=Outcome.TRUE,
                    message="Project has a SBOM file",
                    location=sbom.file.location()
                ))
                
        return findings

    def _run_has_release_sbom_probe(self, raw_data: SBOMData) -> List[Finding]:
        """运行hasReleaseSBOM探针"""
        findings = []
        
        release_sboms = [sbom for sbom in raw_data.sbom_files 
                        if sbom.file.type == FileType.URL]
        
        if not release_sboms:
            findings.append(Finding(
                probe="hasReleaseSBOM",
                outcome=Outcome.FALSE,
                message="Project is not publishing an SBOM file as part of a release or CICD"
            ))
        else:
            for sbom in release_sboms:
                findings.append(Finding(
                    probe="hasReleaseSBOM",
                    outcome=Outcome.TRUE,
                    message="Project publishes an SBOM file as part of a release or CICD",
                    location=sbom.file.location(),
                    values={
                        "assetName": sbom.name,
                        "assetURL": sbom.file.path
                    }
                ))
                
        return findings

    def _evaluate_sbom(self, name: str, findings: List[Finding], logger) -> CheckResult:
        """评估SBOM检查结果"""
        # 验证探针结果
        expected_probes = ["hasSBOM", "hasReleaseSBOM"]
        found_probes = set(finding.probe for finding in findings)
        
        if not all(probe in found_probes for probe in expected_probes):
            return CheckResult(
                name=name,
                score=0,
                reason="Invalid probe results",
                error="Scorecard internal error"
            )

        # 计算分数
        score = 0
        probe_scores = {}
        
        for finding in findings:
            if finding.outcome == Outcome.TRUE:
                if logger:
                    logger.info(finding.message)
                    
                if finding.probe == "hasSBOM" and finding.probe not in probe_scores:
                    score += 5
                    probe_scores[finding.probe] = True
                elif finding.probe == "hasReleaseSBOM" and finding.probe not in probe_scores:
                    score += 5
                    probe_scores[finding.probe] = True
            elif finding.outcome == Outcome.FALSE:
                if logger:
                    logger.warning(finding.message)

        # 检查是否有SBOM文件
        if "hasSBOM" not in probe_scores:
            return CheckResult(
                name=name,
                score=0,
                reason="SBOM file not detected"
            )

        # 检查是否有发布SBOM
        if "hasReleaseSBOM" in probe_scores:
            return CheckResult(
                name=name,
                score=10,
                reason="SBOM file found in release artifacts"
            )

        return CheckResult(
            name=name,
            score=score,
            reason="SBOM file found in project"
        )


# 模拟仓库客户端
class MockRepoClient:
    """模拟仓库客户端"""
    
    def __init__(self, releases=None, files=None):
        self.releases = releases or []
        self.files = files or []
    
    def list_releases(self):
        return self.releases
    
    def list_files(self, predicate):
        return [f for f in self.files if predicate(f)]


def check_sbom_for_project(project_url: str) -> Dict[str, Any]:
    """
    为项目执行SBOM检查
    
    Args:
        project_url: 项目URL
        
    Returns:
        Dict: 包含检查结果的字典
    """
    try:
        # 设置环境变量
        os.environ["SCORECARD_EXPERIMENTAL"] = "true"
        
        # 获取项目名称
        project_name = os.path.basename(project_url).replace('.git', '')
        
        # 检查项目目录是否存在
        if not os.path.exists(project_name):
            logger.error(f"Project directory {project_name} not found")
            return {
                "error": f"Project directory {project_name} not found",
                "status": "failed"
            }
        
        # 查找SBOM文件
        sbom_files = []
        release_sboms = []
        
        # 在项目目录中查找SBOM文件
        for root, dirs, files in os.walk(project_name):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, project_name)
                
                # 检查是否为SBOM文件
                if re.match(r'(?i).+\.(cdx\.json|cdx\.xml|spdx|spdx\.json|spdx\.xml|spdx\.y[a?]ml|spdx\.rdf|spdx\.rdf\.xml)', file):
                    sbom_files.append({
                        "name": relative_path,
                        "path": file_path,
                        "type": "source"
                    })
        
        # 检查发布中的SBOM文件（这里简化处理，实际可能需要调用GitHub API）
        # 在实际实现中，这里应该检查项目的releases
        
        # 创建检查结果
        result = {
            "project_url": project_url,
            "sbom_files": sbom_files,
            "release_sboms": release_sboms,
            "has_sbom": len(sbom_files) > 0,
            "has_release_sbom": len(release_sboms) > 0,
            "score": 0,
            "status": "success"
        }
        
        # 计算分数
        if result["has_sbom"]:
            result["score"] += 5
        if result["has_release_sbom"]:
            result["score"] += 5
            
        return result
        
    except Exception as e:
        logger.exception(f"SBOM check failed for {project_url}: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }
