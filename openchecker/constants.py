def _get_project_name(project_url):
    return f"""project_name=$(basename {project_url} | sed 's/\\.git$//') > /dev/null"""

def _clone_project(project_url, depth=False):
    depth_flag = "--depth=1" if depth else ""
    return f"""if [ ! -e "$project_name" ]; then
    GIT_ASKPASS=/bin/true git clone {depth_flag} {project_url} > /dev/null
fi"""

BASE_SCRIPT = _get_project_name("{project_url}") + "\n" + _clone_project("{project_url}")

download_checkout_shell_script = """
    """ + BASE_SCRIPT + """
    cd "$project_name"

    if [ {version_number} != "None" ]; then
        if git tag | grep -q "^{version_number}$"; then
            git checkout "{version_number}" && \\
            echo "成功切换到标签 {version_number}" || \\
            echo "切换到标签 {version_number} 失败"
        fi
    fi
    """

generate_lock_files_shell_script = """
    """ + BASE_SCRIPT + """
    if [ -e "$project_name/package.json" ] && [ ! -e "$project_name/package-lock.json" ]; then
        cd $project_name && npm install && rm -fr node_modules > /dev/null
        echo "Generate lock files for $project_name with command npm."
    fi
    if [ -e "$project_name/oh-package.json5" ] && [ ! -e "$project_name/oh-package-lock.json5" ]; then
        cd $project_name && ohpm install && rm -fr oh_modules > /dev/null
        echo "Generate lock files for $project_name with command ohpm."
    fi
    """

osv_scanner_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """

    if [ -f "$project_name/oh-package-lock.json5" ] && [ ! -f "$project_name/package-lock.json" ]; then
        mv $project_name/oh-package-lock.json5 $project_name/package-lock.json > /dev/null
        rename_flag=1
    fi

    osv-scanner --format json -r $project_name > $project_name/result.json
    cat $project_name/result.json

    if [ -v rename_flag ]; then
        mv $project_name/package-lock.json $project_name/oh-package-lock.json5 > /dev/null
    fi
    """

scancode_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    scancode -lc --json-pp scan_result.json $project_name --license-score 90 -n 4 > /dev/null
    cat scan_result.json
    rm -rf scan_result.json > /dev/null
    """

sonar_scanner_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    
    if [ ! -d "$project_name" ]; then
        echo "错误: 项目目录不存在: $project_name" >&2
        exit 1
    fi
    
    cd $project_name || {{
        echo "错误: 无法进入项目目录: $project_name" >&2
        exit 1
    }}

    # 排除规则
    EXCLUSIONS="**/node_modules/**,**/target/**,**/build/**,**/dist/**,**/venv/**,**/.venv/**,**/vendor/**,**/bin/**,**/obj/**,**/.git/**,**/coverage/**,**/__pycache__/**"
    
    # 构建SonarQube服务器URL
    case "{sonar_host}" in
        http://*|https://*)
            # Already has protocol
            sonar_url="{sonar_host}"
            ;;
        *)
            # Check if it's an IP address using grep
            if echo "{sonar_host}" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
                # It's an IP address, use http protocol and add port
                if [ -n "{sonar_port}" ] && [ "{sonar_port}" != "None" ]; then
                    sonar_url="http://{sonar_host}:{sonar_port}"
                else
                    sonar_url="http://{sonar_host}"
                fi
            else
                # It's a domain name, use https protocol
                sonar_url="https://{sonar_host}"
            fi
            ;;
    esac
    
    # 扫描结果处理
    handle_scan_result() {{
        scan_type="$1"
        scan_result=$2
        sonar_url="$3"
        
        if [ $scan_result -eq 0 ]; then
            echo "✅ ${{scan_type}}扫描成功"
            echo "📈 查看结果: $sonar_url/dashboard?id={sonar_project_name}"
        elif [ $scan_result -eq 124 ]; then
            echo "⏰ 扫描超时 ({scan_timeout_s}秒)" >&2
            exit 1
        else
            echo "❌ ${{scan_type}}扫描失败 (退出码: $scan_result)" >&2
            exit 1
        fi
    }}
    
    # 项目类型检测
    detect_project_type() {{
        # 优先检测构建工具（Maven/Gradle）
        if [ -f "pom.xml" ]; then
            echo "maven"
            return 0
        elif [ -f "build.gradle" ] || [ -f "build.gradle.kts" ]; then
            echo "gradle"
            return 1
        else
            # 其他类型统一使用通用扫描
            echo "general"
            return 2
        fi
    }}
    
    # 通用扫描
    run_general_scan() {{
        echo "开始通用项目扫描..." >&2
        echo "SonarQube URL: $sonar_url" >&2
        echo "项目名称: {sonar_project_name}" >&2
        
        timeout {scan_timeout_s} sonar-scanner \\
            -Dsonar.host.url="$sonar_url" \\
            -Dsonar.token="{sonar_token}" \\
            -Dsonar.projectKey="{sonar_project_name}" \\
            -Dsonar.projectName="{sonar_project_name}" \\
            -Dsonar.sources="." \\
            -Dsonar.exclusions="$EXCLUSIONS",**/*.java \\
            -Dsonar.scm.disabled=true 2>&1 | tail -n 100 >&2
        
        scan_exit_code=$?
        if [ $scan_exit_code -ne 0 ]; then
            echo "通用扫描命令执行失败，退出码: $scan_exit_code" >&2
        fi
        handle_scan_result "通用" $scan_exit_code "$sonar_url"
    }}
    
    # Maven 扫描
    run_maven_scan() {{
        echo "开始Maven项目扫描..." >&2

        timeout {scan_timeout_s} mvn clean verify sonar:sonar \\
            -Dsonar.host.url="$sonar_url" \\
            -Dsonar.token="{sonar_token}" \\
            -Dsonar.projectKey="{sonar_project_name}" \\
            -Dsonar.projectName="{sonar_project_name}" \\
            -DskipTests 2>&1 | tail -n 50 >&2
        
        scan_exit_code=$?
        handle_scan_result "Maven" $scan_exit_code "$sonar_url"
    }}
    
    # Gradle 扫描
    run_gradle_scan() {{
        echo "开始Gradle项目扫描..." >&2
        chmod +x ./gradlew

        # 检查项目是否配置了 sonarqube 插件
        if ./gradlew tasks --all 2>/dev/null | grep -q "sonarqube"; then
            echo "检测到 SonarQube 插件，使用 Gradle 原生扫描..." >&2
            timeout {scan_timeout_s} ./gradlew sonarqube \\
                -Dsonar.host.url="$sonar_url" \\
                -Dsonar.token="{sonar_token}" \\
                -Dsonar.projectKey="{sonar_project_name}" \\
                -Dsonar.projectName="{sonar_project_name}" 2>&1 | tail -n 50 >&2
            
            scan_exit_code=$?
            handle_scan_result "Gradle" $scan_exit_code "$sonar_url"
        else
            echo "项目未配置 SonarQube 插件，回退到通用扫描..." >&2
            run_general_scan
        fi
    }}
    
    PROJECT_TYPE=$(detect_project_type)
    TYPE_CODE=$?
    echo "✓ 检测到项目类型: $PROJECT_TYPE"
    
    # 根据项目类型选择扫描方式
    case $TYPE_CODE in
        0)  # Maven
            run_maven_scan
            ;;
        1)  # Gradle
            run_gradle_scan
            ;;
        *)  # 其他所有类型（通用扫描）
            run_general_scan
            ;;
    esac
    
    cd ..
    """

dependency_checker_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    ort -P ort.analyzer.allowDynamicVersions=true analyze -i $project_name -o $project_name -f JSON > /dev/null
    cat $project_name/analyzer-result.json
    """

readme_checker_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    find "$project_name" -type f \\( -name "README*" -o -name "docs/README*" \\) -print
    """

maintainers_checker_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    find "$project_name" -type f \\( -iname "MAINTAINERS*" -o -iname "COMMITTERS*" -o -iname "OWNERS*" -o -iname "CODEOWNERS*" \\) -print
    """

languages_detector_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    github-linguist $project_name --breakdown --json
    """

oat_scanner_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """                
    if [ ! -f "$project_name/OAT.xml" ]; then
        echo "OAT.xml not found in the project root directory."
        exit 1   
    fi
    java -jar ohos_ossaudittool-2.0.0.jar -mode s -s $project_name -r $project_name/oat_out -n $project_name > /dev/null            
    report_file="$project_name/oat_out/single/PlainReport_$project_name.txt"
    [ -f "$report_file" ] && cat "$report_file"                        
    """

remove_source_code_shell_script = """
    """ + _get_project_name("{project_url}") + """
    if [ -e "$project_name" ]; then
        rm -rf $project_name > /dev/null
    fi
    """

license_detector_shell_script = """
    """ + _get_project_name("{project_url}") + """
    """ + _clone_project("{project_url}", depth=True) + """
    licensee detect "$project_name" --json
    rm -rf $project_name > /dev/null
    """

shell_script_handlers = {
    "download-checkout": download_checkout_shell_script,
    "generate-lock_files": generate_lock_files_shell_script,
    "osv-scanner": osv_scanner_shell_script,
    "scancode": scancode_shell_script,
    "sonar-scanner": sonar_scanner_shell_script,
    "dependency-checker": dependency_checker_shell_script,
    "readme-checker": readme_checker_shell_script,
    "maintainers-checker": maintainers_checker_shell_script,
    "languages-detector": languages_detector_shell_script,
    "oat-scanner": oat_scanner_shell_script,
    "remove-source-code": remove_source_code_shell_script,
    "license-detector": license_detector_shell_script,
}
