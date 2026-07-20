import axios from "./request";
const base_url = "http://127.0.0.1:20253";
const wsBaseUrl = base_url.replace(/^http/i, 'ws'); // 把 HTTP 后端地址转换为 WebSocket 地址。
const requestWithPath = (path, type = "POST") => {
    return (data) => {
        const mergedObj = data;
        const requestPath = base_url + path
        switch (type.toUpperCase()) {
            case "GET":
                return axios.get(requestPath, { params: mergedObj });
            case "POST":
                return axios.post(requestPath, mergedObj);
            case "PUT":
                return axios.put(requestPath, mergedObj);
            case "DELETE":
                return axios.delete(requestPath, { data: mergedObj });
            case "PATCH":
                return axios.patch(requestPath, mergedObj);
            default:
                throw new Error(`Unsupported HTTP method: ${type}`);
        }
        // return (type == "POST") ? axios.post(requesrPath, mergedObj) : axios.get(requesrPath, { params: mergedObj });
    };
};
export default {
    baseUrl: base_url,
    getLoginUser: requestWithPath("/get_loginUser", "GET"),
    //检测相关
    startDetection: requestWithPath("/detection/start_detection", "GET"),
    pauseDetection: requestWithPath("/detection/pause_detection", "GET"),
    resumeDetection: requestWithPath("/detection/resume_detection", "GET"),
    stopDetection: requestWithPath("/detection/stop_detection", "GET"),
    resetDetection: requestWithPath("/detection/reset_detection", "POST"),
    statusDetection: requestWithPath("/detection/status", "GET"),
    getSopConfigration: requestWithPath("/detection/sop/configration", "GET"),
    webRTcOfferUrl:`${base_url}/detection/webrtc/offer`,
    resultWsUrl:`${wsBaseUrl}/detection/ws/result`, // 检测结果 WebSocket 地址。
    mjpegBaseUrl:`${base_url}/detection/server-stream`, // MJPEG 兜底视频流地址。
    //日志
    getLog: requestWithPath("/sys/error_log", "GET"),
    clearLog: requestWithPath("/sys/error_log/clear", "GET"),
    downloadLog: `${base_url}/sys/error_log/download`,
    //配置相关
    openModelFolder: requestWithPath("/open_models_folder", "GET"),
    getModels: requestWithPath("/get_models", "GET"),
    getDevice: requestWithPath("/get_device", "GET"),
    getModelLabels: requestWithPath("/model/labels", "GET"),
    setModelLabels: requestWithPath("/model/labels/set", "POST"),
    getConfig: requestWithPath("/get_config", "GET"),
    setConfigPath: requestWithPath("/set_config/paths", "POST"),
    setResolution:requestWithPath("/set_cap_resolutions","POST"),
    setResolutionsList:requestWithPath("/set_resolutions/list","POST"),
    deleteResolutionsList:requestWithPath("/delete_resolution/list","DELETE"),
    setSopConfig: requestWithPath("/set_sop_config", "POST"),
    deleteSopConfig: requestWithPath("/delete_sop_config", "DELETE"),
    updateSopConfig: requestWithPath("/update_sop_config", "POST"),
    modifyConfig: requestWithPath("/modify_config", "POST"),//配置更新公共接口
    deleteModel: requestWithPath("/delete_model", "DELETE"),//删除模型文件夹
    setBoxStyleConfig: requestWithPath("/set_box_style_config", "POST"),//设置标记框样式配置
    displayBoxStyleConfig: requestWithPath("/display_box_style_config", "POST"),//展示标记框样式配置
}