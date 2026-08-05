<template>
    <div class="layout-container">
        <div class="el-main-header" ref="device1Ref">
            <div class="el-main-header-left">
              <el-form label-position="top" size="large" :inline="true">
                  <el-button type="primary" class="btn-modelfolder" :title="$t('config.model_upload.open')" circle :icon="UploadFilled" style="font-size: 24px;" @click="modelUploadDialogVisible = true" />
                  <el-form-item :label="$t('config.models')" style="margin-right: 0">
                    <el-select v-model="currentMainModel" :placeholder="t('interacting.select') + t('config.model')"
                        @change="handleChangeMainModel">
                        <el-option v-for="(value, model, index) in modelsList" :key="index" :label="model" :value="model" :disabled="!value" />
                    </el-select>
                  </el-form-item>
                  <el-popover :visible="labelColorVisible" placement="bottom" width="300" trigger="click" popper-style="height: 400px">
                    <div style="width: 100%; max-height: 350px; overflow-y: auto">
                        <el-row v-for="(color, label, index) in currentMainLabels" :key="index" style="border-bottom: 1px solid #000;">
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
                <div class="common-config-entry" @click="handStyleVisible = true">
                    <el-icon class="common-config-icon"><Pointer /></el-icon>
                    <span class="common-config-title">{{ $t('config.hand_style_config') }}</span>
                    <span class="common-config-description">{{ $t('config.hand_style_description') }}</span>
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
                <div class="common-config-entry" @click="manualRegionDialogVisible = true">
                    <el-icon class="common-config-icon"><Aim /></el-icon>
                    <span class="common-config-title">{{ $t('config.manual_region.title') }}</span>
                    <span class="common-config-description">{{ $t('config.manual_region.entry_description') }}</span>
                </div>
                <div class="common-config-entry" @click="resultMediaDialogVisible = true">
                    <el-icon class="common-config-icon"><CameraFilled /></el-icon>
                    <span class="common-config-title">{{ $t('config.result_media.title') }}</span>
                    <span class="common-config-description">{{ $t('config.result_media.entry_description') }}</span>
                </div>
                <div class="common-config-entry" @click="audioResourceDialogVisible = true">
                    <el-icon class="common-config-icon"><Headset /></el-icon>
                    <span class="common-config-title">{{ $t('config.audio_resources.title') }}</span>
                    <span class="common-config-description">{{ $t('config.audio_resources.entry_description') }}</span>
                    <el-tag class="common-config-status" type="info" effect="plain" size="small">{{ $t('config.audio_resources.count',{count:audioResources.length}) }}</el-tag>
                </div>
                <div class="common-config-entry" @click="configTransferDialogVisible = true">
                    <el-icon class="common-config-icon"><DocumentCopy /></el-icon>
                    <span class="common-config-title">{{ $t('config.config_transfer.title') }}</span>
                    <span class="common-config-description">{{ $t('config.config_transfer.entry_description') }}</span>
                </div>
                <div class="common-config-entry" @click="userManagementDialogVisible = true">
                    <el-icon class="common-config-icon"><UserFilled /></el-icon>
                    <span class="common-config-title">{{ $t('config.user_management.title') }}</span>
                    <span class="common-config-description">{{ $t('config.user_management.entry_description') }}</span>
                </div>
            </div>
            <div v-if="resultStorageStatus.pending" class="local-results-notice">
                <div class="local-results-notice__content">
                    <el-icon size="24"><WarningFilled /></el-icon>
                    <div>
                        <div class="local-results-notice__title">
                            {{ $t('config.result_storage.local_pending_title') }}
                        </div>
                        <div class="local-results-notice__description">
                            {{
                              $t('config.result_storage.local_pending_description', {
                                runs: resultStorageStatus.pendingRunCount,
                                media: resultStorageStatus.pendingMediaCount,
                                size: formattedPendingSize,
                              })
                            }}
                        </div>
                        <div v-if="!resultStorageStatus.configuredPathAvailable" class="local-results-notice__error">
                            {{ $t('config.result_storage.target_unavailable') }}
                        </div>
                    </div>
                </div>
                <el-button
                  class="el-button--black"
                  :loading="syncingLocalResults"
                  :disabled="!resultStorageStatus.configuredPathAvailable"
                  @click="handleSyncLocalResults"
                >
                    {{ $t('config.result_storage.sync_button') }}
                </el-button>
            </div>
            <!-- 工序指导配置 -->
            <el-divider content-position="left">
                <template #default>
                    <div style="font-weight: 900">{{ $t("config.sop_config") }}</div>
                </template>
            </el-divider>
            <div class="sop-config-container">
              <div class="sop-card" v-for="(conf,sopName) in sopConfigDatas" :key="sopName">
                <div class="card-color-bar" :style="{ backgroundColor: missingModels.includes(sopName) ? 'var(--bs-danger-color)' : !modelsList[conf.model] ? 'var(--bs-warning-color)' : (conf.enabled ? 'var(--bs-success-color)' : 'var(--bs-info-color)') }"></div>
                <div class="card-content">
                  <div class="card-content-top">
                    <div class="card-content-top-left">
                      <el-checkbox size="large" label="" @change="(value) => handleChangeEnable(value, sopName)" v-model="conf.enabled" :disabled="missingModels.includes(sopName) || !modelsList[conf.model]"></el-checkbox>
                      <div class="card-content-top-left-title">
                        <div class="subtitle">{{ $t('config.sop_name') }}</div>
                        <div class="title">{{ sopName }}</div>
                      </div>
                    </div>
                    <div class="card-content-top-right">
                      <el-icon size="24" style="cursor: pointer;"  @click="handelEditSop(sopName)"><Edit /></el-icon>
                      <el-icon size="24" style="cursor: pointer;" @click="handelDeleteSop(sopName)"><Delete /></el-icon>
                    </div>

                  </div>
                  <div class="card-content-info">
                    <div>
                        <div class="label">{{ $t('config.model') }}</div>
                        <div class="value">{{ conf.model }}</div>
                    </div>
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
            :existingSopNames="Object.keys(sopConfigDatas)"
            :modelsList="modelsList"
            :currentMainLabels="currentMainLabels"
            :manualRegions="manualRegionsConfig"
            :steps="editSteps"
            :resultFeedbackConfig="detectionIntegrationConfig.resultFeedback"
            :audioResources="audioResources"
            @close="handleCloseSignalSet"
            @save="handleSavePositionRow"
            @modelChanged="(model) => handleChangeMainModel(model)"
        />
        <PathDialog
          v-model:visible="pathDialogVisible"
          v-model:path-config="pathConfig"
          @saved="handlePathSaved"
        />
        <BoxStyleDrawer
          v-model:visible="boxStyleVisible"
          v-model:box-style-config="boxStyleConfig"
        />
        <HandStyleDrawer
          v-model:visible="handStyleVisible"
          v-model:hand-style-config="handStyleConfig"
        />
        <ModbusDialog
          v-model:visible="modbusDialogVisible"
          v-model:modbus-config="modbusConfig"
        />
        <DetectionIntegrationDialog
          v-model:visible="integrationDialogVisible"
          v-model:integration-config="detectionIntegrationConfig"
        />
        <ManualRegionDialog
          v-model:visible="manualRegionDialogVisible"
          v-model:manual-regions="manualRegionsConfig"
          :camera-list="cameraList"
          :camera-resolutions="cameraResolution"
          @saved="getConfig"
        />
        <ResultMediaDialog
          v-model:visible="resultMediaDialogVisible"
          v-model:result-media-config="resultMediaConfig"
        />
        <AudioResourceDialog v-model:visible="audioResourceDialogVisible" @changed="handleAudioResourcesChanged" />
        <ModelUploadDialog
          v-model:visible="modelUploadDialogVisible"
          @uploaded="handleModelUploaded"
        />
        <ConfigTransferDialog
          v-model:visible="configTransferDialogVisible"
          @imported="handleConfigImported"
        />
        <UserManagementDialog v-model:visible="userManagementDialogVisible" />
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted,watch, nextTick, reactive, computed, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";
import { useAppStore } from "@/stores/store";
import { ElMessage, FormInstance, FormRules } from "element-plus";
import { FolderOpened,Brush,Crop,Connection,SetUp,Pointer,Aim,CameraFilled,WarningFilled,UploadFilled,DocumentCopy,UserFilled,Headset } from "@element-plus/icons-vue";
import { MesAlertWTitle, MesConfirmWTitle } from "@/assets/js/secondpk";
import api from "@/api/index";
import SopDialog from "@/components/SopDialog.vue";
import ResolutionDrawer from "@/components/ResolutionDrawer.vue";
import BoxStyleDrawer from "@/components/BoxStyleDrawer.vue";
import HandStyleDrawer from "@/components/HandStyleDrawer.vue";
import PathDialog from "@/components/PathDIalog.vue";
import ModbusDialog from "@/components/ModbusDialog.vue";
import DetectionIntegrationDialog from "@/components/DetectionIntegrationDialog.vue";
import ManualRegionDialog from "@/components/ManualRegionDialog.vue";
import ResultMediaDialog from "@/components/ResultMediaDialog.vue";
import ModelUploadDialog from "@/components/ModelUploadDialog.vue";
import ConfigTransferDialog from "@/components/ConfigTransferDialog.vue";
import UserManagementDialog from "@/components/UserManagementDialog.vue";
import AudioResourceDialog from "@/components/AudioResourceDialog.vue";
const appStore = useAppStore();
const { t } = useI18n();
const device1Ref = ref(null);
const elVideoStreamH = ref("0px");
const videoStreamHeight = () => { elVideoStreamH.value = `calc(100% - ${device1Ref.value.offsetHeight}px`; };
const currentMainModel = ref('');
const modelsList = ref({}); 
const modelUploadDialogVisible = ref(false);
const configTransferDialogVisible = ref(false);
const userManagementDialogVisible = ref(false);
const audioResourceDialogVisible = ref(false);
const audioResources = ref<any[]>([]);
const cameraList = ref<string[]>([]);
const labelColorVisible = ref(false);
const currentMainLabels = ref<Record<string, string>>({});
const currentMainCamera = ref(null);
const configCameraVisible = ref(false);
const ws = ref(null);
let previewFrameRendering = false;
let previewFrameUrl: string | null = null;
//分辨率
const resolutionsDes = ref("");
const resolutionsList = ref<number[][]>([]);
const cameraResolution = ref<Record<string, { width: number; height: number; area: number; clarity: number }>>({});
const defaultResolution = ref({ width: 640, height: 480, area: 640, clarity: 50 });
const resolutionForm = reactive({ resolutions: "", area: 640, clarity: 50 });
const resolutionsDrawerVisible = ref(false);
const formatResolution = (width: number, height: number) => `${width}*${height}`;
const parseResolution = (value: string) => {
  const match = String(value || "").trim().match(/^(\d+)\s*[*x×]\s*(\d+)$/i);
  if (!match) return null;
  const width = Number(match[1]);
  const height = Number(match[2]);
  return Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0
    ? { width, height }
    : null;
};
//路径
const pathConfig = ref({ modelPath: "",sopPath:"", resultPath: "",userPath: "",saveDetectionDatasets: false });
const pathDialogVisible = ref(false);
interface ManualRegion {
  id: string;
  name: string;
  color: string;
  shape: "rectangle";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  enabled: boolean;
}
interface ManualRegionsConfig {
  version: number;
  cameras: Record<string, {
    referenceWidth: number;
    referenceHeight: number;
    regions: ManualRegion[];
  }>;
}
const manualRegionDialogVisible = ref(false);
const manualRegionsConfig = ref<ManualRegionsConfig>({
  version: 1,
  cameras: {},
});
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
// 手部关键点样式
const handStyleVisible = ref(false);
const handStyleConfig = ref({
  left: {
    keypointSize: 4,
    keypointColor: "#FF0000",
    connectionWidth: 2,
    connectionColor: "#FF0000",
  },
  right: {
    keypointSize: 4,
    keypointColor: "#00FF00",
    connectionWidth: 2,
    connectionColor: "#00FF00",
  },
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
// 检测结果图片
const resultMediaDialogVisible = ref(false);
const resultMediaConfig = ref({
  enabled: true,
  saveOperationError: true,
  saveNgRawImage: true,
  saveNgAnnotatedImage: true,
  saveStepSuccess: true,
  saveRunCompleted: true,
  saveNgVideo: true,
  ngVideoBeforeSeconds: 8,
  ngVideoAfterSeconds: 5,
  ngVideoFps: 10,
  ngVideoMaxWidth: 1280,
  imageFormat: "jpg" as const,
  jpegQuality: 90,
  minFreeDiskPercent: 10,
  queueSize: 32,
});
const resultStorageStatus = reactive({
  pending: false,
  pendingRunCount: 0,
  pendingMediaCount: 0,
  pendingBytes: 0,
  configuredPathAvailable: true,
  configuredPathError: "",
  syncInProgress: false,
});
const syncingLocalResults = ref(false);
let resultStorageStatusTimer: number | undefined;
const formattedPendingSize = computed(() => {
  const bytes = Number(resultStorageStatus.pendingBytes || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
});
// 参数配置相关
const signalSetVisible = ref(false);
const createSopCompletionFeedback = () => ({modbus:{enabled:false,signals:[]}});
const modelCameraForm = ref({
  sopName: "",
  originalSopName: "",
  model: "",
  confidence: 50,
  sopCompletionFeedback: createSopCompletionFeedback(),
});
onMounted(async () => {
    videoStreamHeight();
    // 配置中的 enableCamera 依赖相机列表，必须先完成设备读取。
    await getDevice();
    await getConfig();
    await loadAudioResources();
    await getResultStorageStatus();
    resultStorageStatusTimer = window.setInterval(
      getResultStorageStatus,
      15000,
    );
    getModels();
});
onUnmounted(() => {
  if (resultStorageStatusTimer !== undefined) {
    window.clearInterval(resultStorageStatusTimer);
  }
  closeCameraPreviewSocket();
});
watch(()=>modelsList.value,()=>{
  checkSopConfigModelsExist();
});

//头部组件
/**-----------初始化---------- */
const getConfig = () => {
  appStore.setLoading(true);
  return api.getConfig().then((res) => {
    const resData = res.data;
    if (!resData.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failed_get_config"), resData.msg, t("button.ok"));
    const datas = resData.datas;
    sopConfigDatas.value = resData.sops || {};
    if ("paths" in datas) {
      const { modelPath = "", sopPath = "", resultPath = "",userPath = "",saveDetectionDatasets = false } = datas.paths;
      pathConfig.value = { ...pathConfig.value, modelPath, sopPath, resultPath,userPath,saveDetectionDatasets };
    };
    if (datas.boxStyle) {boxStyleConfig.value = {...boxStyleConfig.value,...datas.boxStyle, }};
    if (datas.handStyle) {
      handStyleConfig.value = {
        left: {
          ...handStyleConfig.value.left,
          ...(datas.handStyle.left || {}),
        },
        right: {
          ...handStyleConfig.value.right,
          ...(datas.handStyle.right || {}),
        },
      };
    };
    if (datas.manualRegions) {
      manualRegionsConfig.value = {
        version: 1,
        cameras: datas.manualRegions.cameras || {},
      };
    }
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
    if (datas.resultMedia) {
      resultMediaConfig.value = {
        ...resultMediaConfig.value,
        ...datas.resultMedia,
        imageFormat: "jpg",
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
    .catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failed_get_config"), error.message, t("button.ok")))
    .finally(() => { appStore.setLoading(false); });
};
const loadAudioResources = async () => {try {const {data} = await api.getAudioResources();if (data?.status) audioResources.value = Array.isArray(data.datas) ? data.datas : [];} catch (error) {console.error("Failed to load audio resources",error)}};
const handleAudioResourcesChanged = (resources:any[]) => {audioResources.value = Array.isArray(resources) ? resources : []};
const getResultStorageStatus = async () => {
  try {
    const response = await api.getResultStorageStatus({});
    if (response.data?.status && response.data?.data) {
      Object.assign(resultStorageStatus, response.data.data);
    }
  } catch (error) {
    console.error("Failed to read result storage status", error);
  }
};
const handleSyncLocalResults = async () => {
  syncingLocalResults.value = true;
  try {
    const response = await api.syncLocalResults({});
    const summary = response.data?.data;
    if (!response.data?.status) {
      ElMessage.error(response.data?.msg || t("config.result_storage.sync_failed"));
    } else {
      ElMessage.success(
        t("config.result_storage.sync_success", {
          runs: summary?.syncedRunCount || 0,
          media: summary?.syncedMediaCount || 0,
        }),
      );
    }
  } catch (error: any) {
    ElMessage.error(
      error?.response?.data?.msg ||
        error?.message ||
        t("config.result_storage.sync_failed"),
    );
  } finally {
    syncingLocalResults.value = false;
    await getResultStorageStatus();
  }
};
const handlePathSaved = async () => {
  getModels();
  await getResultStorageStatus();
};
const getModels = () => {
  appStore.setLoading(true);
  return api.getModels().then((res) => {
    const resData = res.data;
    if (!resData.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedgetmodels"), resData.msg, t("button.ok"));
    modelsList.value = resData.datas;
  })
    .catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedgetmodels"), error.message, t("button.ok")))
    .finally(() => { appStore.setLoading(false); });
};
const getDevice = () => {
  appStore.setLoading(true);
  return api.getDevice().then((res) => {
    cameraList.value = res.data.camera;
  })
    .catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failed_get_device_title"), error.message, t("button.ok")))
    .finally(() => { appStore.setLoading(false); });
};
const handleModelUploaded = async (modelName: string) => {
  await getModels();
  if (modelName) {
    currentMainModel.value = modelName;
    handleChangeMainModel(modelName);
  }
};
const handleConfigImported = async (configType: "main" | "sop") => {
  if (configType === "main") {
    await getDevice();
  }
  await getConfig();
  await getModels();
  await getResultStorageStatus();
  if (configType === "main") window.dispatchEvent(new CustomEvent("faivs-auth-state-changed"));
};
const handleChangeMainModel = (modelName: string, edit = false) => {
  appStore.setLoading(true);
  api.getModelLabels({ model: modelName }).then((res) => {
    if (!res.data.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedgetlabels"), res.data.msg, t("button.ok"));
    currentMainLabels.value = res.data.datas;
    if (signalSetVisible.value && !edit) {
      console.log("这里需要添加逻辑")
    }
  }).catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedgetlabels"), error.message, t("button.ok")))
    .finally(() => { appStore.setLoading(false); });
};
const handleChangeColor = () => {
  appStore.setLoading(true);
  api.setModelLabels({ model: currentMainModel.value, labels: currentMainLabels.value }).then((res) => {
    if (!res.data.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedmodify"), res.data.msg, t("button.ok"));
    labelColorVisible.value = false;
    ElMessage.success(t("message.success"));
  }).catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedmodify"), error.message, t("button.ok")))
    .finally(() => { appStore.setLoading(false); });
};
const handleChangeMainCamera = (index: number) => {
  const capName = cameraList.value[index];
  appStore.setLoading(true); 
  api.modifyConfig({ enableCamera: capName }).then((res) => {
    if (!res.data.status) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedenabled"), res.data.msg, t("button.ok"));
    ElMessage.success(t("message.messagetext.successenbaled"));
  }).catch((error) => MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedenabled"), error.message, t("button.ok")))
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
const closeCameraPreviewSocket = () => {
  if (ws.value) {
    if (
      ws.value.readyState ===
      WebSocket.OPEN
    ) {
      ws.value.send(
        JSON.stringify({
          action: "CLOSE",
        })
      );
    }

    ws.value.close();
    ws.value = null;
  }

  const img = document.getElementById(
    "video-stream"
  ) as HTMLImageElement | null;

  if (img) {
    img.src = "";
  }
  if (previewFrameUrl) {
    URL.revokeObjectURL(previewFrameUrl);
    previewFrameUrl = null;
  }
  previewFrameRendering = false;
};


const configCameraDialogClosed = () => {
  closeCameraPreviewSocket();
  currentMainCamera.value = null;
};
const videoStream = () => {
  ws.value = new WebSocket(`ws://localhost:${appStore.servicePort}/ws/video_streaming?camera_id=${currentMainCamera.value}`);
  const MAGIC_CAMERA = 0xffff0000;
  ws.value.binaryType = "arraybuffer";
  const img = document.getElementById("video-stream");
  ws.value.onmessage = async (event) => {
    if (previewFrameRendering || !img) return;
    const buffer = new Uint8Array(event.data);
    if (buffer.byteLength < 4) return;
    const magic = new DataView(buffer.buffer).getUint32(0);
    const payload = buffer.slice(4); // 去掉4字节头
    if (magic === MAGIC_CAMERA) {
      previewFrameRendering = true;
      const blob = new Blob([payload], { type: "image/jpeg" });
      const url = URL.createObjectURL(blob);
      previewFrameUrl = url;
      const imgToUpdate = img;
      imgToUpdate.src = url;
      const finishFrame = () => {
        URL.revokeObjectURL(url);
        if (previewFrameUrl === url) {
          previewFrameUrl = null;
        }
        previewFrameRendering = false;
      };
      imgToUpdate.onload = finishFrame;
      imgToUpdate.onerror = finishFrame;
    }
  };
};
//分辨率
const temSetResolutionCapName = ref("");
const resolutionsDrawer = (cameraName: string) => {
  temSetResolutionCapName.value = cameraName;
  const capArea = cameraResolution.value[cameraName];
  resolutionsDes.value = capArea ? ` [${capArea.width}x${capArea.height}_(${capArea.area})]` : "";
  // ResolutionDrawer 的 option value 统一使用 “宽*高”。
  resolutionForm.resolutions = capArea ? formatResolution(capArea.width, capArea.height) : "";
  resolutionForm.area = capArea ? capArea.area : 0;
  resolutionForm.clarity = capArea ? capArea.clarity : 50;
  resolutionsDrawerVisible.value = true;
};
const handleSubmitResolution=(data: { resolutions: string; area: number; clarity: number })=>{
    const parsedResolution = parseResolution(data.resolutions);
    if (!parsedResolution) {
        ElMessage({ message: t("message.messagetext.field_lack_tip"), type: "error" });
        return;
    }
    const { width, height } = parsedResolution;
    const area = Number(data.area);
    const clarity = Number(data.clarity);
    appStore.setLoading(true);
    api.setResolution({
        cap_name: temSetResolutionCapName.value,
        width,
        height,
        area,
        clarity,
    }).then((res) => {
  if (!res.data.status) {
    return ElMessage({
      message: res.data.msg,
      type: "error",
    });
  }

  const savedConfig =
    res.data.data || {
      width,
      height,
      area,
      clarity,
    };

  defaultResolution.value = {
    ...savedConfig,
  };

  cameraResolution.value[
    temSetResolutionCapName.value
  ] = {
    ...savedConfig,
  };

  resolutionsDes.value =
    ` [${savedConfig.width}` +
    `x${savedConfig.height}` +
    `_(${savedConfig.area})]`;

  resolutionForm.resolutions =
    formatResolution(
      savedConfig.width,
      savedConfig.height
    );

  resolutionForm.area =
    savedConfig.area;

  resolutionForm.clarity =
    savedConfig.clarity;

  resolutionsDrawerVisible.value =
    false;

  ElMessage.success(
    t(
      "message.messagetext.successsave"
    )
  );
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
    editSteps.value = [];
    modelCameraForm.value = {
      sopName: "",
      originalSopName: "",
      model: "",
      confidence: 50,
      sopCompletionFeedback: createSopCompletionFeedback(),
    };
    sopDialogVisible.value = true;
}
const handleCloseSignalSet = () => {
  sopDialogVisible.value = false;
  editSteps.value = [];
  modelCameraForm.value.sopName = "";
  modelCameraForm.value.originalSopName = "";
  modelCameraForm.value.model = "";
  modelCameraForm.value.confidence = 50;
  modelCameraForm.value.sopCompletionFeedback = createSopCompletionFeedback();
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
const handelDeleteSop = async (sopName: string) => {
  try {
    await MesConfirmWTitle("warning", t("message.warning"), `${t("message.messagetext.askdelete")}[${sopName}]`, "", t("button.delete"), t("button.cancel"));
  } catch {
    return;
  }

  const modelName = sopConfigDatas.value[sopName]?.model;
  appStore.setLoading(true);
  try {
    const res = await api.deleteSopConfig({ sopName });
    if (!res.data.status) {
      return MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), res.data.msg, t("button.ok"));
    }
    delete sopConfigDatas.value[sopName];
    ElMessage.success(t("message.messagetext.successdelete"));
  } catch (err: any) {
    return MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), err.message || t("message.messagetext.error_service"));
  } finally {
    appStore.setLoading(false);
  }

  const modelStillUsed = Object.values(sopConfigDatas.value).some((config: any) => config?.model === modelName);
  if (!modelName || modelStillUsed || !modelsList.value[modelName]) return;

  try {
    await MesConfirmWTitle("info", t("message.messagetext.successdelete"), t("message.messagetext.modeldelete"), t('message.messagetext.modeldeleteconfirm'), t("button.delete"), t("button.cancel"));
  } catch {
    return;
  }

  appStore.setLoading(true);
  try {
    const resp = await api.deleteModel({ model: modelName });
    if (!resp.data.status) {
      return MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), resp.data.msg, t("button.ok"));
    }
    delete modelsList.value[modelName];
    ElMessage.success(t("message.messagetext.successdelete"));
  } catch (err: any) {
    MesAlertWTitle("error", t("message.error"), t("message.messagetext.faileddelete"), err.message || t("message.messagetext.error_service"));
  } finally {
    appStore.setLoading(false);
  }
};

const handelEditSop = (sopName: string) => {
  const cof = sopConfigDatas.value[sopName];
  if (!cof) return;
  const modelName = cof.model;
  if(!modelsList.value[modelName]) return ElMessage.error(t("message.messagetext.modelconfigerror"));  
  sopDialogVisible.value = true;
  handleChangeMainModel(modelName);
  modelCameraForm.value.sopName = sopName;
  modelCameraForm.value.originalSopName = sopName;
  modelCameraForm.value.model = modelName;
  modelCameraForm.value.confidence = cof.confidence * 100;
  modelCameraForm.value.sopCompletionFeedback = JSON.parse(JSON.stringify(cof.sopCompletionFeedback || createSopCompletionFeedback()));
  if (cof) {
    editSteps.value = cof.steps || [];
  }
};
//检查SOP配置中的模型是否都存在

const checkSopConfigModelsExist = () => {
  const existingModels = Object.keys(modelsList.value);
  missingModels.value = Object.entries(sopConfigDatas.value)
    .filter(([, config]: [string, any]) => !existingModels.includes(config?.model))
    .map(([sopName]) => sopName);
};
const handleChangeEnable = (value: boolean, sopName: string) => {
  const conf = sopConfigDatas.value[sopName];
  if (!conf) return MesAlertWTitle("error", t("message.error"), t("message.messagetext.failedmodify"), t("message.messagetext.refreshpage"), t("button.ok"));
  if(value){
    const enabledSopNames = Object.keys(sopConfigDatas.value).filter(name => sopConfigDatas.value[name].enabled && name !== sopName);
    if(enabledSopNames.length > 0){
      for (const enabledSopName of enabledSopNames) {
        sopConfigDatas.value[enabledSopName].enabled = false;
      }
    }
  }
  appStore.setLoading(true);
  api.updateSopConfig({ sopName, fields:["enabled"], values: [value] }).then((res) => {
    if (!res.data.status) return MesAlertWTitle("error", t("message.error"), (value)?t("message.messagetext.failedenabled"):t("message.messagetext.faileddisabled"), res.data.msg, t("button.ok"));
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
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);

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
  .local-results-notice {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    margin-top: 16px;
    padding: 14px 16px;
    /* border: 1px solid var(--bs-alert-warning-bgcolor); */
    background: var(--bs-alert-warning-bgcolor);
  }
  .local-results-notice__content {
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }
  .local-results-notice__title {
    font-weight: 700;
  }
  .local-results-notice__description,
  .local-results-notice__error {
    margin-top: 4px;
    font-size: 13px;
    line-height: 1.5;
  }
  .local-results-notice__error {
    color: var(--el-color-danger);
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
