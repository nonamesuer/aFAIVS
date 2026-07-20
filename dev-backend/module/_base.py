import json
import os
import time
import ctypes
from copy import deepcopy
from pygrabber.dshow_graph import FilterGraph
graph = FilterGraph()
WEBSOCKET_CLIENTS = set()
CAP_STATUS = 0 #0：未启动，1:正常，2:重连中，3:重连失败
DETECTOR_STATUS = 0 #0：未启动，1:正常，2:重连中，3:重连失败
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
LIB_PATH = os.path.join(PARENT_DIR, "lib")
MODELS_PATH = os.path.join(PARENT_DIR, "models")
RESULTS_PATH = os.path.join(PARENT_DIR, "results")
STATIC_PATH = os.path.join(PARENT_DIR, "static")
CONFIG_PATH = os.path.join(STATIC_PATH, "config.json")
SOP_CONFIG_NAME = "sop_config.json"
MEDIAPIPE_MODEL_PATH = os.path.join(LIB_PATH, "hand_landmarker.task")
DEFAULT_RESOLUTIONS=[[320,240],[640,480],[800,600],[1024,768],[1280,720],[1280,960],[1600,1200],[1920,1080],[2048,1536],
        [2320,1744],[2560,1440],[3840,2160],[4160,2340]]
DEFAULT_MAIN_CONFIG = {
    "paths": {
        "modelPath": MODELS_PATH,
        "sopPath": STATIC_PATH,
        "resultPath": RESULTS_PATH,
        "saveDetectionDatasets": False
    },
    "resolutions": DEFAULT_RESOLUTIONS,
    "enableCamera":None,
    "cameraResolution": {},
    "boxStyle": {
        "boxThickness": 2,
        "fontThickness": 2,
        "fontScale": 0.5,
        "fromAreaFill": False,
        "targetAreaFill": False
    },
    "modbus": {
        "host": "127.0.0.1",
        "port": 502,
        "timeout": 3
    }
}
class JsonFile(object):
    def __init__(self, file_path):
        self.file =file_path
        if not os.path.exists(self.file):
            with open(self.file,'w',encoding="utf-8") as file:
                pass
    def read_json_file(self):
        with open(self.file,'r',encoding="utf-8") as file:
            json_str = file.read()
        if json_str == "":
            self.write_json_file({})
            return {}
        data = json.loads(json_str)
        return data
    def write_json_file(self,cache_data):
        while True:
            try:
                with open(self.file, 'w', encoding='utf-8') as file:
                    json.dump(cache_data, file, indent=4, ensure_ascii=False)
                break
            except PermissionError:
                # 如果文件被锁定，等待并重试
                time.sleep(0.5)  
class ConfigUpdater:
    """_summary_
    前端：

    const update_param = {
        "sop":{
        [modelName]:{
            enabled: value
        }
        }
    }

    调用：
    updater = ConfigUpdater(config_datas)
    result = updater.update(update_data)  

    Returns:
        _type_: _description_
    """
    VALID_KEYS = DEFAULT_MAIN_CONFIG

    def __init__(self, config):
        self.config = config
    
    def update(self, updates):
        return self._deep_update(self.config, updates, self.VALID_KEYS)
    
    def _deep_update(self, original, update, valid_keys=None):
        for key, value in update.items():
            if not self._is_valid_key(key, valid_keys):
                continue

            child_valid_keys = self._get_child_valid_keys(key, valid_keys)
            if isinstance(value, dict) and isinstance(original.get(key), dict):
                self._deep_update(original[key], value, child_valid_keys)
            else:
                original[key] = value
        return original

    def _is_valid_key(self, key, valid_keys):
        return valid_keys is None or key in valid_keys

    def _get_child_valid_keys(self, key, valid_keys):
        if not isinstance(valid_keys, dict):
            return None
        child_valid_keys = valid_keys.get(key)
        if child_valid_keys == {}:
            return None
        return child_valid_keys
    
    def get_config(self):
        return self.config
class CapStatus:
    def set(self,value):
        global CAP_STATUS
        CAP_STATUS = value

    def get(self):
        global CAP_STATUS
        return CAP_STATUS
class DetectorStatus:
    def set(self,value):
        global DETECTOR_STATUS
        DETECTOR_STATUS = value

    def get(self):
        global DETECTOR_STATUS
        return DETECTOR_STATUS
class SopConfig:
    
    def __init__(self):
        self.sop_config_path = os.path.join(self.get_sops_path(), SOP_CONFIG_NAME)
        if not os.path.exists(self.sop_config_path):
            JsonFile(self.sop_config_path).write_json_file({})
    def get_sops_path(self) -> str:
        path_config = get_main_config()
        paths = path_config.get("paths", {}) if path_config else {}
        sop_path = paths.get("sopPath") if isinstance(paths, dict) else None
        return sop_path if isinstance(sop_path, str) and sop_path else STATIC_PATH
    def get(self):
        return JsonFile(self.sop_config_path).read_json_file()
    
    def set(self, config):
        JsonFile(self.sop_config_path).write_json_file(config)
def get_camera_index(camera_name):
    devices = graph.get_input_devices()
    return devices.index(camera_name) if camera_name in devices else None

def get_display_name():
    GetUserNameEx = ctypes.windll.secur32.GetUserNameExW
    NameDisplay = 3  # 显示名称格式
    size = ctypes.pointer(ctypes.c_ulong(0))
    GetUserNameEx(NameDisplay, None, size)
    buffer = ctypes.create_unicode_buffer(size.contents.value)
    if GetUserNameEx(NameDisplay, buffer, size):return buffer.value
    return "User"

def get_main_config() -> dict:
    default_datas = deepcopy(DEFAULT_MAIN_CONFIG)
    if not os.path.exists(CONFIG_PATH):
        JsonFile(CONFIG_PATH).write_json_file(default_datas)
        return default_datas
    config_datas = JsonFile(CONFIG_PATH).read_json_file()
    if not config_datas:
        JsonFile(CONFIG_PATH).write_json_file(default_datas)
        return default_datas
    re_write = False
    for key, value in default_datas.items():
        if key not in config_datas:
            config_datas[key] = value
            re_write = True
    if re_write:JsonFile(CONFIG_PATH).write_json_file(config_datas)
    return config_datas

def get_models_path() -> str:
    path_config = get_main_config()
    paths = path_config.get("paths", {}) if path_config else {}
    model_path = paths.get("modelPath") if isinstance(paths, dict) else None
    return model_path if isinstance(model_path, str) and model_path else MODELS_PATH



async def send_websocket_json(message):
    """发送消息到所有WebSocket客户端"""
    for client in WEBSOCKET_CLIENTS:
        await client.send_json(message)

