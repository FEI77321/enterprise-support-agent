# 模块职责：backend 镜像构建文件：将 FastAPI 代码、依赖、向量索引脚本和只读知识库打包为可运行容器镜像。

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY data/docs ./data/docs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
