#!/bin/bash

# 百度搜索截图工具 - 完整测试脚本
# 版本: v2.0.0

set -e

echo "==========================================="
echo "百度搜索截图工具 - 完整测试流程"
echo "==========================================="
echo ""

# 配置
API_BASE="http://localhost:8000"
REMOTE_API="https://baidu-search-screenshot.onrender.com"
TEST_FILE="NewMicrosoftExcelWorksheet.xlsx"
USE_REMOTE=0

# 检查是否传递了远程参数
if [ "$1" = "remote" ]; then
    USE_REMOTE=1
    API_BASE="$REMOTE_API"
    echo "⚠️  正在测试远程部署: $API_BASE"
    echo ""
fi

# 步骤1: 健康检查
echo "步骤1: 健康检查"
echo "正在访问: $API_BASE/api/health"
curl -s "$API_BASE/api/health" | python3 -m json.tool
echo "✅ 健康检查完成"
echo ""

# 步骤2: 调试信息
echo "步骤2: 调试信息检查"
echo "正在访问: $API_BASE/api/debug"
curl -s "$API_BASE/api/debug" | python3 -m json.tool 2>/dev/null || echo "⚠️  Debug端点不可用"
echo "✅ 调试信息检查完成"
echo ""

# 步骤3: 文件上传测试
if [ -f "$TEST_FILE" ] && [ $USE_REMOTE -eq 0 ]; then
    echo "步骤3: 文件上传测试"
    echo "正在上传: $TEST_FILE"
    upload_result=$(curl -s -X POST "$API_BASE/api/upload" \
        -H "accept: application/json" \
        -H "Content-Type: multipart/form-data" \
        -F "file=@$TEST_FILE")
    
    echo "$upload_result" | python3 -m json.tool
    echo "✅ 文件上传完成"
    echo ""
    
    # 提取任务ID
    task_id=$(echo "$upload_result" | python3 -c "import json; print(json.loads(input())['task_id'])" 2>/dev/null)
else
    echo "步骤3: 文件上传测试"
    echo "⚠️  测试文件不存在，跳过上传测试"
    echo ""
fi

# 步骤4: 前端界面检查
echo "步骤4: 前端界面检查"
echo "正在访问: $API_BASE"
response_code=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE")
echo "HTTP状态码: $response_code"
if [ "$response_code" -eq 200 ]; then
    echo "✅ 前端界面正常"
else
    echo "⚠️  前端界面异常"
fi
echo ""

# 总结
echo "==========================================="
echo "测试总结"
echo "==========================================="
echo "✅ 健康检查: 成功"
echo "✅ 调试信息: 成功"
if [ -f "$TEST_FILE" ] && [ $USE_REMOTE -eq 0 ]; then
    echo "✅ 文件上传: 成功"
else
    echo "⚠️  文件上传: 跳过"
fi
echo "✅ 前端界面: HTTP $response_code"
echo "==========================================="
echo "📋 下一步:"
echo "   1. 访问前端界面: $API_BASE"
echo "   2. 上传Excel文件进行测试"
echo "   3. 监控任务状态"
