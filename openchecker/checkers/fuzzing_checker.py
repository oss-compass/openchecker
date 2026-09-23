import os
import glob
import re
import json
from typing import List, Dict, Tuple
from constans import shell_script_handlers
from common import shell_exec
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

# github-linguist（"languages-detector" 处理器调用）使用自己的展示名上报语言，
# 例如 "C++"、"C#"、"JavaScript"、"TypeScript"。这些名字与
# get_language_configs() 返回的小写配置键（如 "cpp"、"javascript"）并不一致，
# 所以在选择语言级模糊测试项之前必须先把 github-linguist 的原始输出归一化。
# 没有对应语言配置的展示名（例如 "C#"、"Shell"、"HTML"）刻意不在此映射表中，
# 会被下面的 _extract_languages() 丢弃。
LINGUIST_LANGUAGE_ALIASES = {
    'c': 'c',
    'c++': 'cpp',
    'cpp': 'cpp',
    'go': 'go',
    'golang': 'go',
    'haskell': 'haskell',
    'java': 'java',
    'javascript': 'javascript',
    'python': 'python',
    'rust': 'rust',
    'typescript': 'typescript',
}


def _extract_languages(shell_output) -> List[str]:
    """将 github-linguist 的输出归一化为语言配置键列表

    "languages-detector" 处理器执行
    ``github-linguist $project_name --breakdown --json``（见 constans.py），
    其 stdout 是一个 JSON 对象：键为 github-linguist 的展示名，值为占比，
    例如 b'{"JavaScript": 70.0, "C++": 30.0}'。而 shell_exec 返回的是
    process.communicate() 的原始字节，未做解码，因此必须先 decode 再
    json.loads：直接遍历 bytes 得到的是 int，这正是过去在这里抛出
    AttributeError: 'int' object has no attribute 'lower' 的原因。

    展示名经由 LINGUIST_LANGUAGE_ALIASES 映射，没有对应语言配置的名字会被
    丢弃；返回值为小写配置键，保持 github-linguist 的输出顺序并去重。

    shell_exec 在处理器失败时返回 None，None 不能直接交给 json.loads。
    凡是不可用的输出（None、b''、非法 JSON、非 UTF-8 字节）都返回空列表，
    由 check_language_fuzzing() 回退为检测全部支持的语言，而不是抛出异常。

    Args:
        shell_output: 语言检测器 handler 的原始 stdout，通常是 bytes；
            失败时为 None。

    Returns:
        小写语言配置键列表；无法使用时返回空列表。
    """
    if not shell_output:
        # shell_exec 在 handler 退出非 0 时返回 None，成功但没有输出时返回
        # b''，两者都表示"没有可用的语言信息"。
        return []

    try:
        if isinstance(shell_output, (bytes, bytearray)):
            # 先解码再解析：bytes 既不是 JSON 也不是文本，遍历 bytes 得到 int。
            decoded = shell_output.decode('utf-8')
        else:
            decoded = str(shell_output)
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, ValueError, TypeError, AttributeError):
        # 非法 JSON、非 UTF-8 字节或意外类型都不能让检查器崩溃，
        # 统一按"没有语言信息"处理。
        return []

    if isinstance(parsed, dict):
        # github-linguist --json 输出以展示名为键的对象，如 {"Go": 100.0}，
        # 只有键携带语言信息。
        names = list(parsed.keys())
    elif isinstance(parsed, list):
        # 同时兼容其他版本返回的纯语言名数组。
        names = parsed
    else:
        # 裸 JSON 数字或字符串不含任何可用的语言信息。
        return []

    known_languages = get_language_configs()
    languages = []
    for name in names:
        if not isinstance(name, str):
            continue
        alias = LINGUIST_LANGUAGE_ALIASES.get(name.strip().lower())
        # 丢弃没有对应配置的语言（如 "C#"、"Shell"），并避免重复上报同一语言。
        if alias in known_languages and alias not in languages:
            languages.append(alias)
    return languages

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
    shell_script = shell_script_handlers["languages-detector"].format(project_url=project_url)
    result, error = shell_exec(shell_script)
    # shell_exec 返回的是 github-linguist stdout 的原始字节，失败时为 None；
    # 由 _extract_languages() 负责解码与归一化。不可用的输出（None、空输出
    # 或非法 JSON）会得到空列表，使下面的 check_language_fuzzing() 回退为
    # 检测全部支持的语言，而不是抛异常。
    languages = _extract_languages(result) if error is None else []
    lang_results = check_language_fuzzing(repo_path, languages)
    all_results.extend(lang_results)
    
    res_payload["scan_results"][COMMAND] = all_results
