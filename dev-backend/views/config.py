import logging
import os
from fastapi.responses import JSONResponse  
from fastapi import APIRouter, Request,HTTPException,File, UploadFile
from module._base import CONFIG_PATH,DEFAULT_MAIN_CONFIG,SopConfig,get_models_path,JsonFile,get_main_config,DEFAULT_RESOLUTIONS,ConfigUpdater
from datetime import datetime
logger = logging.getLogger(__name__)
api_config = APIRouter()
@api_config.get("/get_config")
def get_config():
    config_datas = get_main_config()
    sop_config = SopConfig()
    sop_config_datas = sop_config.get()
    if "resolutions" not in config_datas:
        config_datas["resolutions"] = DEFAULT_RESOLUTIONS
    return JSONResponse(content={"status": True, "datas": config_datas,"sops":sop_config_datas})
@api_config.get("/box_style_config")
def get_box_style_config():
    config_datas = get_main_config()
    box_style_config = config_datas.get("boxStyle", DEFAULT_MAIN_CONFIG["boxStyle"])
    return JSONResponse(content={"status": True, "datas": box_style_config})
@api_config.post("/set_box_style_config")
async def set_box_style_config(request: Request):
    try:
        body = await request.json()
        box_style_config = body.get("boxStyle")
        if not box_style_config:return JSONResponse(content={"status": False, "msg": "Missing boxStyle parameter"})
        config_datas = get_main_config()
        config_datas["boxStyle"] = box_style_config
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return JSONResponse(content={"status": True, "msg": "Box style configuration set successfully"})
    except Exception as e:
        logger.exception(f"Error setting box style configuration: {e}")
        return JSONResponse(content={"status": False, "msg": "Failed to set box style configuration"})
@api_config.post("/display_box_style_config")
async def display_box_style_config(request: Request):
    import numpy as np
    import base64
    import cv2
    try:
        body = await request.json()
        box_style_config = body.get("boxStyle")
        if not box_style_config:return JSONResponse(content={"status": False, "msg": "Missing boxStyle parameter"})
        box_thickness = box_style_config.get("boxThickness", 3)
        font_thickness = box_style_config.get("fontThickness", 2)
        font_scale = box_style_config.get("fontScale", 0.5)
        from_area_fill = box_style_config.get("fromAreaFill", False)
        target_area_fill = box_style_config.get("targetAreaFill", False)
        img = np.zeros((400, 400, 3), dtype=np.uint8)
        cv2.rectangle(img, (50, 50), (150,150), (0, 255, 0), thickness=box_thickness)
        (textSizeW, textSizeH), baseline = cv2.getTextSize('Example', cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
        cv2.putText(img, 'Example', (50, 50-textSizeH), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), thickness=font_thickness, lineType=cv2.LINE_AA)
        if from_area_fill:
            cv2.rectangle(img, (200, 50), (300,150), (250, 180, 255), thickness=cv2.FILLED)
        if target_area_fill:
            cv2.rectangle(img, (50, 250), (150,350), (180, 180, 255), thickness=cv2.FILLED)
        cv2.rectangle(img, (200, 50), (300,150), (0, 255, 255), thickness=box_thickness)
        cv2.putText(img, 'Start', (200, 50-textSizeH), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 255), thickness=font_thickness, lineType=cv2.LINE_AA)
        cv2.rectangle(img, (50, 250), (150,350), (0, 0, 255), thickness=box_thickness)
        cv2.putText(img, 'Target', (50, 250-textSizeH), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), thickness=font_thickness, lineType=cv2.LINE_AA)
        _, img_encoded = cv2.imencode('.webp', img, [int(cv2.IMWRITE_WEBP_QUALITY), 90])
        img_base64 = base64.b64encode(img_encoded).decode('utf-8')
        result_img = f"data:image/webp;base64,{img_base64}"
        return JSONResponse({"status": True, "frame": result_img, "msg": "Example image generated successfully"})
    except Exception as e:
        logger.exception(f"Error displaying box style configuration: {e}")
        return JSONResponse(content={"status": False, "msg": "Failed to display box style configuration"})
@api_config.get("/open_models_folder")
def open_models_folder():
    try:
        models_path = get_models_path()
        if not os.path.exists(models_path):
            os.makedirs(models_path)
        os.startfile(models_path)
        return JSONResponse({"status":True})
    except Exception as e:
        logger.exception(f"Error opening models folder")
        return JSONResponse(content={"status":False,"msg":"Failed to open models folder"})
@api_config.get("/get_models")
def get_models():
    try:
        models_path = get_models_path()
        model_status = {}
        for model_dir in os.listdir(models_path):
            model_folder = os.path.join(models_path, model_dir)
            if os.path.isdir(model_folder):
                onnx_file = "example.onnx"
                for file in os.listdir(model_folder):
                    if file.endswith(".onnx"):
                        onnx_file = os.path.join(model_folder, file)
                        break
                cache_file = os.path.join(model_folder, "cache.json")
                model_status[model_dir] = os.path.exists(onnx_file) and os.path.exists(cache_file)
        return JSONResponse(content={"status":True,"datas": model_status})
    except Exception as e:
        logger.exception("Error getting models")
        return JSONResponse(content={"status":False,"msg":"Failed to getting model"})
@api_config.delete("/delete_model")
async def delete_model(request: Request):
    data = await request.json()
    model = data.get("model")
    try:
        if not model:return JSONResponse(content={"status":False,"msg":"Missing model parameter"})
        models_path = get_models_path()
        model_folder = os.path.join(models_path, model)
        if not os.path.exists(model_folder):return JSONResponse(content={"status":True,"msg":"Model folder does not exist"})
        # 删除模型文件夹及其内容
        for root, dirs, files in os.walk(model_folder, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(model_folder)
        return JSONResponse(content={"status":True,"msg":"Successfully deleted model folder"})
    except Exception as e:
        logger.exception(f"Error deleting model folder: {model}")
        return JSONResponse(content={"status":False,"msg":"Failed to delete model folder"})
@api_config.get("/model/labels")
def get_model_labels(model: str):
    try:
        labels = {}
        model_folder = os.path.join(get_models_path(), model)
        if not os.path.exists(model_folder):
            logger.error(f"Model folder does not exist: {model_folder}")
            return JSONResponse(content={"status":False,"msg":"Model folder does not exist"})
        label_file = os.path.join(model_folder, "cache.json")
        if not os.path.exists(label_file):
            logger.error(f"Label file does not exist: {label_file}")
            return JSONResponse(content={"status":False,"msg":"Label file does not exist"})
        cache_datas = JsonFile(label_file).read_json_file()
        if not cache_datas:
            logger.error(f"Cache data is empty: {label_file}")
            return JSONResponse(content={"status":False,"msg":"Label file data is empty"})
        labels = cache_datas.get("labeling")
        if not labels:
            logger.error(f"Labeling data is empty: {label_file}")
            return JSONResponse(content={"status":False,"msg":"Labeling data is empty"})
        return JSONResponse(content={"status":True,"datas": labels})
    except Exception as e:
        logger.exception(f"Error getting model labels")
        return JSONResponse(content={"status":False,"msg":"Failed to getting model labels"})
@api_config.post("/model/labels/set")
async def set_model_labels(request: Request):
    try:
        data = await request.json()
        model = data.get("model")
        labels = data.get("labels")
        if not model or not labels or len(labels) == 0:
            logger.error(f"Missing model or labels: {model}, {labels}")
            return JSONResponse(content={"status":False,"msg":"Missing parameters"})
        model_folder = os.path.join(get_models_path(), model)
        if not os.path.exists(model_folder):
            return JSONResponse(content={"status":False,"msg":"Model does not exist"})
        label_file = os.path.join(model_folder, "cache.json")
        json_file = JsonFile(label_file)
        cache_datas = json_file.read_json_file()
        cache_datas['labeling'] = labels
        json_file.write_json_file(cache_datas)
        return JSONResponse(content={"status":True,"msg":"Successfully set model labels"})
    except Exception as e:
        logger.exception(f"Error setting model labels")
        return JSONResponse(content={"status":False,"msg":"Failed to set model labels"})
@api_config.post("/set_config/paths")
async def set_config_paths(request: Request):
    try:
        data = await request.json()
        model_path = data.get("modelPath")
        results_path = data.get("resultPath")
        sops_path =data.get("sopPath")
        save_datasets = data.get("saveDetectionDatasets", False)
        if model_path and not os.path.exists(model_path):
            try:
                os.makedirs(model_path)
            except Exception as e:
                logger.error(f"Failed to create model path: {model_path}, error: {e}")
                return JSONResponse(content={"status":False,"msg":"Model path is not available"})
        if sops_path and not os.path.exists(sops_path):
            try:
                os.makedirs(sops_path)
            except Exception as e:
                logger.error(f"Failed to create sops path: {sops_path}, error: {e}")
                return JSONResponse(content={"status":False,"msg":"SOP path is not available"})
        if results_path and not os.path.exists(results_path):
            try:
                os.makedirs(results_path)
            except Exception as e:
                logger.error(f"Failed to create results path: {results_path}, error: {e}")
                return JSONResponse(content={"status":False,"msg":"Results path is not available"})
        config_data = get_main_config()
        config_data["paths"] = {
            "modelPath": model_path,
            "sopPath": sops_path,
            "resultPath": results_path,
            "saveDetectionDatasets": save_datasets
        }
        json_file = JsonFile(CONFIG_PATH)
        json_file.write_json_file(config_data)
        return JSONResponse(content={"status":True,"msg":"Successfully set paths"})
    except Exception as e:
        logger.exception(f"Error setting config paths")
        return JSONResponse(content={"status":False,"msg":"Failed to set paths"})
    
@api_config.post("/set_cap_resolutions")
async def set_cap_resolutions(request:Request):
    try:
        body = await request.json()
        cap_name = body.get("cap_name", "")
        if not cap_name:return {"status": False, "msg": "Camera name is required."}
        width = body.get("width", 0)
        height = body.get("height", 0)
        area = body.get("area", 0)
        clarity = body.get("clarity", 50)
        if not width or not height:return {"status": False, "msg": "Invalid resolution"}
        config_datas = get_main_config()
        if "cameraResolution" not in config_datas:config_datas["cameraResolution"] = {} 
        config_datas["cameraResolution"][cap_name] = {"width": width, "height": height,"area":area,"clarity":clarity}
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return {"status": True, "msg": "Resolution set successfully."}
    except Exception as e:
        logger.error(f"Error setting camera resolutions for {cap_name}: {e}")
        return {"status": False, "msg": str(e)}
@api_config.post("/set_resolutions/list")
async def set_resolutions_list(request:Request):
    try:
        body = await request.json()
        width = body.get("width", 0)
        height = body.get("height", 0)
        if not width or not height:return {"status": False, "msg": "Invalid resolution"}
        config_datas = get_main_config()
        resolutions = config_datas.get("resolutions", [])
        newResolution = [width, height]
        if newResolution in resolutions:return {"status": False, "msg": "Resolution already exists."}
        #将新的分辨率按宽度从小到大插入到resolutions中
        inserted = False
        for i, res in enumerate(resolutions):
            if newResolution[0] < res[0]:
                resolutions.insert(i, newResolution)
                inserted = True
                break
        if not inserted:
            resolutions.append(newResolution)
        config_datas["resolutions"] = resolutions
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return {"status": True, "msg": "Resolutions set successfully.","data":resolutions}
    except Exception as e:
        logger.error(f"Error setting resolutions: {e}")
        return {"status": False, "msg": str(e)}
@api_config.delete("/delete_resolution/list")
async def delete_resolution_list(request:Request):
    try:
        body = await request.json()
        width = body.get("width", 0)
        height = body.get("height", 0)
        config_datas = get_main_config()
        resolutions = config_datas.get("resolutions", [])
        targetResolution = [width, height]
        if targetResolution not in resolutions:
            return {"status": False, "msg": "Resolution not found."}
        resolutions.remove(targetResolution)
        config_datas["resolutions"] = resolutions
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return {"status": True, "msg": "Resolution deleted successfully.","data":resolutions}
    except Exception as e:
        logger.error(f"Error deleting resolution: {e}")
        return {"status": False, "msg": str(e)}
@api_config.post("/set_sop_config")
async def set_sop_config(request:Request):
    try:
        body = await request.json() 
        model_name = body.get("model", "")
        if not model_name:return {"status": False, "msg": "Model name is required."}
        sop_config = SopConfig()
        sop_config_datas = sop_config.get()
        existing_sop = sop_config_datas.get(model_name)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
        #这里要写当 existing_sop不存在时，设置 create_time 和 enabled 为 False 的逻辑；如果存在则将body的数据覆盖到existing_sop中，existing_sop中已经存在的不变
        if existing_sop:
            for key, value in existing_sop.items():
                if key not in body:
                    body[key] = value
        else:
            body["create_time"] = now
            body["enabled"] = False
        body["modify_time"] = now
        sop_config_datas[model_name] = body
        sop_config.set(sop_config_datas)
        return {"status": True,"datas":sop_config_datas, "msg": "SOP configuration set successfully."}
    except Exception as e:
        logger.error(f"Error setting SOP configuration: {e}")
        return {"status": False, "msg": str(e)}
@api_config.delete("/delete_sop_config")
async def delete_sop_config(request:Request):
    try:
        body = await request.json()
        model_name = body.get("model", "")
        if not model_name:return {"status": False, "msg": "Model name is required."}
        sop_config = SopConfig()
        sop_config_datas = sop_config.get()
        if not sop_config_datas or model_name not in sop_config_datas:
            return {"status": False, "msg": "SOP configuration not found for the specified model."}
        del sop_config_datas[model_name]
        sop_config.set(sop_config_datas)
        return {"status": True, "msg": "SOP configuration deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting SOP configuration: {e}")
        return {"status": False, "msg": str(e)}
@api_config.post("/update_sop_config")
async def update_sop_config(request:Request):
    try:
        body = await request.json()
        model_name = body.get("model", "")
        fields = body.get("fields", [])
        values = body.get("values", [])
        if not model_name:return {"status": False, "msg": "Model name is required."}
        if not fields or not values or len(fields) != len(values):return {"status": False, "msg": "Fields and values must be provided and have the same length."}
        sop_config_datas = SopConfig().get()
        if not sop_config_datas or model_name not in sop_config_datas:
            return {"status": False, "msg": "SOP configuration not found for the specified model."}
        for field, value in zip(fields, values):
            sop_config_datas[model_name][field] = value
            if field == "enabled" and value is True:
                for other_model in sop_config_datas:
                    if other_model != model_name:
                        sop_config_datas[other_model]["enabled"] = False
        SopConfig().set(sop_config_datas)
        return {"status": True, "msg": "SOP configuration updated successfully."}
    except Exception as e:
        logger.error(f"Error updating SOP configuration: {e}")
        return {"status": False, "msg": str(e)}
@api_config.post("/modify_config") 
async def modify_config(request:Request):
    """_summary_:通用配置更新接口，
    需要保证和配置的框架一致，否则会导致配置文件错乱

    Args:
        request (Request): body = await request.json()

    Returns:
        _type_: _description_
    """
    try:
        body = await request.json()
        updater = ConfigUpdater(get_main_config())
        updated_config = updater.update(body)
        JsonFile(CONFIG_PATH).write_json_file(updated_config)
        return {"status": True, "msg": "Configuration modified successfully."}
    except Exception as e:
        logger.error(f"Error modifying configuration: {e}")
        return {"status": False, "msg": str(e)}
