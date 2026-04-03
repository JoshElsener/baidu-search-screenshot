# 针对Render环境优化的Dockerfile
FROM python:3.9-slim

# 设置构建参数 - 强制重新构建
ARG BUILD_DATE=2026-04-01

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    libglib2.0-0 \
    libnss3 \
    libxss1 \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 安装Chromium浏览器
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# 设置Chrome环境变量
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_DRIVER=/usr/bin/chromedriver

# 验证安装
RUN ls -la /usr/bin/chromium && \
    ls -la /usr/bin/chromedriver && \
    chromium --version && \
    chromedriver --version

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY web_requirements.txt .

# 使用国内源加速安装
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r web_requirements.txt

# 复制应用文件
COPY app.py .
COPY frontend ./frontend

# 创建必要的目录
RUN mkdir -p uploads outputs temp && \
    chmod -R 777 uploads outputs temp

# 暴露端口
EXPOSE 8000

# 设置环境变量 - 针对Render优化
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV PYTHONPATH=/app
ENV TZ=Asia/Shanghai

# 优化内存设置
ENV MAX_OLD_SPACE_SIZE=256
ENV NODE_OPTIONS="--max-old-space-size=$MAX_OLD_SPACE_SIZE"

# 启动命令
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 -ac & python app.py"]
