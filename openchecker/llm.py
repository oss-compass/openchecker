from transformers import AutoTokenizer, AutoModel
import torch
import openai, time, random
from openai import OpenAI
import os

def retry_with_exponential_backoff(
    func,
    initial_delay: float = 2,
    exponential_base: float = 2,
    jitter: bool = False,
    max_retries: int = 10,
    errors: tuple = (openai.RateLimitError, openai.APIError, openai.Timeout, openai.APIConnectionError, openai.InternalServerError),
):
    """Retry a function with exponential backoff."""
 
    def wrapper(*args, **kwargs):
        # Initialize variables
        num_retries = 0
        delay = initial_delay
 
        # Loop until a successful response or max_retries is hit or an exception is raised
        while True:
            try:
                return func(*args, **kwargs)
 
            # Retry on specific errors
            except Exception as e:
                # Increment retries
                num_retries += 1
 
                # Check if max retries has been reached
                if num_retries > max_retries:
                    raise Exception(
                        f"Maximum number of retries ({max_retries}) exceeded."
                    ) from e
 
                # Increment the delay
                delay *= exponential_base
 
                # Sleep for the delay
                print("sleep: ", delay, " s")
                time.sleep(delay)
 
            # # Raise exceptions for any errors not specified
            # except Exception as e:
            #     print(e)
 
    return wrapper

class SentenceEmbeddingGenerator:
    def __init__(self, model_path):
        """
        初始化函数，用于加载模型和分词器。

        Args:
            model_path (str): 预训练模型的路径。
        """
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModel.from_pretrained(model_path)
        self.model.eval()

    def generate_embeddings(self, sentences):
        """
        生成句子嵌入的函数。

        Args:
            sentences (list): 要生成嵌入的句子列表。

        Returns:
            torch.Tensor: 句子嵌入的张量。
        """
        encoded_input = self.tokenizer(sentences, padding=True, truncation=True, return_tensors='pt')

        with torch.no_grad():
            model_output = self.model(**encoded_input)
            sentence_embeddings = model_output[0][:, 0]

        sentence_embeddings = torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)

        return sentence_embeddings

class ChatCompletionHandler:
    def __init__(self, model_name = "gpt3.5-turbo", base_url = f"https://api.openai.com/v1"):
        if "openai.com" in base_url:
            api_key = os.environ.get("OPENAI_API_KEY")
        elif "ark.cn" in base_url:
            api_key = os.environ.get("ARK_API_KEY")
        else:
            api_key = None

        self.client = OpenAI(
            api_key=api_key,
            base_url= base_url
        )
        self.model = model_name

    @retry_with_exponential_backoff
    def non_streaming_chat(self, messages):
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        return completion.choices[0].message.content

    def streaming_chat(self, messages):
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True
        )

        # result = ""
        # for chunk in stream:
        #     if not chunk.choices:
        #         continue
        #     result += chunk.choices[0].delta.content
        # return result
        return stream

if __name__ == "__main__":
    model_path = '/home/guoqiang/models/bge-large-en-v1.5'
    sentences = ["sample-data-1", "sample-data2-2"]

    embedding_generator = SentenceEmbeddingGenerator(model_path)
    embeddings = embedding_generator.generate_embeddings(sentences)

    print(embeddings.shape)
    print("Sentence embeddings:", embeddings)
    
    llm = ChatCompletionHandler(model_name="ep-20241129094859-p47sh", base_url=f"https://ark.cn-beijing.volces.com/api/v3/")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Waht`s your name?"},
    ]
    
    non_stream_result = llm.non_streaming_chat(messages)
    print(non_stream_result)
    
    stream = llm.streaming_chat(messages)
    stream_result = ""

    for chunk in stream:
            if not chunk.choices:
                continue
            stream_result += chunk.choices[0].delta.content
    
    print(stream_result)
