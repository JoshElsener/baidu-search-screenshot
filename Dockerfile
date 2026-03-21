FROM python:3.9-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    libglib2.0-0 \
    libnss3  \
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

# 安装Microsoft Edge
RUN wget -q -O - https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge.list' \
    && apt-get update \
    && apt-get install -y microsoft-edge-stable \
    && rm -rf /var/lib/apt/lists/*

# 安装Microsoft Edge WebDriver
RUN apt-get update && apt-get install -y microsoft-edge-driver

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY web_requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r web_requirements.txt

# 复制应用文件
COPY app.py .
COPY frontend ./frontend

# 创建必要的目录
RUN mkdir -p uploads outputs temp

# 暴露端口
EXPOSE 8000

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动应用
CMD ["python", "app.py"]
