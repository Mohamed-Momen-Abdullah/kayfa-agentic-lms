import os
import pandas as pd
from llama_index.core import Settings, VectorStoreIndex, StorageContext, load_index_from_storage
from llama_index.core.schema import TextNode, Document as LlamaDocument
from llama_index.llms.groq import Groq as LlamaGroq
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SentenceSplitter, SemanticSplitterNodeParser
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.retrievers import QueryFusionRetriever

from app.agents.config import GROQ_MODEL, GROQ_API_KEY, EMBEDDING_MODEL
from app.data.connector import DATA_FOLDER_PATH
from app.services.sentiment import arabic_tokenizer
from app.observability.tracing import callback_manager

IQ_QUERY_TERMS = ("iq", "iq test", "iq quiz", "intelligence test", "intelligence quiz", "اختبار iq", "اختبار ذكاء", "اختبار الذكاء", "كويز ذكاء", "قياس الذكاء", "مقياس الذكاء", "اختبار القدرات العقلية")

def is_iq_query(query: str) -> bool:
    q = str(query).lower().strip()
    return any(term in q for term in IQ_QUERY_TERMS)

def load_documents_from_folder(folder_path: str):
    json_documents, csv_documents = [], []
    if not os.path.exists(folder_path): return json_documents, csv_documents
    RELEVANT_JSON_FILES = os.getenv("RAG_JSON_FILES", "").split(",") if os.getenv("RAG_JSON_FILES") else []
    
    for filename in RELEVANT_JSON_FILES:
        filename = filename.strip()
        if not filename: continue
        try:
            df_json = pd.read_json(os.path.join(folder_path, filename))
            for idx, row in df_json.iterrows():
                json_documents.append(LlamaDocument(text=str(row.to_dict()), metadata={"source": filename, "row_id": idx}))
        except Exception: pass
        
    for csv_file in ["FAQs.csv", "Policies.csv", "IQ_Quiz_Bank.csv", "IQ_quiz_bank.csv", "iq_quiz_bank.csv", "IQ_QuizBank.csv", "iq_bank.csv", "IQ.csv"]:
        if os.path.exists(os.path.join(folder_path, csv_file)):
            try:
                df = pd.read_csv(os.path.join(folder_path, csv_file))
                for idx, text in df.apply(lambda row: " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notnull(val)]), axis=1).items():
                    csv_documents.append(LlamaDocument(text=f"ملف {csv_file}: {text}", metadata={"source": csv_file, "row_id": int(idx)}))
            except Exception: pass
    return json_documents, csv_documents

def init_hybrid_agent_system():
    Settings.embed_model = HuggingFaceEmbedding(model_name=EMBEDDING_MODEL)
    if callback_manager:
        Settings.callback_manager = callback_manager
    Settings.llm = LlamaGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0.2, streaming=False, reasoning_effort="none")
    splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    Settings.node_parser = splitter

    PERSIST_DIR = os.getenv("RAG_PERSIST_DIR", os.path.join(DATA_FOLDER_PATH, "_university_rag_index_v2"))
    hybrid_retriever, nodes = None, []

    if os.path.exists(PERSIST_DIR):
        try:
            vector_index = load_index_from_storage(StorageContext.from_defaults(persist_dir=PERSIST_DIR))
            nodes = list(vector_index.docstore.docs.values())
        except Exception: vector_index = None
    else: vector_index = None

    if vector_index is None:
        json_documents, csv_documents = load_documents_from_folder(DATA_FOLDER_PATH)
        json_nodes = []
        if json_documents:
            try:
                semantic_splitter = SemanticSplitterNodeParser(buffer_size=1, breakpoint_percentile_threshold=95, embed_model=Settings.embed_model)
                json_nodes = semantic_splitter.get_nodes_from_documents(json_documents)
            except Exception:
                json_nodes = splitter.get_nodes_from_documents(json_documents)
        csv_nodes = [TextNode(text=doc.text, metadata=doc.metadata) for doc in csv_documents]
        nodes = json_nodes + csv_nodes

        if nodes:
            vector_index = VectorStoreIndex(nodes, show_progress=False)
            try: vector_index.storage_context.persist(persist_dir=PERSIST_DIR)
            except Exception: pass

    if nodes:
        vector_retriever = vector_index.as_retriever(similarity_top_k=5)
        bm25_retriever = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=5, tokenizer=arabic_tokenizer)
        hybrid_retriever = QueryFusionRetriever(retrievers=[vector_retriever, bm25_retriever], similarity_top_k=5, num_queries=1, mode="reciprocal_rerank", use_async=False)

    return {"hybrid_retriever": hybrid_retriever, "nodes": nodes}
