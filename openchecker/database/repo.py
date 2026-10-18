import urllib3
import time
from urllib.parse import urlparse
from elasticsearch import Elasticsearch, RequestsHttpConnection
from logger import get_logger
import time
import urllib3

logger = get_logger('openchecker.database.repo')
urllib3.disable_warnings()


def get_elasticsearch_client(elastic_url):
    """ Get elasticsearch client by url """
    is_https = urlparse(elastic_url).scheme == 'https'
    client = Elasticsearch(
        elastic_url, 
        use_ssl=is_https, 
        verify_certs=False, 
        connection_class=RequestsHttpConnection,
        timeout=100, 
        max_retries=10, 
        retry_on_timeout=True
    )
    return client

client = None


def get_client(url):
    """ Get default client by url """
    global client
    if client is not None:
        return client
    client = get_elasticsearch_client(url)
    return client

def too_many_scrolls(res):
    """Check if result conatins 'too many scroll contexts' error"""
    r = res
    return (
        r
        and 'status' in r
        and 'error' in r
        and 'root_cause' in r['error']
        and len(r['error']['root_cause']) > 0
        and 'reason' in r['error']['root_cause'][0]
        and 'Trying to create too many scroll contexts' in r['error']['root_cause'][0]['reason']
    )

def free_scroll(client, scroll_id=None):
        """ Free scroll after use"""
        if not scroll_id:
            return
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception as e:
            logger.debug("Error releasing scroll: {}", scroll_id)


def get_items(client, index, body, size, scroll_id=None, scroll="10m"):
        page = None
        try:
            if scroll_id is None:
                page = client.search(index=index, body=body, scroll=scroll, size=size)
            else:
                page = client.scroll(scroll_id=scroll_id, scroll=scroll)
        except Exception as e:
            if too_many_scrolls(e.info):
                return {'too_many_scrolls': True}
        return page


def get_generator(client, body, index=None):
        scroll_wait = 900  #wait for 15 minutes
        page_size = body["size"]
        scroll_id = None
        page = get_items(client = client, index=index, body=body, size=page_size, scroll_id=scroll_id)
        if page and 'too_many_scrolls' in page:
            sec = scroll_wait
            while sec > 0:
                logger.debug("Too many scrolls open, waiting up to {} seconds".format(sec))
                time.sleep(1)
                sec -= 1
                page = get_items(index=index, body=body, size=page_size, scroll_id=scroll_id)
                if not page:
                    logger.debug("Waiting for scroll terminated")
                    break
                if 'too_many_scrolls' not in page:
                    logger.debug("Scroll acquired after {} seconds".format(scroll_wait - sec))
                    break

        if not page:
            return []
        
        scroll_id = page["_scroll_id"]
        total = page['hits']['total']
        scroll_size = total['value'] if isinstance(total, dict) else total

        if scroll_size == 0:
            free_scroll(client, scroll_id)
            return []

        while scroll_size > 0:

            for item in page['hits']['hits']:
                yield item
            page = get_items(client=client, index=index, body=body, size=page_size, scroll_id=scroll_id)
            if not page:
                break

            scroll_size = len(page['hits']['hits'])
        free_scroll(client, scroll_id)

def check_repo_china(client, repo):
    repo_tz_index = "github_event_repository_enrich"
    repo_tz_body = {
        "query": {
            "bool": {
                "must": [
                    {
                        "match_phrase": {
                            "tz_detail_list.tz": 8
                        }
                    },
                    {
                        "match_phrase": {
                            "repo.keyword": repo
                        }
                    }
                ]
            }
        },
        "size": 1
    }
    hits = client.search(index=repo_tz_index, body=repo_tz_body)['hits']['hits']
    return len(hits) > 0

if __name__ == '__main__':
    opensearch_url = ""
    repo_index = "github_event_repository"
    
    ''' 
    body = {
        # "_source": ["name", "html_url", "description", "topics", "language"],
        "_source": ["name", "html_url", "description", "topics"],
        "query": {
            "bool": {
                "must": [
                    {
                        "exists": {
                            "field": "topics"
                        }
                    },
                    # {
                    #     "exists": {
                    #         "field": "language"
                    #     }
                    # },
                    {
                        "exists": {
                            "field": "description"
                        }
                    }
                ]
            }
        },
        "size": 10
    }
    repo_generator = get_generator(get_elasticsearch_client(opensearch_url), body, repo_index)
    
    count = 0
    projects = []
    for repo_item in repo_generator:
        count += 1

        project = {
                "name": repo_item["_source"]["name"], 
                "description": repo_item["_source"]["description"],
                "topics": repo_item["_source"]["topics"],
                # "language": repo_item["_source"]["language"],
                "html_url": repo_item["_source"]["html_url"], 
                }

        projects.append(project)

        if count % 10000 == 0:
            file_index = count / 10000
            result_projects_file_path = f"/home/guoqiang/opencheck/test/projects/all_projects_part_{file_index}.json"
            with open(result_projects_file_path, 'w', encoding='utf-8') as f:
                json.dump(projects, f, ensure_ascii=True)
                logger.info("write back to: ", result_projects_file_path)

            projects = []
            
    result_projects_file_path = "/home/guoqiang/opencheck/test/projects/all_projects_part_end.json"
    with open(result_projects_file_path, 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=True)
        logger.info("write back to: ", result_projects_file_path)
    
    '''
    
    
    client = get_elasticsearch_client(opensearch_url)
    repo = "https://github.com/dgrammatiko/wysiwyg-tinymce-j4.1"
    
    print(check_repo_china(client, repo))