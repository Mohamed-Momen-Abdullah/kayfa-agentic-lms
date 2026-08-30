import time
from llama_index.core.schema import TextNode

cache_index = None

def update_cache(query: str, answer: str):
    global cache_index
    if cache_index is None:
        return
    node = TextNode(
        text=query,
        metadata={"answer": str(answer), "timestamp": time.time(), "is_valid": True},
    )
    cache_index.insert_nodes([node])

def check_semantic_cache(query: str, threshold: float = 0.85):
    global cache_index
    if cache_index is None:
        return None, "miss"
    MAX_TTL = 24 * 60 * 60
    retriever = cache_index.as_retriever(similarity_top_k=1)
    try:
        results = retriever.retrieve(query)
        if results and results[0].score >= threshold:
            node = results[0].node
            metadata = node.metadata
            age = time.time() - metadata.get("timestamp", 0)
            if metadata.get("is_valid", True) and age <= MAX_TTL:
                return metadata["answer"], "fresh"
    except Exception as e:
        print(f"Cache check error: {e}")
    return None, "miss"
