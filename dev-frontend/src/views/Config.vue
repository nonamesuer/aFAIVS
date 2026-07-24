<template>
    <div class="layout-container">
        <div class="el-main-header" ref="device1Ref">
            <div class="el-main-header-left">
              <el-form label-position="top" size="large" :inline="true">
                  <el-button type="primary" class="btn-modelfolder" :title="$t('button.openmodellib')" circle :icon="FolderOpened" style="font-size: 24px;" @click="openModelFolder" />
                  <el-form-item :label="$t('config.models')" style="margin-right: 0">
                    <el-select v-model="currentMainModel" :placeholder="t('interacting.select') + t('config.model')"
                        @change="handleChangeMainModel">
                        <el-option v-for="(value, model, index) in modelsList" :key="index" :label="model" :value="model" :disabled="!value" />
                    </el-select>
                  </el-form-item>
                  <el-popover :visible="labelColorVisible" placement="bottom" width="300" trigger="click" popper-style="height: 400px">
                    <div style="width: 100%; max-height: 350px; overflow-y: auto">
                        <el-row v-for="(color, label, index) in currentMainLabels" :key="index">
                        <el-col :span="16">{{ label }}</el-col>
                        <el-col :span="6">
                            <el-color-picker v-model="currentMainLabels[label]"
                            @active-change="(val) => (currentMainLabels[label] = val)" color-format="hex" />
                        </el-col>
                        </el-row>
                        <div style=" text-align: right; position: absolute; bottom: 0; right: 20px; margin-top: 10px;">
                        <el-button size="small" type="primary" @click="handleChangeColor">{{ $t("button.confirm") }}</el-button>
                        <el-button size="small" type="primary" plain @click="labelColorVisible = false">{{ $t("button.close") }}</el-button>
                        </div>
                    </div>
                    <template #reference>
                        <el-button v-show="currentMainModel" :title="$t('config.labels')" :icon="Brush" type="primary"
                        class="btn_open-changecolor" circle @click="labelColorVisible = true" />
                    </template>
                  </el-popover>
                  <el-form-item :label="$t('config.cameras')" style="margin-left: 30px;">
                    <el-select v-model="currentMainCamera" :placeholder="t('interacting.select') + t('config.camera')" @change="handleChangeMainCamera">
                        <el-option v-for="(camera, index) in cameraList" :key="camera" :label="camera" :value="index">
                          <el-row :gutter="10">
                              <el-col :span="16"><span >{{ camera }}</span></el-col>
                              <el-col :span="4" style="display: flex;align-items: center; justify-content: center;"><el-icon @click.stop="displayCapSteram(index)" size="20px"><VideoPlay /></el-icon></el-col>
                              <el-col :span="4" style="display: flex; align-items: center; justify-content: center;"><el-icon @click.stop="resolutionsDrawer(camera)" size="20px"><Setting /></el-icon></el-col>
                              
                          </el-row>
                          <!-- <div style="display: flex;align-items: start; justify-content: space-between;">
                            <span >{{ camera }}</span>
                            <span style=" display: flex; align-items: center; height: 100%;" @click.stop="resolutionsDrawer(camera)"><el-icon color="var(--bs-primary-color)" size="20px"><Setting /></el-icon></span>
                            <span><el-icon size="20px"><VideoPlay /></el-icon></span>
                          </div>   -->
                          
                          </el-option>
                    </el-select>
                  </el-form-item>
              </el-form>
            </div>
        <!-- <div class="el-main-header-right">
        <el-dropdown  trigger="click"  @command="handleConfigDropdownCommand"  style="cursor: pointer">
            <el-button type="primary" :icon="MoreFilled" circle style="font-size: 24px;"></el-button>
            <template #dropdown>
            <el-dropdown-menu>
                <el-dropdown-item :icon="Download" command="download">{{ t('button.downloadconfig') }}</el-dropdown-item>
                <el-dropdown-item :icon="Upload" command="upload">{{ t('button.uploadconfig') }}</el-dropdown-item>
            </el-dropdown-menu>
            </template>
        </el-dropdown>
        </div> -->
        </div>
        <div class="el-main-body" :style="{ height: elVideoStreamH }">
            <!-- 公共配置入口 -->
            <el-divider content-position="left">
                <template #default>
                    <div style="font-weight: 900">{{ $t("config.common_config") }}</div>
                </template>
            </el-divider>
            <div class="common-config-grid">
                <div class="common-config-entry" @click="pathDialogVisible = true">
                    <el-icon class="common-config-icon"><FolderOpened /></el-icon>
                    <span class="common-config-title">{{ $t('config.path_config') }}</span>
                    <span class="common-config-description">{{ $t('config.path_config_description') }}</span>
                </div>

                <div class="common-config-entry" @click="boxStyleVisible = true">
                    <el-icon class="common-config-icon"><Crop /></el-icon>
                    <span class="common-config-title">{{ $t('button.title.box_style_setting') }}</span>
                    <span class="common-config-description">{{ $t('config.box_style_description') }}</span>
                </div>
                <div class="common-config-entry" @click="modbusDialogVisible = true">
                    <el-icon class="common-config-icon"><Connection /></el-icon>
                    <span class="common-config-title">{{ $t('config.modbus_config') }}</span>
                    <span class="common-config-description">{{ $t('config.modbus_config_description') }}</span>
                </div>
                <div class="common-config-entry" @click="integrationDialogVisible = true">
                    <el-icon class="common-config-icon"><SetUp /></el-icon>
                    <span class="common-config-title">{{ $t('config.detection_integration_config') }}</span>
                    <span class="common-config-description">{{ $t('config.detection_integration_config_description') }}</span>
                </div>
            </div>
            <!-- 工序指导配置 -->
            <el-divider content-position="left">
                <template #default>
                    <div style="font-weight: 900">{{ $t("config.sop_config") }}</div>
                </template>
            </el-divider>
            <div class="sop-config-container">
              <div class="sop-card" v-for="(conf,modelName,index) in sopConfigDatas" :key="index">
                <div class="card-color-bar" :style="{ backgroundColor: missingModels.includes(modelName) ? 'var(--bs-danger-color)' : !modelsList[modelName] ? 'var(--bs-warning-color)' : (conf.enabled ? 'var(--bs-success-color)' : 'var(--bs-info-color)') }"></div>
                <div class="card-content">
                  <div class="card-content-top">
                    <div class="card-content-top-left">
                      <el-checkbox size="large" label="" @change="(value) => handleChangeEnable(value, modelName)" v-model="conf.enabled" :disabled="missingModels.includes(modelName) || !modelsList[modelName]"></el-checkbox>
                      <div class="card-content-top-left-title">
                        <div class="subtitle">{{ $t('config.model') }}</div>
                        <div class="title">{{ modelName }}</div>
                      </div>
                    </div>
                    <div class="card-content-top-right">
                      <el-icon size="24" style="cursor: pointer;"  @click="handelEditSop(modelName)"><Edit /></el-icon>
                      <el-icon size="24" style="cursor: pointer;" @click="handelDeleteSop(modelName)"><Delete /></el-icon>
                    </div>

                  </div>
                  <div class="card-content-info">
                    <div>
                        <div class="label">{{ $t('config.confidence') }}</div>
                        <div class="value">{{ conf.confidence }}</div>
                    </div>
                    <div>
                        <div class="label">{{ $t('config.sop_step_config.step_count') }}</div>
                        <div class="value">{{ conf.steps.length }}</div>
                    </div>
                  </div>
                  <div class="card-content-description">
                    <div class="label">{{ $t('config.sop_step_config.latestupdatetime') }}</div>
                        <div class="value">{{ conf.modify_time }}</div>
                  </div>
                </div>

              </div>
              
            </div>
            <div>
                <el-button type="primary" plain class="mt-4" style="width: 100%; margin-top: 10px" @click="handleAddSOP">{{ $t("button.new") + " " + $t("config.sop_config") }}</el-button>
            </div>
        </div>
        <!-- 摄像头预览 -->
        <el-dialog v-model="configCameraVisible" modal-class="bs-shade" :title="cameraList[currentMainCamera] + resolutionsDes" width="50%"
            destroy-on-close @closed="configCameraDialogClosed" draggable :z-index="99999">
            <div class="video-wrapper">
            <div class="video-container">
                <img id="video-stream" src="" />
            </div>
            </div>
        </el-dialog>
        <ResolutionDrawer
            v-model:visible="resolutionsDrawerVisible"
            :resolutionForm="resolutionForm"
            :resolutionsList="resolutionsList"
            :defaultResolution="defaultResolution"
            
            @submitResolution="handleSubmitResolution"
            @addResolution="handleAddResolution"
            @deleteResolution="handleDeleteResolution"
        />
        <SopDialog 
            v-model:visible="sopDialogVisible"
            :modelCameraForm="modelCameraForm"
            :modelsList="modelsList"
            :currentMainLabels="currentMainLabels"
            :steps="editSteps"
            :resultFeedbackConfig="detectionIntegrationConfig.resultFeedback"
            @close="handleCloseSignalSet"
            @save="handleSavePositionRow"
            @modelChanged="(model) => handleChangeMainModel(model)"
        />
        <PathDialog
          v-model:visible="pathDialogVisible"
          v-model:path-config="pathConfig"
          @saved="getModels"
        />
        <BoxStyleDrawer
          v-model:visible="boxStyleVisible"
          v-model:box-style-config="boxStyleConfig"
        />
        <ModbusDialog
          v-model:visible="modbusDialogVisible"
          v-model:modbus-config="modbusConfig"
        />
        <DetectionIntegrationDialog
          v-model:visible="integrationDialogVisible"
          v-model:integration-config="detectionIntegrationConfig"
        />
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted,onBeforeMount,watch, nextTick, reactive, computed, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";
import { useAppStore } from "@/stores/store";
import { ElMessage, FormInstance, FormRules } from "element-plus";
import { FolderOpened,Brush,Crop,Connection,SetUp } from "@element-plus/icons-vue";
import { MesAlertWTitle, MesConfirmWTitle } from "@/assets/js/secondpk";
import api from "@/api/index";
import SopDialog from "@/components/SopDialog.vue";
import ResolutionDrawer from "@/components/ResolutionDrawer.vue";
import BoxStyleDrawer from "@/components/BoxStyleDrawer.vue";
import PathDialog from "@/components/PathDIalog.vue";
import ModbusDialog from "@/components/ModbusDialog.vue";
import DetectionIntegrationDialog from "@/components/DetectionIntegrationDialog.vue";
const appStore = useAppStore();
const { t } = useI18n();
const device1Ref = ref(null);
const elVideoStreamH = ref("0px");
const videoStreamHeight = () => { elVideoStreamH.value = `calc(100% - ${device1Ref.value.offsetHeight}px`; };
const currentMainModel = ref('');
const modelsList = ref({}); 
const cameraList = ref<string[]>([]);
const labelColorVisible = ref(false);
const currentMainLabels = ref<Record<string, string>>({});
const currentMainCamera = ref(null);
const configCameraVisible = ref(false);
const ws = ref(null);
//分辨率
const resolutionsDes = ref("");
const resolutionsList = ref<number[][]>([]);
const cameraResolution = ref<Record<string, { width: number; height: number; area: number; clarity: number }>>({});
const defaultResolution = ref({ width: 640, height: 480, area: 640, clarity: 50 });
const resolutionForm = reactive({ resolutions: "", area: 640, clarity: 50 });
const resolutionsDrawerVisible = ref(false);
//路径
const pathConfig = ref({ modelPath: "",sopPath:"", resultPath: "", saveDetectionDatasets: false });
const pathDialogVisible = ref(false);
// SOP配置
const sopDialogVisible = ref(false);
const sopConfigDatas = ref({});
const editSteps = ref([]);
const missingModels = ref<string[]>([]);//检查SOP配置中的模型是否都存在
// 边框样式
const boxStyleVisible = ref(false);
const boxStyleConfig = ref({
  boxThickness: 2,
  fontThickness: 2,
  fontScale: 0.5,
  fromAreaFill: false,
  targetAreaFill: false,
  areaFillAlpha: 0.5,
});
// Modbus TCP
const modbusDialogVisible = ref(false);
const modbusConfig = ref({
  host: "127.0.0.1",
  port: 502,
  timeout: 3,
});
// 检测触发与结果反馈
const integrationDialogVisible = ref(false);
interface DetectionIntegrationConfig {
  triggers: {
    httpApi: boolean;
    httpParameters: string[];
    usbScanner: boolean;
    usbScannerLength: {
      min: number;
      max: number;
    };
    modbus: boolean;
    modbusSignals: Array<{
      slaveAddress: number;
      dataType: "coil" | "discreteInput" | "holdingRegister" | "inputRegister";
      address: number;
      triggerValue: boolean | number;
    }>;
  };
  resultFeedback: {
    enabled: boolean;
    endpoints: Array<{
      name: string;
      url: string;
      enabled: boolean;
    }>;
  };
}
const detectionIntegrationConfig = ref<DetectionIntegrationConfig>({
  triggers: {
    httpApi: false,
    httpParameters: [],
    usbScanner: false,
    usbScannerLength: {
      min: 1,
      max: 128,
    },
    modbus: false,
    modbusSignals: [],
  },
  resultFeedback: {
    enabled: false,
    endpoints: [],
  },
});
// 参数配置相关
const signalSetVisible = ref(false);
const modelCameraForm = ref({
  model: "",
  confidence: 50,
});
onBeforeMount(()=>{
  getDevice();
})
onMounted(() => {
    videoStreamHeight();
    
    getConfig(); 
    getModels();
    
    
});
watch(()=>modelsList.value,()=>{
  checkSopConfigModelsExist();
});

//头部组件
/**-----------初始化---------- */
const getConfig = () => {
  appStore.setLoading(true);
  api.getConfig().then((res) => {
    const resData = res.data;
    if (!resData.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failed_get_config"), resData.msg, "OK");
    const datas = resData.datas;
    sopConfigDatas.value = resData.sops || {};
    if ("paths" in datas) {
      const { modelPath = "", sopPath = "", resultPath = "", saveDetectionDatasets = false } = datas.paths;
      pathConfig.value = { ...pathConfig.value, modelPath, sopPath, resultPath, saveDetectionDatasets };
    };
    if (datas.boxStyle) {boxStyleConfig.value = {...boxStyleConfig.value,...datas.boxStyle, }};
    if (datas.modbus) {modbusConfig.value = {...modbusConfig.value,...datas.modbus, }};
    if (datas.detectionIntegration) {
      const triggerConfig = datas.detectionIntegration.triggers || {};
      detectionIntegrationConfig.value = {
        triggers: {
          ...detectionIntegrationConfig.value.triggers,
          ...triggerConfig,
          httpParameters: Array.isArray(triggerConfig.httpParameters)
            ? triggerConfig.httpParameters.slice(0, 3).map((parameter: unknown) => {
                if (typeof parameter === "string") return parameter;
                if (parameter && typeof parameter === "object" && "name" in parameter) {
                  return String(parameter.name || "");
                }
                return "";
              })
            : [],
          usbScannerLength: {
            ...detectionIntegrationConfig.value.triggers.usbScannerLength,
            ...(triggerConfig.usbScannerLength || {}),
          },
          modbusSignals: Array.isArray(triggerConfig.modbusSignals)
            ? triggerConfig.modbusSignals.slice(0, 3)
            : [],
        },
        resultFeedback: {
          ...detectionIntegrationConfig.value.resultFeedback,
          ...(datas.detectionIntegration.resultFeedback || {}),
          endpoints: Array.isArray(datas.detectionIntegration.resultFeedback?.endpoints)
            ? datas.detectionIntegration.resultFeedback.endpoints.slice(0, 5)
            : [],
        },
      };
    };
    if("cameraResolution" in datas){ cameraResolution.value = datas.cameraResolution; };
    if("enableCamera" in datas){ 
      let index = cameraList.value.indexOf(datas.enableCamera);
      if (index !== -1) {
        currentMainCamera.value = index;
      }
    }
    // if ("modbus" in datas) {
    //   const { host = "127.0.0.1", port = "502", timeout = 3 } = datas.modbus;
    //   modbusBasicForm.value = { ...modbusBasicForm.value, host, port, timeout };
    // }
    // if ("parameters" in datas) { positionTable.value = datas.parameters || []; }
    if ("resolutions" in datas) { resolutionsList.value = datas.resolutions || []; }
    // if("skipFramesNum" in datas){ skipFramesNum.value = datas.skipFramesNum; }
    
  })
    .catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failed_get_config"), error.message, "OK"))
    .finally(() => { appStore.setLoading(false); });
};
const getModels = () => {
  appStore.setLoading(true);
  api.getModels().then((res) => {
    const resData = res.data;
    if (!resData.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedgetmodels"), resData.msg, "OK");
    modelsList.value = resData.datas;
  })
    .catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedgetmodels"), error.message, "OK"))
    .finally(() => { appStore.setLoading(false); });
};
const getDevice = () => {
  appStore.setLoading(true);
  api.getDevice().then((res) => {
    cameraList.value = res.data.camera;
  })
    .catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failed_get_device_title"), error.message, "OK"))
    .finally(() => { appStore.setLoading(false); });
};
const openModelFolder = () => {
  api.openModelFolder().then((res) => {
    if (!res.data.status) MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedopenmodelsfolder"), res.data.msg, "OK");
  }).catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedopenmodelsfolder"), error.message, "OK"));
};
const handleChangeMainModel = (modelName: string, edit = false) => {
  appStore.setLoading(true);
  api.getModelLabels({ model: modelName }).then((res) => {
    if (!res.data.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedgetlabels"), res.data.msg, "OK");
    currentMainLabels.value = res.data.datas;
    if (signalSetVisible.value && !edit) {
      console.log("这里需要添加逻辑")
    }
  }).catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedgetlabels"), error.message, "OK"))
    .finally(() => { appStore.setLoading(false); });
};
const handleChangeColor = () => {
  appStore.setLoading(true);
  api.setModelLabels({ model: currentMainModel.value, labels: currentMainLabels.value }).then((res) => {
    if (!res.data.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedmodify"), res.data.msg, "OK");
    labelColorVisible.value = false;
    ElMessage.success(t("message.success"));
  }).catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedmodify"), error.message, "OK"))
    .finally(() => { appStore.setLoading(false); });
};
const handleChangeMainCamera = (index: number) => {
  const capName = cameraList.value[index];
  appStore.setLoading(true); 
  api.modifyConfig({ enableCamera: capName }).then((res) => {
    if (!res.data.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedenabled"), res.data.msg, "OK");
    ElMessage.success(t("message.messagetext.successenbaled"));
  }).catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedenabled"), error.message, "OK"))
    .finally(() => { appStore.setLoading(false); });
};
const displayCapSteram = (index: number) => {
  currentMainCamera.value = index;
  configCameraVisible.value = true;
  const capName = cameraList.value[index];
  const capArea = cameraResolution.value[capName];
  resolutionsDes.value = capArea ? ` [${capArea.width}x${capArea.height}_(${capArea.area})]` : "";
  nextTick(() => videoStream());
  
};
const configCameraDialogClosed = () => {
  ws.value.send(JSON.stringify({ action: "CLOSE" }));
  if (ws.value) {
    ws.value.close();
    ws.value = null;
  }
  currentMainCamera.value = null;
  const img = document.getElementById("video-stream");
  img.src = "";
};
const videoStream = () => {
  ws.value = new WebSocket(`ws://localhost:${appStore.servicePort}/ws/video_streaming?camera_id=${currentMainCamera.value}`);
  const MAGIC_CAMERA = 0xffff0000;
  ws.value.binaryType = "arraybuffer";
  const img = document.getElementById("video-stream");
  ws.value.onmessage = async (event) => {
    const buffer = new Uint8Array(event.data);
    const magic = new DataView(buffer.buffer).getUint32(0);
    const payload = buffer.slice(4); // 去掉4字节头
    if (magic === MAGIC_CAMERA) {
      const blob = new Blob([payload], { type: "image/jpeg" });
      let url = URL.createObjectURL(blob);
      const imgToUpdate = img;
      imgToUpdate.src = url;
      // 图片加载完成后撤销 URL
      imgToUpdate.onload = () => { URL.revokeObjectURL(url); };
      // 处理加载失败的情况
      imgToUpdate.onerror = () => { URL.revokeObjectURL(url); };
    }
  };
};
//分辨率
const temSetResolutionCapName = ref("");
const resolutionsDrawer = (cameraName: string) => {
    temSetResolutionCapName.value = cameraName;
  const capArea = cameraResolution.value[cameraName];
  resolutionsDes.value = capArea ? ` [${capArea.width}x${capArea.height}_(${capArea.area})]` : "";
  resolutionForm.resolutions = capArea ? `${capArea.width}x${capArea.height}` : "";
  resolutionForm.area = capArea ? capArea.area : 0;
  resolutionForm.clarity = capArea ? capArea.clarity : 50;
  resolutionsDrawerVisible.value = true;
};
const handleSubmitResolution=(data: { resolutions: string; area: number; clarity: number })=>{
    const [width, height] = data.resolutions.split("*").map(Number);
    appStore.setLoading(true);
    api.setResolution({cap_name: temSetResolutionCapName.value,width, height,area: data.area,clarity: data.clarity,}).then((res) => {
        if (!res.data.status) return ElMessage({ message: res.data.msg, type: "error" });
        defaultResolution.value = { width, height, area: data.area, clarity: data.clarity };
        cameraResolution.value[temSetResolutionCapName.value] = { width, height, area: data.area, clarity: data.clarity };
        resolutionsDes.value = ` [${width}x${height}_(${data.area})]`;
        resolutionForm.resolutions = `${width}*${height}`;
        resolutionForm.area = data.area;
        resolutionForm.clarity = data.clarity;
        resolutionsDrawerVisible.value = false;
        ElMessage.success(t("message.messagetext.successsave"));
    }).catch((err) => {
        MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedsave"), err.message || t("message.messagetext.error_service"));
    }).finally(() => { appStore.setLoading(false); });
}
const handleAddResolution=(data: { width: number; height: number })=>{
    appStore.setLoading(true);
    api.setResolutionsList({ width: data.width, height: data.height }).then((res) => {
        if (!res.data.status) return ElMessage({ message: res.data.msg, type: "error" });
        resolutionsList.value = res.data.data;
        ElMessage.success(t("message.messagetext.successadd"));
    }).catch((err) => {
        MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedadd"), err.message || t("message.messagetext.error_service"));
    }).finally(() => { appStore.setLoading(false); });
}
const handleDeleteResolution=(resolutionStr: string)=>{
    const [widthStr, heightStr] = resolutionStr.split("*");
    const width = Number(widthStr);
    const height = Number(heightStr);
    MesConfirmWTitle("warning", t("message.warning"), `${t("message.messagetext.askdelete")}[${resolutionStr}]`, "", t("button.confirm"), t("button.cancel"))
        .then(() => {
        appStore.setLoading(true);
        api.deleteResolutionsList({ width, height }).then((res) => {
            if (!res.data.status) return ElMessage({ message: res.data.msg, type: "error" });
            resolutionsList.value = res.data.data;
            ElMessage.success(t("message.messagetext.successdelete"));
        }).catch((err) => {
            MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), err.message || t("message.messagetext.error_service"));
        }).finally(() => { appStore.setLoading(false); });
        }).catch(() => {});
}
//SOP配置
const handleAddSOP = ()=>{
    sopDialogVisible.value = true;
}
const handleCloseSignalSet = () => {
  sopDialogVisible.value = false;
  editSteps.value = [];
  modelCameraForm.value.model = "";
  modelCameraForm.value.confidence = 50;
};

const handleSavePositionRow = (data: any) => {
  // 这里可以处理保存逻辑，例如调用 API 保存数据
  sopDialogVisible.value = false;
  appStore.setLoading(true);
  api.setSopConfig(data).then((res) => {
    const resData = res.data;
    if (!resData.status) return ElMessage({ message: resData.msg, type: "error" });
    sopConfigDatas.value = resData.datas;
    ElMessage.success(t("message.messagetext.successsave"));
  }).catch((err) => {
    MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedsave"), err.message || t("message.messagetext.error_service"));
  }).finally(() => { appStore.setLoading(false); });
  
};
const handelDeleteSop = (modelName: string) => {
  MesConfirmWTitle("warning", t("message.warning"), `${t("message.messagetext.askdelete")}[${modelName}]`, "", t("button.delete"), t("button.cancel"))
    .then(() => {
      appStore.setLoading(true);
      api.deleteSopConfig({ model: modelName }).then((res) => {
        if (!res.data.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), res.data.msg, "OK");
        delete sopConfigDatas.value[modelName];
        MesConfirmWTitle("info", t("message.messagetext.successdelete"), t("message.messagetext.modeldelete"),t('message.messagetext.modeldeleteconfirm'),t("button.delete"), t("button.cancel")).then(()=>{
          api.deleteModel({ model: modelName }).then((resp) => {
            if (!resp.data.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), resp.data.msg, "OK");
            delete modelsList.value[modelName];
            ElMessage.success(t("message.messagetext.successdelete"));
          }).catch((err) => {
            MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), err.message || t("message.messagetext.error_service"));
          }).finally(() => { appStore.setLoading(false); });
        }).catch(() => {});
        ElMessage.success(t("message.messagetext.successdelete"));
      }).catch((err) => {
        MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), err.message || t("message.messagetext.error_service"));
      }).finally(() => { appStore.setLoading(false); });
    }).catch(() => {});
};

const handelEditSop = (modelName: string) => {
  if(!modelsList.value[modelName]) return ElMessage.error(t("message.messagetext.modelconfigerror"));  
  sopDialogVisible.value = true;
  handleChangeMainModel(modelName);
  modelCameraForm.value.model = modelName;
  const cof = sopConfigDatas.value[modelName];
  modelCameraForm.value.confidence = cof.confidence * 100;
  if (cof) {
    editSteps.value = cof.steps || [];
  }
};
//检查SOP配置中的模型是否都存在

const checkSopConfigModelsExist = () => {
  const existingModels = Object.keys(modelsList.value);
  const sopModels = Object.keys(sopConfigDatas.value);
  missingModels.value = sopModels.filter(model => !existingModels.includes(model));
};
const handleChangeEnable = (value: boolean, modelName: string) => {
  const conf = sopConfigDatas.value[modelName];
  if (!conf) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedmodify"), t("message.messagetext.refreshpage"), "OK");
  if(value){
    const enabledModels = Object.keys(sopConfigDatas.value).filter(model => sopConfigDatas.value[model].enabled && model !== modelName);
    if(enabledModels.length > 0){
      for (const enabledModel of enabledModels) {
        sopConfigDatas.value[enabledModel].enabled = false;
      }
    }
  }
  appStore.setLoading(true);
  api.updateSopConfig({ model: modelName, fields:["enabled"], values: [value] }).then((res) => {
    if (!res.data.status) return MesAlertWTitle("error", t("message.error"), (value)?t("message.messagetext.failedenabled"):t("message.messagetext.faileddisabled"), res.data.msg, "OK");
    conf.enabled = value;
    ElMessage.success((value)?t("message.messagetext.successenbaled"):t("message.messagetext.successdisabled"));
  }).catch((err) => {
    MesAlertWTitle("error", t("message.error"), (value)?t("message.messagetext.failedenabled"):t("message.messagetext.faileddisabled"), err.message || t("message.messagetext.error_service"));
  }).finally(() => { appStore.setLoading(false); });

  
};
</script>
<style scoped>
.layout-container{
  height: 100%;
  width: 100%;
}
:deep(.el-form-item--label-top) {
  .el-form-item__label {
    margin-bottom: 0 !important;
  }
}

.el-main-header {
  background-color: var(--bs-bgcolor);
  display: flex;
  align-items: end;
  justify-content: space-between;
  padding: 2px 16px 14px;
  position: sticky;

  .el-main-header-left {
    display: flex;
    justify-content: space-between;
  }

  .el-main-header-right {
    display: flex;
    justify-content: space-between;
  }

  .el-form-item {
    margin-bottom: 0;

    .el-select {
      width: 200px;
    }
  }

  .btn_open-changecolor,
  .btn-modelfolder {
    margin-top: auto;
  }
}
.el-main-body {
  box-sizing: border-box;
  padding: 20px;
  /* padding-bottom: 0; */
  overflow-y: auto;

  :deep(.el-form-item__label) {
    font-weight: 900;
    font-size: 15px;
    color: #000;
  }
  .common-config-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(190px, 240px));
    gap: 16px;
    align-items: stretch;
  }
  .common-config-entry {
    min-height: 150px;
    padding: 22px 18px;
    /* border: 1px solid var(--bs-radio-bscolor); */
    /* border-radius: 6px; */
    background: var(--bs-bgcolor);
    color: inherit;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    text-align: center;
    font: inherit;
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    border-top:var(--bs-primary-color)  solid 6px;
  }
  .common-config-entry:hover{
    background:var(--bs-card-bgcolor-hover);
  }
  .common-config-entry:active {
    background: var(--ba-card-bgcolor-active);
  }
  .common-config-entry:focus-visible {
    transform: translateY(-2px);
    border-color: var(--bs-primary-color);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
    outline: none;
  }
  .common-config-icon {
    font-size: 42px;
    color: var(--bs-primary-color);
  }
  .common-config-title {
    font-size: 16px;
    font-weight: 700;
  }
  .common-config-description {
    /* color: var(--el-text-color-secondary); */
    font-size: 13px;
    line-height: 1.5;
  }
  .sop-config-container{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    justify-content: start;
    gap: 15px;
    .sop-card{
      min-width: 0;
      /* box-shadow:
          0 1px 3px rgba(0,0,0,.2),
          0 2px 6px rgba(0,0,0,.08); */

      transition: .25s;
      position: relative;
      overflow: hidden;
      &:hover{
        transform:translateY(-1px);
        box-shadow:0 3px 5px rgba(0,0,0,.18);
      }
      .card-color-bar{
        height:6px;
        width:100%;
      }
      .card-content{
        padding:18px;
        background-color:var(--bs-bgcolor);
        .card-content-top{
          display:flex;
          justify-content:space-between;
          align-items:flex-start;
          .card-content-top-left{
            display:flex;
            align-items:flex-start;
            .card-content-top-left-title{
              margin-left:12px;
              display:flex;
              flex-direction:column;
            }
            .subtitle{
              font-size:12px;
            }
            .title{
              white-space: nowrap;
              overflow: hidden;
              text-overflow: ellipsis;
              font-size:20px;
              font-weight:700;
            }
          }
          .card-content-top-right{
            display:flex;
            gap:20px;
            margin-top:8px;
          }
        }
        .card-content-info{
          /* margin-top:22px; */
          display:grid;
          grid-template-columns:repeat(3,1fr);
          gap:20px;
          
          
        }
        .card-content-description{
          margin-top:22px;
        }
        .label,.value{
          white-space: nowrap;
          text-overflow: ellipsis;
          overflow: hidden;
        }
        .label{
          font-size:12px;
        font-weight:700;
        }
        .value{
          font-size:16px;
        }
      }
    }
  }
}


/* 摄像头 */
.video-wrapper {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  top: -22px;
  overflow: hidden;
  background-color: var(--bs-radio-bscolor);
  * {
    position: relative;
    z-index: 1;
  }

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-image: url(@/assets/img/FAIVS.jpg);
    background-size: 100% 100%;
    /* 填充整个容器（可能拉伸图片） */
    background-repeat: no-repeat;
    opacity: 0.1;
    /* 透明度 0~1（0.5=半透明） */
    z-index: 0;
    /* 确保背景在内容下层 */
  }
  .video-container {
    position: relative;
    width: 100%;
    overflow: hidden;
    height: 100%;
    img {
        position: absolute;
        top:0;
        left: 0;
        width: 100%;
        height: 100%;
        object-fit: contain;
        /* 保持图片比例且不超出容器 */
        }
    }
}
/* 配置组件样式 */
:deep(.el-overlay-dialog) {
  overflow: hidden ;
  
}
:deep(.sop-dialog.is-fullscreen) {
  margin: 0;
  height: 100vh !important;
  display: flex;
  flex-direction: column;
  background-color: var(--bs-bgcolor);
  padding-left:15px;
  padding-right: 15px;
}
:deep(.sop-dialog .el-dialog__header) {
  flex: 0 0 auto;
  background-color:transparent
}
:deep(.sop-dialog .el-dialog__body) {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
:deep(.sop-dialog .el-dialog__footer) {
  flex: 0 0 auto;
}
</style>
