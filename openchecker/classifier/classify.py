from llm import ChatCompletionHandler
import yaml
import json
from repo import get_generator, get_elasticsearch_client
import re
import sys

def replace_single_quotes_with_regex(s):
    return re.sub(r"'", '"', s)

def extract_second_level_categories(yaml_file_path):
    categories = {}

    with open(yaml_file_path, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)

    for category in data:
        categories[category["name"]] = category['items']

    return categories


if __name__ == "__main__":
    
    if len(sys.argv) < 2:
        print("请提供至少一个参数。")
        sys.exit(1)

    # 读取参数
    input_param = sys.argv[1]
    print(f"传入的参数是: {input_param}")
    
    yaml_file_path = "/home/guoqiang/opencheck/test/collections.yml"
    categories = extract_second_level_categories(yaml_file_path)
    # part_categories = [ {"Operation System": categories["Operation System"]}, {"Database": categories["Database"]}]
    
    source_projects_file_path = f"/home/guoqiang/opencheck/test/projects/all_projects_part_{input_param}.json"
    result_projects_file_path = f"/home/guoqiang/opencheck/test/projects_result/all_projects_part_{input_param}.json"

    few_shot_examples = """例如有如下项目信息：
        "name"："PostgreSQL"
        "description"："是一款功能强大、特性丰富的开源关系型数据库管理系统。"
        "language"："C"
        "topics"：["Data Modeling", "SQL", "Data Storage"]
        按照要求，模型的输出应该如下：
        {
            "project_name": "PostgreSQL",
            "assigned_first_level_category": "Database",
            "assigned_second_level_category": "sql-database",
        }
        """

    project_schema = """{
            "project_name": "具体项目名称",
            "assigned_first_level_category": "划分到的一级类别名称",
            "assigned_second_level_category": "划分到的二级类别名称(是一级分类的细分领域)",
            }"""

    system_message = {
        "role": "system",
        "content": f"""你是一个专业的软件项目分类助手，能够根据输入的软件项目的信息和给定的二级分类列表，准确地将项目划分到合适的技术类别中。你要尽可能保证分类的准确性,并优先使用给定类别，当给定类别不合适时允许新建分类。每个项目必须给出分类。请严格按照以下格式输出结果，以方便后续的解析处理：
            {project_schema}

            给定的一级分类及二级分类信息及对应关系如下：
            {categories}
            """
    }

    projects = []
    with open(source_projects_file_path, 'r', encoding='utf-8') as f:
        projects = json.load(f)
    
    count = 0 
    result_projects = []
    
    for project in projects:
        count += 1
        project_m = {
                "name": project["name"], 
                "description": project["description"],
                }

        user_message = {
            "role": "user", 
            "content": """以下是需要进行分类的开源项目的详细信息：
            {}
            """.format(project_m)
        }

        messages = [system_message, user_message]
        
        llm = ChatCompletionHandler(model_name="ep-20241129094859-p47sh", base_url=f"https://ark.cn-beijing.volces.com/api/v3/")
        try:
            llm_result = json.loads(replace_single_quotes_with_regex(llm.non_streaming_chat(messages)))
            first_category, second_category =llm_result['assigned_first_level_category'] , llm_result['assigned_second_level_category']
        except Exception as e:
            print("Failed to category: ", project['name'], e)
            print(llm_result)
            first_category, second_category = '', ''
            
        project["assigned_first_level_category"] = first_category
        project['assigned_second_level_category'] = second_category
        
        result_projects.append(project)

        if count == 100:
            with open(result_projects_file_path, 'w', encoding='utf-8') as f:
                json.dump(result_projects, f, ensure_ascii=True)
            
            count = 0
            print("write back to json file.")
