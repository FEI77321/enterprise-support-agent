# 模块职责：简易向量检索模块：将知识库文本块构建为内存索引，使用轻量相似度算法检索相关内容，用于演示 RAG 的向量召回环节。

from dataclasses import dataclass
from app.knowledge_base import load_documents, split_text_into_chunks
from pathlib import Path

import chromadb


CHROMA_DIR = Path(__file__).resolve().parents[1] / "data" / "chroma"
COLLECTION_NAME = "enterprise_support_docs"

from chromadb.utils.embedding_functions import (
    SentenceTransformerEmbeddingFunction,
)

BGE_COLLECTION_NAME = "enterprise_support_docs_bge_small_zh"
BGE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
BGE_CACHE_DIR = Path(r"D:\AI-Model-Cache\huggingface")


def get_bge_embedding_function():
    """返回使用本地 D 盘缓存的中文 BGE embedding 函数。"""
    return SentenceTransformerEmbeddingFunction(
        model_name=BGE_MODEL_NAME,
        device="cpu",
        normalize_embeddings=True,
        cache_folder=str(BGE_CACHE_DIR),
    )


@dataclass
class VectorSearchResult:  # 类：表示向量检索命中的文本块、来源和相似度。
    chunk_id: str
    file: str
    content: str
    score: float


def load_knowledge_chunks() -> list[VectorSearchResult]:  # 函数：负责 加载 知识 chunks 相关逻辑。
    documents = load_documents()
    chunks: list[VectorSearchResult] = []

    for file, content in documents.items():
        for index, chunk in enumerate(split_text_into_chunks(content)):
            if chunk.startswith("#"):
                continue

            chunks.append(
                VectorSearchResult(
                    chunk_id=f"{file}::chunk-{index + 1}",
                    file=file,
                    content=chunk,
                    score=0.0,
                )
            )

    return chunks

def _simple_similarity(query: str, content: str) -> float:  # 函数：负责 simple similarity 相关逻辑。
    query = query.strip().lower()
    content = content.strip().lower()

    if query and query in content:
        return 1.0

    query_terms = set(query.split())
    content_terms = set(content.split())

    if not query_terms or not content_terms:
        return 0.0

    overlap = query_terms & content_terms
    return len(overlap) / len(query_terms)



def build_bge_vector_index() -> None:
    """使用 bge-small-zh-v1.5 构建独立中文向量索引。"""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    collection = client.get_or_create_collection(
        name=BGE_COLLECTION_NAME,
        embedding_function=get_bge_embedding_function(),
    )

    chunks = load_knowledge_chunks()

    ids = [chunk.chunk_id for chunk in chunks]
    documents = [chunk.content for chunk in chunks]
    metadatas = [
        {
            "file": chunk.file,
            "chunk_id": chunk.chunk_id,
        }
        for chunk in chunks
    ]

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    print(
        f"BGE 索引构建完成：{BGE_COLLECTION_NAME}，"
        f"共 {len(chunks)} 个子块"
    )



def build_vector_index() -> None:  # 函数：负责 构建 向量 index 相关逻辑。
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME
    )

    chunks = load_knowledge_chunks()

    ids = [chunk.chunk_id for chunk in chunks]##准备 ChromaDB 里的每条数据 ID
    documents = [chunk.content for chunk in chunks]
    metadatas = [
        {
            "file": chunk.file,
            "chunk_id": chunk.chunk_id,
        }
        for chunk in chunks
    ]

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )


def search_vector_store(query: str, top_k: int = 3) -> list[VectorSearchResult]:  # 函数：负责 检索 向量 存储 相关逻辑。
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME
    )

    result = collection.query(
        query_texts=[query],
        n_results=max(top_k, 10),
    )

    ids = result["ids"][0]
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    results: list[VectorSearchResult] = []

    for chunk_id, document, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
    ):
        score = max(0.0, 1.0 - float(distance))

        results.append(
            VectorSearchResult(
                chunk_id=chunk_id,
                file=metadata["file"],
                content=document,
                score=score,
            )
        )


    existing_chunk_ids = {result.chunk_id for result in results}
##exact match 补召回
    for chunk in load_knowledge_chunks():
        query_text = query.strip().lower()
        content_text = chunk.content.strip().lower()

        if query_text and query_text in content_text and chunk.chunk_id not in existing_chunk_ids:
            results.append(
                VectorSearchResult(
                    chunk_id=chunk.chunk_id,
                    file=chunk.file,
                    content=chunk.content,
                    score=1.0,
                )
            )

##rerank 加分
    for result in results:
        query_text = query.strip().lower()
        content_text = result.content.strip().lower()

        if query_text and query_text in content_text:
            result.score += 1.0

    results.sort(key=lambda item: item.score, reverse=True)
    return results[:top_k]


def search_bge_vector_store(
    query: str,
    top_k: int = 3,
) -> list[VectorSearchResult]:
    """在 bge-small-zh-v1.5 的独立索引中检索。"""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    collection = client.get_collection(
        name=BGE_COLLECTION_NAME,
        embedding_function=get_bge_embedding_function(),
    )

    result = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    results: list[VectorSearchResult] = []

    for chunk_id, document, metadata, distance in zip(
        result["ids"][0],
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
    ):
        results.append(
            VectorSearchResult(
                chunk_id=chunk_id,
                file=metadata["file"],
                content=document,
                # 当前阶段主要比较排序；分数只保留为非负展示值。
                score=max(0.0, 1.0 - float(distance)),
            )
        )

    return results
