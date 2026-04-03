"""
百度搜索截图在线工具 - 极简版本
适配Render环境
"""

import os
import asyncio
import json
import logging
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import openpyxl
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
import zipfile
import shutil

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(title="百度搜索截图在线工具", version="1.0.0")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建必要的目录
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
TEMP_DIR = "temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 挂载静态文件目录
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

# 全局任务状态存储
task_status = {}


class TaskRequest(BaseModel):
    """任务请求模型"""
    excel_filename: str
    sheet_name: str = None
    column_index: int = 0
    max_pages: int = 4


class TaskResponse(BaseModel):
    """任务响应模型"""
    task_id: str
    status: str
    message: str


def create_chrome_driver():
    """创建Chrome浏览器驱动 - 简化版"""
    try:
        chrome_options = ChromeOptions()
        
        # 基础参数
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 排除自动化开关
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # 尝试使用系统安装的chromedriver
        chrome_driver = os.environ.get('CHROME_DRIVER', '/usr/bin/chromedriver')
        if os.path.exists(chrome_driver):
            service = ChromeService(executable_path=chrome_driver)
            return webdriver.Chrome(service=service, options=chrome_options)
        
        # 尝试使用webdriver_manager
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType
        return webdriver.Chrome(
            service=ChromeService(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()),
            options=chrome_options
        )
        
    except Exception as e:
        logger.error(f"创建Chrome驱动失败: {str(e)}")
        raise


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return JSONResponse(content={"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.get("/api/debug")
async def debug_info():
    """调试信息"""
    debug_info = {
        "python_version": os.popen('python --version 2>&1').read().strip(),
        "chrome_exists": os.path.exists('/usr/bin/chromium') or os.path.exists('/usr/bin/google-chrome'),
        "chromedriver_exists": os.path.exists('/usr/bin/chromedriver'),
        "chromedriver_version": os.popen('chromedriver --version 2>/dev/null').read().strip(),
        "chrome_version": os.popen('chromium --version 2>/dev/null').read().strip() if os.path.exists('/usr/bin/chromium') else "N/A",
        "dependencies": {
            "selenium": os.popen('pip show selenium 2>/dev/null | grep Name').read().strip() != '',
            "webdriver_manager": os.popen('pip show webdriver-manager 2>/dev/null | grep Name').read().strip() != ''
        },
        "environment": {
            "CHROME_BIN": os.environ.get('CHROME_BIN', 'not set'),
            "CHROME_DRIVER": os.environ.get('CHROME_DRIVER', 'not set'),
            "DISPLAY": os.environ.get('DISPLAY', 'not set')
        }
    }
    return JSONResponse(content=debug_info)


@app.post("/api/upload", response_model=TaskResponse)
async def upload_excel(file: UploadFile = File(...)):
    """上传Excel文件"""
    try:
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="不支持的文件格式，请上传Excel文件")
        
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        
        return TaskResponse(
            task_id=task_id,
            status="uploaded",
            message=f"文件上传成功: {file.filename}"
        )
    
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@app.post("/api/process", response_model=TaskResponse)
async def process_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """处理搜索任务"""
    try:
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        task_status[task_id] = {
            "status": "queued",
            "message": "任务已加入队列..."
        }
        
        background_tasks.add_task(process_search_task, task_id, request)
        
        return TaskResponse(
            task_id=task_id,
            status="queued",
            message="任务已加入处理队列"
        )
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


async def process_search_task(task_id: str, request: TaskRequest):
    """处理搜索任务"""
    driver = None
    try:
        task_status[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "正在读取Excel文件...",
            "total": 0,
            "completed": 0,
            "failed": 0,
            "start_time": datetime.now().isoformat()
        }
        
        excel_path = os.path.join(UPLOAD_DIR, request.excel_filename)
        if not os.path.exists(excel_path):
            raise Exception(f"Excel文件不存在: {request.excel_filename}")
        
        workbook = openpyxl.load_workbook(excel_path)
        sheet = workbook[request.sheet_name] if request.sheet_name else workbook.active
        
        keywords = []
        for row in sheet.iter_rows(min_row=2):
            cell = row[request.column_index]
            if cell.value and str(cell.value).strip():
                keywords.append(str(cell.value).strip())
        
        if not keywords:
            raise Exception("没有找到有效的关键词")
        
        task_status[task_id]["total"] = len(keywords)
        task_status[task_id]["message"] = f"找到{len(keywords)}个关键词，开始处理..."
        
        task_output_dir = os.path.join(OUTPUT_DIR, task_id)
        os.makedirs(task_output_dir, exist_ok=True)
        
        driver = create_chrome_driver()
        wait = WebDriverWait(driver, 15)
        
        for idx, keyword in enumerate(keywords, 1):
            try:
                progress = int((idx - 1) / len(keywords) * 100)
                task_status[task_id]["progress"] = progress
                task_status[task_id]["message"] = f"正在处理第{idx}/{len(keywords)}个关键词: {keyword}"
                
                driver.get("https://www.baidu.com")
                await asyncio.sleep(2)
                
                search_box = wait.until(EC.presence_of_element_located((By.ID, "kw")))
                search_box.clear()
                search_box.send_keys(keyword)
                search_box.send_keys(Keys.RETURN)
                await asyncio.sleep(2)
                
                screenshot_path = os.path.join(task_output_dir, f"{keyword.replace('/', '_')}.jpg")
                driver.save_screenshot(screenshot_path)
                task_status[task_id]["completed"] += 1
                
            except Exception as e:
                logger.error(f"处理关键词 '{keyword}' 失败: {str(e)}")
                task_status[task_id]["failed"] += 1
                continue
        
        task_status[task_id].update({
            "status": "completed",
            "progress": 100,
            "message": f"处理完成！成功{task_status[task_id]['completed']}个，失败{task_status[task_id]['failed']}个",
            "end_time": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"任务处理失败: {str(e)}")
        task_status[task_id].update({
            "status": "failed",
            "message": f"任务失败: {str(e)}",
            "end_time": datetime.now().isoformat()
        })
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


@app.get("/api/status/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return JSONResponse(content=task_status[task_id])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
