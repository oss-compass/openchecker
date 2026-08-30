import os
import glob
import re
from typing import List, Dict, Tuple
from constans import shell_script_handlers
from common import shell_exec
from shlex import quote as shell_quote
from platform_adapter import platform_manager

COMMAND = 'fuzzing-checker'


# 模糊测试工具常量
FUZZING_TOOLS = {
    'CLUSTERFUZZ_LITE': 'ClusterFuzzLite',
    'OSS_FUZZ': 'OSS-Fuzz',
    'GO_NATIVE': 'GO NATIVE',
    'PYTHON_ATHERIS': 'Python Atheris',
    'C_LIBFUZZER': 'C LibFuzzer',
    'CPP_LIBFUZZER': 'C++ LibFuzzer',
    'RUST_CARGO_FUZZ': 'Rust Cargo-fuzz',
    'JAVA_JAZZER': 'Java Jazzer',
    'JS_FAST_CHECK': 'JavaScript fast-check',
    'TS_FAST_CHECK': 'TypeScript fast-check',
    'HASKELL_QUICKCHECK': 'Haskell QuickCheck'
}

def create_fuzzing_result(tool_name: str, found: bool, files: List[str] = None, description: str = "") -> Dict:
    """创建模糊测试结果字典"""
    return {
        'tool': tool_name,
        'found': found,
        'files': files or [],
        'description': description
    }
    

def create_language_config(file_patterns: List[str], func_pattern: str, tool_name: str, description: str) -> Dict:
    """创建语言配置字典"""
    return {
        'file_patterns': file_patterns,
        'func_pattern': func_pattern,
        'tool': tool_name,
        'description': description
    }

    
def get_language_configs() -> Dict[str, Dict]:
    """获取语言特定的模糊测试配置"""
    return {
        'go': create_language_config(
            ['*_test.go'],
            r'func\s+Fuzz\w+\s*\(\w+\s+\*testing\.F\)',
            FUZZING_TOOLS['GO_NATIVE'],
            'Go fuzzing intelligently walks through the source code to report failures and find vulnerabilities.'
        ),
        'python': create_language_config(
            ['*.py'],
            r'import atheris',
            FUZZING_TOOLS['PYTHON_ATHERIS'],
            'Python fuzzing by way of Atheris'
        ),
        'c': create_language_config(
            ['*.c'],
            r'LLVMFuzzerTestOneInput',
            FUZZING_TOOLS['C_LIBFUZZER'],
            'Fuzzed with C LibFuzzer'
        ),
        'cpp': create_language_config(
            ['*.cc', '*.cpp'],
            r'LLVMFuzzerTestOneInput',
            FUZZING_TOOLS['CPP_LIBFUZZER'],
            'Fuzzed with C++ LibFuzzer'
        ),
        'rust': create_language_config(
            ['*.rs'],
            r'libfuzzer_sys',
            FUZZING_TOOLS['RUST_CARGO_FUZZ'],
            'Fuzzed with Cargo-fuzz'
        ),
        'java': create_language_config(
            ['*.java'],
            r'com\.code_intelligence\.jazzer\.api\.FuzzedDataProvider;',
            FUZZING_TOOLS['JAVA_JAZZER'],
            'Fuzzed with Jazzer fuzzer'
        ),
        'javascript': create_language_config(
            ['*.js'],
            r'(from\s+[\"\'](fast-check|@fast-check/(ava|jest|vitest))[\"\']+|require\(\s*[\"\'](fast-check|@fast-check/(ava|jest|vitest))[\"\']\s*\))',
            FUZZING_TOOLS['JS_FAST_CHECK'],
            'JavaScript property-based testing with fast-check'
        ),
        'typescript': create_language_config(
            ['*.ts'],
            r'(from\s+[\"\'](fast-check|@fast-check/(ava|jest|vitest))[\"\']+|require\(\s*[\"\'](fast-check|@fast-check/(ava|jest|vitest))[\"\']\s*\))',
            FUZZING_TOOLS['TS_FAST_CHECK'],
            'TypeScript property-based testing with fast-check'
        ),
        'haskell': create_language_config(
            ['*.hs', '*.lhs'],
            r'import\s+(qualified\s+)?Test\.((Hspec|Tasty)\.)?(QuickCheck|Hedgehog|Validity|SmallCheck)',
            FUZZING_TOOLS['HASKELL_QUICKCHECK'],
            'Haskell property-based testing'
        )
    }

    
    
def check_clusterfuzz_lite(repo_path: str) -> Dict:
    """检测 ClusterFuzzLite 配置"""
    dockerfile_path = os.path.join(repo_path, '.clusterfuzzlite', 'Dockerfile')
    
    if os.path.exists(dockerfile_path):
        try:
            with open(dockerfile_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 检查是否包含命令（以#开头的注释不算）
                if content.strip() and not content.strip().startswith('#'):
                    return create_fuzzing_result(
                        FUZZING_TOOLS['CLUSTERFUZZ_LITE'],
                        True,
                        [dockerfile_path],
                        'continuous fuzzing solution that runs as part of Continuous Integration (CI) workflows'
                    )
        except Exception as e:
            pass
    
    return create_fuzzing_result(FUZZING_TOOLS['CLUSTERFUZZ_LITE'], False)
    

def check_language_fuzzing(repo_path: str, languages: List[str] = None) -> List[Dict]:
    """检测语言特定的模糊测试"""
    language_configs = get_language_configs()
    results = []
    
    if not languages:
        # 如果没有指定语言，检测所有支持的语言
        languages = list(language_configs.keys())
    
    for lang in languages:
        if lang in language_configs:
            config = language_configs[lang]
            result = check_single_language_fuzzing(repo_path, lang, config)
            results.append(result)
    
    return results 


def check_single_language_fuzzing(repo_path: str, language: str, config: Dict) -> Dict:
    """检测单个语言的模糊测试"""
    found_files = []
    
    # 搜索匹配的文件
    matching_files = find_files_with_pattern(repo_path, config['file_patterns'])
    
    # 检查文件内容
    for file_path in matching_files:
        if check_file_content(file_path, config['func_pattern']):
            found_files.append(file_path)
    
    return create_fuzzing_result(
        config['tool'],
        len(found_files) > 0,
        found_files,
        config['description']
    )
    

def find_files_with_pattern(repo_path: str, file_patterns: List[str]) -> List[str]:
    """根据文件模式查找文件"""
    found_files = []
    for pattern in file_patterns:
        file_pattern = os.path.join(repo_path, '**', pattern)
        matching_files = glob.glob(file_pattern, recursive=True)
        found_files.extend(matching_files)
    return found_files


def check_file_content(file_path: str, func_pattern: str) -> bool:
    """检查文件内容是否包含指定模式"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            return bool(re.search(func_pattern, content))
    except Exception as e:
        return False
    
    

def fuzzing_checker(project_url: str, res_payload: dict) -> None:
    """
    执行模糊测试检查
    指标详情介绍 https://github.com/ossf/scorecard/blob/main/docs/checks.md#fuzzing
    """
    
    all_results = []
    owner_name, repo_path = platform_manager.parse_project_url(project_url)
    
    # 检测 ClusterFuzzLite
    cfl_result = check_clusterfuzz_lite(repo_path)
    all_results.append(cfl_result)
    
    # 检测语言特定的模糊测试
    shell_script = shell_script_handlers["languages-detector"].format(project_url=shell_quote(project_url))
    result, error = shell_exec(shell_script)
    if error is None:
        languages = result
    else:
        languages = []
    languages = [lang.lower() for lang in languages]
    lang_results = check_language_fuzzing(repo_path, languages)
    all_results.extend(lang_results)
    
    res_payload["scan_results"][COMMAND] = all_results
