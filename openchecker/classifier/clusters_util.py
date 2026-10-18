from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity, pairwise_distances
from sklearn.cluster import KMeans
import numpy as np
import json
import os
from llm import SentenceEmbeddingGenerator
import matplotlib.pyplot as plt

def euclidean_distance(point1, point2):
    """
    欧几里得距离计算函数
    """
    return np.sqrt(np.sum((point1 - point2) ** 2))


def manhattan_distance(point1, point2):
    """
    曼哈顿距离计算函数
    """
    return np.sum(np.abs(point1 - point2))

class KMeans:
    def __init__(self, n_clusters=3, max_iter=500, rtol=1.e-5, atol=1.e-8, distance_func_x=euclidean_distance, distance_func_y=cosine_similarity):
        self.n_clusters = n_clusters
        self.max_iter = max_iter
        self.rtol = rtol
        self.atol = atol
        self.distance_func_x = distance_func_x
        self.distance_func_y = distance_func_y
        self.centroids_x = None
        self.centroids_y = None
        self.clusters_with_index = None

    def fit(self, X, Y=None):
        intial_centroids_index = np.random.choice(X.shape[0], self.n_clusters, replace=False)
        self.centroids_x = X[intial_centroids_index]
        self.centroids_y = Y[intial_centroids_index]

        for _ in range(self.max_iter):
            clusters_x = [[] for _ in range(self.n_clusters)]
            clusters_y = [[] for _ in range(self.n_clusters)]
            clusters_with_index = [[] for _ in range(self.n_clusters)]
            for i, point in enumerate(X):
                distances = [self.distance_func_x(point, centroid) for centroid in self.centroids_x] + [self.distance_func_y(point, centroid) for centroid in self.centroids_y]
                cluster_index = np.argmin(distances)
                clusters_x[cluster_index].append(point)
                clusters_y[cluster_index].append(Y[i])
                clusters_with_index[cluster_index].append(i)
            self.clusters_with_index = clusters_with_index

            prev_centroids_x = self.centroids_x.copy()
            prev_centroids_y = self.centroids_y.copy()
            for i, cluster in enumerate(clusters_x):
                if len(cluster) > 0:
                    self.centroids_x[i] = np.mean(cluster, axis=0)
            for i, cluster in enumerate(clusters_y):
                if len(cluster) > 0:
                    self.centroids_y[i] = np.mean(cluster, axis=0)


            if np.allclose(self.centroids_x, prev_centroids_x, self.rtol, self.atol) and np.allclose(self.centroids_y, prev_centroids_y, self.rtol, self.atol):
                break

    def predict(self, X, Y=None):
        predictions = []
        for point in X:
            distances = [self.distance_func_x(point, centroid) for centroid in self.centroids_x]
            cluster_index = np.argmin(distances)
            predictions.append(cluster_index)
        return np.array(predictions)

if __name__ == "__main__":

    all_projects_test = [
        {
            "topics": ["web development", "python"],
            "description": "A web application developed with Python and Django.",
            "language": "Python"
        },
        {
            "topics": ["data science", "python"],
            "description": "A data analysis tool using Python libraries.",
            "language": "Python"
        },
        {
            "topics": ["web development", "javascript"],
            "description": "A front-end web app built with JavaScript.",
            "language": "JavaScript"
        }
    ]

    """ Loading all projects and related info from json file  """
    all_projects = []
    projects_file_path = "/home/guoqiang/opencheck/test/projects.json"
    cache_file_path="/home/guoqiang/opencheck/test/.embedding_cache.json"

    with open(projects_file_path, "r") as f:
        projects = json.load(f)
        all_projects = [{
                    "name": project["_source"]["name"], 
                    "description": project["_source"]["description"],
                    "topics": project["_source"]["topics"],
                    "language": project["_source"]["language"]
                 } for project in projects ]


    """" Generate feature with TF-IDF """
    def project_to_feature_vector(project):
        all_text = " ".join(project["name"]) + " " + project["description"] + " " + project["language"] + " ".join(project["topics"])
        return all_text

    project_feature_vectors = [project_to_feature_vector(project) for project in all_projects]

    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(project_feature_vectors)
    # X = pairwise_distances(X, metric=cosine_similarity)
    print("X shape: ", X.shape)
    
    vocabulary = vectorizer.vocabulary_
    print("vocabulary:")
    for word, index in vocabulary.items():
        print(f"{word}: {index}")


    """" Generate embedding vector with LLM model """
    model_path = '/home/guoqiang/models/bge-large-en-v1.5'
    embedding_model = SentenceEmbeddingGenerator(model_path)

    embedding_cache_data = {}
    vectorized_data = []

    if os.path.exists(cache_file_path):
        with open(cache_file_path, "r") as f:
            embedding_cache_data = json.load(f)
    
    need_vectorized_data = [ project["description"] for project in all_projects if hash(project["description"]) not in embedding_cache_data ]
    new_embedding_cache_data = embedding_model.generate_embeddings(need_vectorized_data)
    
    index = 0
    for project in all_projects:
        project_id = hash(project["description"])
        if project_id in embedding_cache_data:
            vectorized_data.append(embedding_cache_data[project_id])
        else:
            vectorized_data.append(new_embedding_cache_data[index])
            embedding_cache_data[project_id] = new_embedding_cache_data[index]
            index += 1
            
    with open(cache_file_path, "w") as f:
            json.dump(embedding_cache_data, f)
            
    print("Y shape: ", len(vectorized_data))
    
    """"Generate clustes with K-means """
    num_clusters = 10

    kmeans = KMeans(n_clusters=num_clusters, distance_func_x=manhattan_distance)
    kmeans.fit(X.toarray(), vectorized_data.toarray())

    clusters_index = kmeans.clusters_with_index

    for i, cluster_index in enumerate(clusters_index):
        for index in cluster_index:
            all_projects[index]["cluster_id"] = i
            print(f"cluster {i}: project_name: {all_projects[index]['name']} description: {all_projects[index]['description']}")

    for i, project in enumerate(all_projects):
        print(f"Project {i}: {project['description']}, Cluster ID: {project['cluster_id']}")

    # Visulation
    # colors = plt.cm.get_cmap('Set1', num_clusters)

    # for i, project in enumerate(all_projects):
    #     vector = np.array(X[i])
    #     cluster_id = project["cluster_id"]
    #     color = colors(cluster_id)

    #     plt.scatter(range(vec)), vector, c=color, label=f"Cluster {cluster_id}: {project['project_name']}")

    # plt.legend()

    # plt.title("Projects Visualization based on Vectors")
    # plt.xlabel("Vector Position")
    # plt.ylabel("Vector Value")

    # plt.show()