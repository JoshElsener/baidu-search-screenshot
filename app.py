"""
百度搜索截图在线工具 - FastAPI后端服务
支持Excel上传、Edge浏览器自动化搜索、截图生成和下载
"""

import os
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket
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

# 挂载静态文件目录 - 修复路由优先级问题
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

# 全局任务状态存储（生产环境应使用Redis）
task_status = {}


class TaskRequest(BaseModel):
    """任务请求模型"""
    excel_filename: str
    sheet_name: Optional[str] = None
    column_index: int = 0
    max_pages: int = 4


class TaskResponse(BaseModel):
    """任务响应模型"""
    task_id: str
    status: str
    message: str


def clean_filename(filename):
    """清理文件名中的非法字符"""
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    if len(filename) > 100:
        filename = filename[:100]
    return filename.strip()


def create_chrome_driver():
    """创建Chromium浏览器驱动 - 针对Render环境深度优化"""
    try:
        chrome_options = ChromeOptions()
        
        # 基础参数
        chrome_options.add_argument('--headless=new')  # 使用新的Headless模式
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # 反检测参数 - 更全面的反检测设置
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--disable-translate')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        chrome_options.add_argument('--disable-hang-monitor')
        chrome_options.add_argument('--disable-ipc-flooding-protection')
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--no-default-浏览器-check')
        chrome_options.add_argument('--no-experiments')
        chrome_options.add_argument('--no-service-autorun')
        chrome_options.add_argument('--no-startup-window')
        chrome_options.add_argument('--force-color-profile=srgb')
        chrome_options.add_argument('--metrics-recording-only')
        chrome_options.add_argument('--password-store=basic')
        chrome_options.add_argument('--use-mock-keychain')
        
        # 性能优化参数 - 适配Render的512MB内存限制
        chrome_options.add_argument('--memory-pressure-off')
        chrome_options.add_argument('--max_old_space_size=256')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        # 用户代理伪装 - 使用更真实的Chrome UA
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 排除自动化开关
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # 指定二进制路径 - 确保使用系统安装的Chromium
        chrome_binary = os.environ.get('CHROME_BIN', '/usr/bin/chromium')
        chrome_driver = os.environ.get('CHROME_DRIVER', '/usr/bin/chromedriver')
        
        if os.path.exists(chrome_binary):
            chrome_options.binary_location = chrome_binary
            logger.info(f"使用Chrome二进制: {chrome_binary}")
        
        # 使用ChromeDriver服务
        driver = None
        
        # 尝试1: 使用系统安装的chromedriver
        try:
            if os.path.exists(chrome_driver):
                service = ChromeService(executable_path=chrome_driver)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info(f"使用系统ChromeDriver: {chrome_driver}")
        except Exception as e:
            logger.error(f"使用系统ChromeDriver失败: {str(e)}")
        
        # 尝试2: 使用自动下载的chromedriver
        if not driver:
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                from webdriver_manager.core.os_manager import ChromeType
                
                driver = webdriver.Chrome(
                    service=ChromeService(
                        ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
                    ),
                    options=chrome_options
                )
                logger.info("使用webdriver_manager自动下载的ChromeDriver")
            except Exception as e:
                logger.error(f"使用webdriver_manager失败: {str(e)}")
        
        # 尝试3: 使用Selenium Hub（如果配置了的话）
        if not driver:
            try:
                from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
                
                driver = webdriver.Remote(
                    command_executor='http://chrome:4444/wd/hub',
                    desired_capabilities=DesiredCapabilities.CHROME
                )
                logger.info("使用Selenium Hub")
            except Exception as e:
                logger.error(f"使用Selenium Hub失败: {str(e)}")
        
        # 如果还是无法创建，抛出异常
        if not driver:
            raise Exception("无法创建Chrome驱动，所有尝试都失败了")
        
        # 注入反检测脚本 - 更全面的反检测
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en-US', 'en']
                });
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 4
                });
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 0
                });
                Object.defineProperty(window, 'chrome', {
                    get: () => {
                        return {
                            runtime: {},
                            loadTimes: () => {
                                return {
                                    requestTime: Date.now() - 1000,
                                    startLoadTime: Date.now() - 500,
                                    commitLoadTime: Date.now(),
                                    finishDocumentLoadTime: Date.now() + 500,
                                    finishLoadTime: Date.now() + 1000
                                };
                            }
                        };
                    }
                });
                Object.defineProperty(window, 'scrollY', {
                    get: () => 0
                });
                Object.defineProperty(window, 'outerWidth', {
                    get: () => 1920
                });
                Object.defineProperty(window, 'outerHeight', {
                    get: () => 1080
                });
                Object.defineProperty(window, 'innerWidth', {
                    get: () => 1920
                });
                Object.defineProperty(window, 'innerHeight', {
                    get: () => 1080
                });
            """
        })
        
        logger.info("Chrome驱动创建成功 - 完成所有反检测设置")
        return driver
        
    except Exception as e:
        logger.error(f"创建Chrome驱动失败: {str(e)}")
        # 打印详细错误信息用于调试
        import traceback
        logger.error(traceback.format_exc())
        raise


async def process_search_task(task_id: str, request: TaskRequest):
    """处理搜索任务"""
    driver = None
    try:
        # 更新任务状态
        task_status[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "正在读取Excel文件...",
            "total": 0,
            "completed": 0,
            "failed": 0,
            "start_time": datetime.now().isoformat()
        }
        
        # 读取Excel文件
        excel_path = os.path.join(UPLOAD_DIR, request.excel_filename)
        if not os.path.exists(excel_path):
            raise Exception(f"Excel文件不存在: {request.excel_filename}")
        
        workbook = openpyxl.load_workbook(excel_path)
        
        # 选择工作表
        if request.sheet_name:
            sheet = workbook[request.sheet_name]
        else:
            sheet = workbook.active
        
        # 提取关键词
        keywords = []
        for row in sheet.iter_rows(min_row=2):
            cell = row[request.column_index]
            if cell.value and str(cell.value).strip():
                keywords.append(str(cell.value).strip())
        
        if not keywords:
            raise Exception("没有找到有效的关键词")
        
        # 更新任务状态
        task_status[task_id]["total"] = len(keywords)
        task_status[task_id]["message"] = f"找到{len(keywords)}个关键词，开始处理..."
        
        # 创建输出目录（使用分类文件夹结构）
        task_output_dir = os.path.join(OUTPUT_DIR, task_id)
        os.makedirs(task_output_dir, exist_ok=True)
        
        # 创建Chromium浏览器驱动
        driver = create_chrome_driver()
        wait = WebDriverWait(driver, 15)
        
        # 处理每个关键词
        for idx, keyword in enumerate(keywords, 1):
            try:
                # 更新进度
                progress = int((idx - 1) / len(keywords) * 100)
                task_status[task_id]["progress"] = progress
                task_status[task_id]["message"] = f"正在处理第{idx}/{len(keywords)}个关键词: {keyword}"
                
                clean_keyword = clean_filename(keyword)
                
                # 为每个关键词创建单独的文件夹
                keyword_dir = os.path.join(task_output_dir, clean_keyword)
                os.makedirs(keyword_dir, exist_ok=True)
                
                success_count = 0
                
                # 访问百度首页
                logger.info(f"访问百度: {keyword}")
                driver.get("https://www.baidu.com")
                await asyncio.sleep(2)
                
                # 输入搜索关键词
                try:
                    search_box = wait.until(
                        EC.presence_of_element_located((By.ID, "kw"))
                    )
                    search_box.clear()
                    search_box.send_keys(keyword)
                    search_box.send_keys(Keys.RETURN)
                    await asyncio.sleep(2.5)
                except Exception as e:
                    logger.error(f"搜索框操作失败: {str(e)}")
                    # 截图当前页面用于调试
                    debug_screenshot = os.path.join(task_output_dir, f"{clean_keyword}_debug_0.jpg")
                    try:
                        driver.save_screenshot(debug_screenshot)
                        logger.info(f"保存调试截图: {debug_screenshot}")
                    except:
                        pass
                    task_status[task_id]["failed"] += 1
                    continue
                
                # 逐页截图
                for page in range(1, request.max_pages + 1):
                    try:
                        screenshot_filename = f"{clean_keyword}{page}.jpg"
                        screenshot_path = os.path.join(keyword_dir, screenshot_filename)
                        
                        # 滚动到页面顶部
                        driver.execute_script("window.scrollTo(0, 0);")
                        await asyncio.sleep(0.5)
                        
                        # 截图
                        driver.save_screenshot(screenshot_path)
                        success_count += 1
                        logger.info(f"成功截图: {screenshot_filename}")
                        
                        # 点击下一页
                        if page < request.max_pages:
                            try:
                                next_button = driver.find_element(By.CSS_SELECTOR, "a.n")
                                if next_button and next_button.is_displayed():
                                    next_button.click()
                                    await asyncio.sleep(2.5)
                                else:
                                    logger.warning(f"关键词 '{keyword}' 第{page}页后没有更多结果")
                                    break
                            except Exception as e:
                                logger.warning(f"找不到下一页按钮: {str(e)}")
                                break
                    
                    except Exception as e:
                        logger.error(f"截图第{page}页失败: {str(e)}")
                        continue
                
                # 如果没有截图成功，标记失败
                if success_count == 0:
                    logger.warning(f"关键词 '{keyword}' 未生成任何截图")
                    task_status[task_id]["failed"] += 1
                else:
                    task_status[task_id]["completed"] += 1
                
                # 添加延迟，避免被封
                if idx < len(keywords):
                    delay = 3 + (idx % 3)
                    await asyncio.sleep(delay)
            
            except Exception as e:
                logger.error(f"处理关键词 '{keyword}' 失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                task_status[task_id]["failed"] += 1
                continue
        
        # 创建ZIP压缩包
        try:
            # 检查是否生成了截图
            screenshot_files = []
            for root, dirs, files in os.walk(task_output_dir):
                for file in files:
                    if file.endswith(('.jpg', '.png')):
                        screenshot_files.append(os.path.join(root, file))
            
            if not screenshot_files:
                raise Exception("没有生成任何截图文件，请检查百度搜索是否成功")
            
            logger.info(f"共找到 {len(screenshot_files)} 张截图文件")
            
            zip_filename = f"{task_id}_screenshots.zip"
            zip_path = os.path.join(OUTPUT_DIR, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(task_output_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, task_output_dir)
                        zipf.write(file_path, arcname)
            
            logger.info(f"ZIP 压缩包创建成功: {zip_filename}")
            
            # 更新任务状态为完成
            task_status[task_id].update({
                "status": "completed",
                "progress": 100,
                "message": f"处理完成！共生成 {len(screenshot_files)} 张截图",
                "end_time": datetime.now().isoformat(),
                "zip_filename": zip_filename,
                "download_url": f"/outputs/{zip_filename}"
            })
        except Exception as e:
            logger.error(f"创建ZIP压缩包失败: {str(e)}")
            raise Exception(f"生成结果失败: {str(e)}")
    
    except Exception as e:
        logger.error(f"任务处理失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
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


@app.get("/")
async def root():
    """根路径，返回前端页面"""
    return FileResponse("frontend/index.html")


@app.post("/api/upload", response_model=TaskResponse)
async def upload_excel(file: UploadFile = File(...)):
    """上传Excel文件"""
    try:
        # 验证文件类型
        if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
            raise HTTPException(status_code=400, detail="不支持的文件格式，请上传Excel文件")
        
        # 保存文件
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 生成任务ID
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
        # 生成任务ID
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 初始化任务状态
        task_status[task_id] = {
            "status": "queued",
            "message": "任务已加入队列..."
        }
        
        # 添加后台任务
        background_tasks.add_task(process_search_task, task_id, request)
        
        return TaskResponse(
            task_id=task_id,
            status="queued",
            message="任务已加入处理队列"
        )
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@app.get("/api/status/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return JSONResponse(content=task_status[task_id])


@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket连接，实时推送任务进度"""
    await websocket.accept()
    
    try:
        while True:
            if task_id in task_status:
                await websocket.send_json(task_status[task_id])
                
                # 如果任务完成或失败，断开连接
                if task_status[task_id]["status"] in ["completed", "failed"]:
                    await websocket.close()
                    break
            
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"WebSocket连接错误: {str(e)}")
        await websocket.close()


@app.get("/api/download/{task_id}")
async def download_results(task_id: str):
    """下载任务结果"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task_info = task_status[task_id]
    if task_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    zip_path = os.path.join(OUTPUT_DIR, task_info["zip_filename"])
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="结果文件不存在")
    
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"screenshots_{task_id}.zip"
    )


@app.get("/api/preview/{task_id}")
async def preview_results(task_id: str):
    """预览任务结果"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task_info = task_status[task_id]
    if task_info["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    task_output_dir = os.path.join(OUTPUT_DIR, task_id)
    if not os.path.exists(task_output_dir):
        raise HTTPException(status_code=404, detail="结果目录不存在")
    
    # 获取所有截图文件
    screenshots = []
    for root, dirs, files in os.walk(task_output_dir):
        for file in files:
            if file.endswith(('.jpg', '.png')):
                screenshots.append({
                    "filename": file,
                    "url": f"/outputs/{task_id}/{file}"
                })
    
    return JSONResponse(content={
        "task_id": task_id,
        "screenshots": screenshots,
        "total": len(screenshots)
    })


@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str):
    """删除任务及其结果"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    try:
        # 删除任务状态
        del task_status[task_id]
        
        # 删除结果文件
        task_output_dir = os.path.join(OUTPUT_DIR, task_id)
        if os.path.exists(task_output_dir):
            shutil.rmtree(task_output_dir)
        
        # 删除ZIP文件
        task_info = task_status.get(task_id, {})
        if "zip_filename" in task_info:
            zip_path = os.path.join(OUTPUT_DIR, task_info["zip_filename"])
            if os.path.exists(zip_path):
                os.remove(zip_path)
        
        return JSONResponse(content={"message": "任务删除成功"})
    
    except Exception as e:
        logger.error(f"删除任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return JSONResponse(content={"status": "healthy", "timestamp": datetime.now().isoformat()})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
