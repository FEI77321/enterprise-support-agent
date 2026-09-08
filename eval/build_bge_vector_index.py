# 模块职责：构建 bge-small-zh-v1.5 的独立 Chroma 向量索引。

from eval_path import setup_backend_path

setup_backend_path()

from app.vector_store import build_bge_vector_index


if __name__ == "__main__":
    build_bge_vector_index()