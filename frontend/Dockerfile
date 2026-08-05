# 模块职责：frontend 镜像构建文件：第一阶段用 Node 构建 React 产物，第二阶段用 nginx 托管静态文件，最终镜像只含 nginx 与构建产物。

# 阶段一：构建（需要 Node 环境）
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# 阶段二：运行（只需要静态文件，换极小的 nginx）
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
