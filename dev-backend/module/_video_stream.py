from typing import Dict
import logging
from concurrent.futures import ThreadPoolExecutor
import struct,cv2
import asyncio
camera_streams: Dict[int, Dict[str, any]] = {}
executor = ThreadPoolExecutor(max_workers=4)  # 根据CPU核心数调整
logger = logging.getLogger(__name__)
async def stream_camera(camera_id: int, area=None, clarity=50):
    if camera_id not in camera_streams or not camera_streams[camera_id]["active"]:return
    capture = camera_streams[camera_id]["capture"]
    clients = list(camera_streams[camera_id]["clients"])
    header = struct.pack(">I", 0xFFFF0000)  # 使用大端字节序打包帧头
    try:
        while camera_streams[camera_id]["active"] and clients:
            if len(camera_streams[camera_id]["clients"]) == 0:
                break
            ret, frame = capture.read()
            if not ret:break
            if area:
                reduce_result = await reduce_px1(frame, area_area=area)
                if reduce_result["status"]:
                    frame = reduce_result["frame"]
            _, buffer = cv2.imencode('.webp', frame, [int(cv2.IMWRITE_WEBP_QUALITY), clarity])
            frame_bytes = buffer.tobytes()
            to_remove = []
            for client in list(camera_streams[camera_id]["clients"]):  # 遍历客户端列表的副本，避免在迭代时修改
                try:await client.send_bytes(header + frame_bytes)
                except Exception as e:to_remove.append(client)
            for client in to_remove:camera_streams[camera_id]["clients"].remove(client)# 移除断开的客户端
            await asyncio.sleep(0.03)  # 控制帧率,约 33ms -> 30fps
    except Exception as e:
        logger.exception(f"Streaming disconnected for camera {camera_id}")
    finally:# 停止摄像头流并释放资源
        logger.warning(f"Stopping camera stream for camera {camera_id}")
        if camera_id in camera_streams:
            camera_streams[camera_id]["active"] = False
            if camera_streams[camera_id]["capture"]:
                camera_streams[camera_id]["capture"].release()
            del camera_streams[camera_id]  # 删除摄像头记录
@staticmethod
async def reduce_px1(frame,area_area):
    # 获取原始分辨率
    height, width = frame.shape[:2]
    if width < 320 or height < 240:
        logger.warning(f"Resolution too small: {(width, height)}, minimum required: 320 * 240")
        return {"status":False,"msg":"The resolution is too small, the minimum allowed resolution is 320 * 240"}
    # 自适应裁剪逻辑
    max_side = max(width, height)
    if area_area == 0 or max_side <= area_area:
        return {"status":True,"frame":frame}
    elif max_side > area_area:
        # 计算中心区域
        start_x = max(0, (width - area_area) // 2)
        start_y = max(0, (height - area_area) // 2)
        end_x = min(width, start_x + area_area)
        end_y = min(height, start_y + area_area)
        if end_x > width:
            end_x = width
            start_x = width - area_area
        if end_y > height:
            end_y = height
            start_y = height - area_area
        processed_frame = frame[
            start_y : end_y,
            start_x : end_x
        ]
        return {"status":True,"frame":processed_frame}
    else:return {"status":True,"frame":frame}

