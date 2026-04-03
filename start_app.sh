#!/bin/bash

# 百度搜索截图工具 - 一键部署脚本
# 版本: v2.0.0
# 适配Render环境

set -e

echo "==========================================="
echo "百度搜索截图工具 - 一键部署脚本"
echo "==========================================="
echo ""

# 1. 检查Python版本
echo "1. 环境检查:"
python3 --version || echo "⚠️  Python3未安装，请先安装Python3"
pip3 --version || echo "⚠️  pip3未安装，请先安装pip3"
echo ""

# 2. 安装依赖
echo "2. 安装Python依赖:"
echo "   - 从web_requirements.txt安装..."
pip3 install --no-cache-dir -r web_requirements.txt
echo "✅  依赖安装完成"
echo ""

# 3. 检查Chrome和ChromeDriver
echo "3. 浏览器环境检查:"
if command -v chromium-浏览器 &> /dev/null; then
    echo "   - Chromium: $(chromium-浏览器 --version)" 2>/dev/null
elif command -v chrome &> /dev/null; then
    echo "   - Chrome: $(chrome --version)" 2>/dev/null
else
    echo "   ⚠️  未检测到Chrome/Chromium浏览器"
fi

if command -v chromedriver &> /dev/null; then
    echo "   - ChromeDriver: $(chromedriver --version)" 2>/dev/null
else
    echo "   ⚠️  未检测到ChromeDriver"
fi
echo ""

# 4. 启动服务
echo "4. 启动服务:"
echo "   - FastAPI服务将在0.0.0.0:8000启动"
echo "   - 访问地址: http://localhost:8000"
echo "   - 健康检查: http://localhost:8000/api/health"
echo ""
echo "按Ctrl+C停止服务"
echo "==========================================="
echo ""

# 启动FastAPI服务
uvicorn app:app --host 0.0.0.0 --port 8000
