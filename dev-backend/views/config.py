import logging
import os
import numpy as np
import base64
import cv2
from fastapi.responses import JSONResponse  
from fastapi import APIRouter, Request,HTTPException,File, UploadFile
from module._base import CONFIG_PATH,DEFAULT_MAIN_CONFIG,SopConfig,get_models_path,JsonFile,get_main_config,DEFAULT_RESOLUTIONS,ConfigUpdater,DEFAULT_BOX_STYLE_CONFIG,DEFAULT_HAND_STYLE_CONFIG
from module._step_feedback import validate_sop_step_feedback_config
from module._box_style import normalize_area_fill_alpha
from module._hand_detection import HandTracker
from module._hand_style import normalize_hand_style_config
from datetime import datetime
from pydantic import BaseModel, Field
from pymodbus.client import ModbusTcpClient
logger = logging.getLogger(__name__)
api_config = APIRouter()


def _hand_preview_points() -> dict[str, list[tuple[float, float]]]:
    left_points = [
        (155, 300),
        (125, 270), (102, 240), (88, 210), (82, 180),
        (142, 250), (138, 205), (136, 160), (134, 115),
        (165, 245), (165, 192), (165, 140), (165, 92),
        (187, 250), (193, 205), (198, 163), (202, 125),
        (207, 260), (220, 225), (231, 195), (240, 168),
    ]
    right_points = [(640 - x, y) for x, y in left_points]
    return {"l": left_points, "r": right_points}


@api_config.get("/get_config")
def get_config():
    config_datas = get_main_config()
    sop_config = SopConfig()
    sop_config_datas = sop_config.get()
    if "resolutions" not in config_datas:
        config_datas["resolutions"] = DEFAULT_RESOLUTIONS
    return JSONResponse(content={"status": True, "datas": config_datas,"sops":sop_config_datas})
@api_config.post("/set_box_style_config")
async def set_box_style_config(request: Request):
    try:
        body = await request.json()
        box_style_config = body.get("boxStyle")
        if not box_style_config:return JSONResponse(content={"status": False, "msg": "Missing boxStyle parameter"})
        area_fill_alpha = box_style_config.get(
            "areaFillAlpha",
            DEFAULT_BOX_STYLE_CONFIG["areaFillAlpha"],
        )
        try:
            area_fill_alpha = float(area_fill_alpha)
        except (TypeError, ValueError):
            return JSONResponse(content={"status": False, "msg": "areaFillAlpha must be a number between 0 and 1"})
        if not np.isfinite(area_fill_alpha) or not 0 <= area_fill_alpha <= 1:
            return JSONResponse(content={"status": False, "msg": "areaFillAlpha must be between 0 and 1"})
        box_style_config = {
            **box_style_config,
            "areaFillAlpha": round(area_fill_alpha, 2),
        }
        config_datas = get_main_config()
        config_datas["boxStyle"] = box_style_config
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return JSONResponse(content={"status": True, "msg": "Box style configuration set successfully"})
    except Exception as e:
        logger.exception(f"Error setting box style configuration: {e}")
        return JSONResponse(content={"status": False, "msg": "Failed to set box style configuration"})
@api_config.post("/display_box_style_config")
async def display_box_style_config(request: Request):
    try:
        body = await request.json()
        box_style_config = body.get("boxStyle")
        if not box_style_config:return JSONResponse(content={"status": False, "msg": "Missing boxStyle parameter"})
        box_thickness = box_style_config.get("boxThickness", 3)
        font_thickness = box_style_config.get("fontThickness", 2)
        font_scale = box_style_config.get("fontScale", 0.5)
        from_area_fill = box_style_config.get("fromAreaFill", False)
        target_area_fill = box_style_config.get("targetAreaFill", False)
        area_fill_alpha = normalize_area_fill_alpha(
            box_style_config.get("areaFillAlpha"),
            DEFAULT_BOX_STYLE_CONFIG["areaFillAlpha"],
        )
        img = np.zeros((400, 400, 3), dtype=np.uint8)
        cv2.rectangle(img, (50, 50), (150,150), (0, 255, 0), thickness=box_thickness)
        (textSizeW, textSizeH), baseline = cv2.getTextSize('Example', cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
        cv2.putText(img, 'Example', (50, 50-textSizeH), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), thickness=font_thickness, lineType=cv2.LINE_AA)
        overlay = img.copy()
        if from_area_fill:
            cv2.rectangle(overlay, (200, 50), (300,150), (0, 255, 255), thickness=cv2.FILLED)
        if target_area_fill:
            cv2.rectangle(overlay, (50, 250), (150,350), (0, 0, 255), thickness=cv2.FILLED)
        if from_area_fill or target_area_fill:
            cv2.addWeighted(
                overlay,
                area_fill_alpha,
                img,
                1.0 - area_fill_alpha,
                0,
                dst=img,
            )
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


@api_config.post("/set_hand_style_config")
async def set_hand_style_config(request: Request):
    try:
        body = await request.json()
        hand_style_config = body.get("handStyle")
        if not isinstance(hand_style_config, dict):
            return JSONResponse(
                content={"status": False, "msg": "Missing handStyle parameter"}
            )
        try:
            hand_style_config = normalize_hand_style_config(
                hand_style_config,
                DEFAULT_HAND_STYLE_CONFIG,
                strict=True,
            )
        except ValueError as exc:
            return JSONResponse(content={"status": False, "msg": str(exc)})

        config_datas = get_main_config()
        config_datas["handStyle"] = hand_style_config
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return JSONResponse(
            content={
                "status": True,
                "msg": "Hand style configuration set successfully",
                "datas": hand_style_config,
            }
        )
    except Exception as exc:
        logger.exception(f"Error setting hand style configuration: {exc}")
        return JSONResponse(
            content={"status": False, "msg": "Failed to set hand style configuration"}
        )


@api_config.post("/display_hand_style_config")
async def display_hand_style_config(request: Request):
    try:
        body = await request.json()
        hand_style_config = body.get("handStyle")
        if not isinstance(hand_style_config, dict):
            return JSONResponse(
                content={"status": False, "msg": "Missing handStyle parameter"}
            )
        try:
            hand_style_config = normalize_hand_style_config(
                hand_style_config,
                DEFAULT_HAND_STYLE_CONFIG,
                strict=True,
            )
        except ValueError as exc:
            return JSONResponse(content={"status": False, "msg": str(exc)})

        image = np.full((360, 640, 3), 32, dtype=np.uint8)
        cv2.putText(
            image,
            "LEFT HAND",
            (95, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (230, 230, 230),
            2,
            lineType=cv2.LINE_AA,
        )
        cv2.putText(
            image,
            "RIGHT HAND",
            (405, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (230, 230, 230),
            2,
            lineType=cv2.LINE_AA,
        )
        HandTracker.draw_hands(
            image,
            _hand_preview_points(),
            hand_style_config,
        )

        encoded, buffer = cv2.imencode(
            ".webp",
            image,
            [int(cv2.IMWRITE_WEBP_QUALITY), 90],
        )
        if not encoded:
            raise RuntimeError("Failed to encode hand style preview")
        frame = f"data:image/webp;base64,{base64.b64encode(buffer).decode('utf-8')}"
        return JSONResponse(
            content={
                "status": True,
                "frame": frame,
                "msg": "Hand style preview generated successfully",
            }
        )
    except Exception as exc:
        logger.exception(f"Error displaying hand style configuration: {exc}")
        return JSONResponse(
            content={"status": False, "msg": "Failed to display hand style configuration"}
        )


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
        validation_error = validate_sop_step_feedback_config(body, get_main_config())
        if validation_error:
            return {"status": False, "msg": validation_error}
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
MAX_RESULT_FEEDBACK_ENDPOINTS = 5
MAX_HTTP_TRIGGER_PARAMETERS = 3
MAX_MODBUS_TRIGGER_SIGNALS = 3
MODBUS_BIT_TYPES = {"coil", "discreteInput"}
MODBUS_REGISTER_TYPES = {"holdingRegister", "inputRegister"}


def _is_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_detection_integration_config(body: dict) -> str:
    integration = body.get("detectionIntegration")
    if integration is None:
        return ""
    if not isinstance(integration, dict):
        return "detectionIntegration must be an object"

    triggers = integration.get("triggers")
    if triggers is not None:
        if not isinstance(triggers, dict):
            return "detectionIntegration.triggers must be an object"

        http_parameters = triggers.get("httpParameters")
        if http_parameters is not None:
            if not isinstance(http_parameters, list):
                return "triggers.httpParameters must be an array"
            if len(http_parameters) > MAX_HTTP_TRIGGER_PARAMETERS:
                return f"A maximum of {MAX_HTTP_TRIGGER_PARAMETERS} HTTP trigger parameters is allowed"
            parameter_names = set()
            for parameter in http_parameters:
                if not isinstance(parameter, str):
                    return "Each HTTP trigger parameter must be a string"
                name = parameter.strip()
                if not name:
                    return "HTTP trigger parameter name cannot be empty"
                if name in parameter_names:
                    return "HTTP trigger parameter names must be unique"
                parameter_names.add(name)
        if triggers.get("httpApi") is True and not http_parameters:
            return "At least one HTTP trigger parameter is required when HTTP API trigger is enabled"

        scanner_length = triggers.get("usbScannerLength")
        if scanner_length is not None:
            if not isinstance(scanner_length, dict):
                return "triggers.usbScannerLength must be an object"
            min_length = scanner_length.get("min")
            max_length = scanner_length.get("max")
            if not _is_integer(min_length) or not _is_integer(max_length):
                return "USB scanner minimum and maximum lengths must be integers"
            if min_length < 1 or max_length < min_length or max_length > 9999:
                return "USB scanner length requires 1 <= min <= max <= 9999"

        modbus_signals = triggers.get("modbusSignals")
        if modbus_signals is not None:
            if not isinstance(modbus_signals, list):
                return "triggers.modbusSignals must be an array"
            if len(modbus_signals) > MAX_MODBUS_TRIGGER_SIGNALS:
                return f"A maximum of {MAX_MODBUS_TRIGGER_SIGNALS} Modbus trigger signals is allowed"
            for signal in modbus_signals:
                if not isinstance(signal, dict):
                    return "Each Modbus trigger signal must be an object"
                slave_address = signal.get("slaveAddress")
                address = signal.get("address")
                data_type = signal.get("dataType")
                trigger_value = signal.get("triggerValue")
                if not _is_integer(slave_address) or not 1 <= slave_address <= 247:
                    return "Modbus slave address must be an integer between 1 and 247"
                if not _is_integer(address) or not 0 <= address <= 65535:
                    return "Modbus trigger address must be an integer between 0 and 65535"
                if data_type in MODBUS_BIT_TYPES:
                    if not isinstance(trigger_value, bool):
                        return "Modbus coil and discrete input trigger values must be boolean"
                elif data_type in MODBUS_REGISTER_TYPES:
                    if not _is_integer(trigger_value) or not 0 <= trigger_value <= 65535:
                        return "Modbus register trigger value must be an integer between 0 and 65535"
                else:
                    return "Unsupported Modbus data type"
        if triggers.get("modbus") is True and not modbus_signals:
            return "At least one Modbus trigger signal is required when Modbus trigger is enabled"

    result_feedback = integration.get("resultFeedback")
    if result_feedback is None:
        return ""
    if not isinstance(result_feedback, dict):
        return "resultFeedback must be an object"

    endpoints = result_feedback.get("endpoints")
    if endpoints is None:
        return ""
    if not isinstance(endpoints, list):
        return "resultFeedback.endpoints must be an array"
    if len(endpoints) > MAX_RESULT_FEEDBACK_ENDPOINTS:
        return f"A maximum of {MAX_RESULT_FEEDBACK_ENDPOINTS} result feedback endpoints is allowed"
    if any(not isinstance(endpoint, dict) for endpoint in endpoints):
        return "Each result feedback endpoint must be an object"
    return ""


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
        if not isinstance(body, dict):
            return {"status": False, "msg": "Configuration payload must be an object"}
        validation_error = validate_detection_integration_config(body)
        if validation_error:
            return {"status": False, "msg": validation_error}
        updater = ConfigUpdater(get_main_config())
        updated_config = updater.update(body)
        JsonFile(CONFIG_PATH).write_json_file(updated_config)
        return {"status": True, "msg": "Configuration modified successfully."}
    except Exception as e:
        logger.error(f"Error modifying configuration: {e}")
        return {"status": False, "msg": str(e)}
class ModbusConnectionRequest(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    timeout: float = Field(gt=0, le=60)
@api_config.post("/modbus/test_connection")
def test_modbus_connection(payload: ModbusConnectionRequest):
    """测试指定地址能否建立 Modbus TCP 连接，不读取任何寄存器。"""
    host = payload.host.strip()
    if not host:return JSONResponse(content={"status": False, "msg": "Modbus host is required"})
    client = ModbusTcpClient(host=host,port=payload.port,timeout=payload.timeout)
    try:
        if client.connect():return JSONResponse(content={"status": True,"msg": f"Connected to Modbus TCP server {host}:{payload.port}",})
        return JSONResponse(content={"status": False,"msg": f"Unable to connect to Modbus TCP server {host}:{payload.port}"})
    except Exception as exc:
        logger.exception("Failed to test Modbus TCP connection to %s:%s", host, payload.port)
        return JSONResponse(content={"status": False, "msg": str(exc)})
    finally:
        try:
            client.close()
        except Exception:
            logger.exception("Failed to close Modbus TCP test client")

@api_config.post("/http/response_test")
async def http_response_test(request: Request):
    """测试 HTTP 响应，返回请求的 JSON 数据和状态码。"""
    try:
        body = await request.json()
        print("body",body)
        return JSONResponse(content={"status": True, "msg": "HTTP response test successful", "data": body})
    except Exception as e:
        logger.error(f"Error in HTTP response test: {e}")
        return JSONResponse(content={"status": False, "msg": str(e)})
