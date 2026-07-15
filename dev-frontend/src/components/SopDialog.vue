<template>
    <el-dialog class="sop-dialog" :model-value="visible" modal-class="bs-shade" fullscreen @closed="handleClosed" @update:model-value="$emit('update:visible', $event)">
      <template #header>
          <el-form v-if="visible" ref="ruleModelCameraRef" :model="modelCameraForm" :inline="true">
              <!-- 摄像头选择 -->
              <el-form-item :label="$t('config.model')" style="margin-right: 0" prop="model" required>
                <el-select v-model="modelCameraForm.model" style="width: 200px" @change="(model) => $emit('modelChanged', model)">
                    <el-option v-for="(value, model, index) in modelsList" :key="index" :label="model" :value="model" :disabled="!value" />
                </el-select>
              </el-form-item>
              <el-form-item label="">
                <el-button v-show="modelCameraForm.model !== null && modelCameraForm.model !== ''" :title="$t('button.title.box_style_setting')" :icon="Setting" size="small" link circle @click="$emit('openBoxStyleDrawer')" />
              </el-form-item>
              <el-form-item :label="$t('config.confidence')">
                <div style="width: 280px"><el-slider v-model="modelCameraForm.confidence" :format-tooltip="val => val / 100" /></div>
                <b style="margin-left: 5px">{{ modelCameraForm.confidence / 100 }}</b>
              </el-form-item>
              <!-- <el-form-item label="">
              <el-button :disabled="modelCameraForm.monitors.length >= 3" :icon="Monitor"  type="primary" size="small" @click="onAddMonitorData">{{ $t("button.add_monitor") }}</el-button>
              <el-button v-if="modelCameraForm.monitors.length > 0" type="warning" :icon="Warning"  size="small" @click="$emit('openAbnormalFeedbackTrigger')">{{ $t("button.add_feedback_trigger") }}</el-button>
              </el-form-item> -->
          </el-form>
      </template>
      <div class="sop-layout" v-if="modelCameraForm.model && visible">
        
          <el-splitter>
              <el-splitter-panel size="400px" min="200px">
                  <div class="config-container steps-sidebar">
                      <div class="config-title">
                        {{ $t('config.sop_step_config.process_chain_config') }}
                        <el-icon v-if="steps_local.length>0" style="float: right;" color="red" @click="handleDeleteStep"><Delete /></el-icon>
                      </div>
                      <div class="step-list-wrapper">
                        <VueDraggable ref="el" ghostClass="ghost" v-model="steps_local" :animation="150">
                          <div  v-for="(step, index) in steps_local"  :key="step.id" :class="['step-item', { isActivate: activeStepIndex === index }]"  @click="activeStepIndex = index">
                            <span class="step-num">{{ index + 1 }}</span>
                            <span class="step-name">{{ step.name || 'Unnamed steps' }}</span>
                            <el-tag effect="dark" :type="getStepTypeLabel(step.type)[1]" style="margin-left: auto;">{{ getStepTypeLabel(step.type)[0] }}</el-tag>
                          </div>
                        </VueDraggable>
                      </div>
                      <el-button type="primary" plain size="small" style="width:100%" @click="handleAddNewStep"> + {{ $t('button.add') }}</el-button>
                  </div>
              </el-splitter-panel>
              <el-splitter-panel min="50%">
                  <div class="config-container">
                      <div class="config-title">{{ $t('config.sop_step_config.property_config') }}</div>
                      <div class="config-wrapper" v-if="currentStep">
                        <h3>{{ $t('interacting.step') }}-{{ activeStepIndex + 1 }}</h3>
                        <el-form ref="ruleStepRef" :model="currentStep" :rules="stepRules" label-position="top">
                          <el-form-item :label="$t('config.form.stepname')" prop="name">
                            <el-input v-model="currentStep.name" :placeholder="$t('interacting.pls') + $t('interacting.enter') + $t('config.form.stepname')" />
                          </el-form-item>
                          <el-form-item :label="$t('config.form.stepdes')" prop="hint">
                            <el-input type="textarea" v-model="currentStep.hint" :placeholder="$t('interacting.pls') + $t('interacting.enter') + $t('config.form.stepdes')" />
                          </el-form-item>
                          <el-row :gutter="10">
                              <el-col :span="6">
                                <el-form-item :label="$t('config.form.steptype')" prop="type">
                                  <el-select v-model="currentStep.type">
                                    <el-option v-for="(_type,index) in _types" :key="index" :value="_type.value"  :label="_type.label">{{ _type.label }}</el-option>
                                  </el-select>
                                </el-form-item>
                              </el-col>
                              <el-col :span="6">
                                <el-form-item :label="$t('config.form.expectedM')" prop="context.expectedObject">
                                  <el-select v-model="currentStep.context.expectedObject" clearable>
                                    <el-option v-for="(color,obj, index) in props.currentMainLabels" :key="index" :label="obj" :value="obj" :disabled="currentStep.context.fromRegion === obj || currentStep.context.toRegion === obj"/>
                                  </el-select>
                              </el-form-item>
                              </el-col>
                              <el-col :span="6">
                                <el-form-item :label="$t('config.form.targettimes')" prop="target">
                                  <el-input-number v-model.number="currentStep.target" :min="1" style="width: 100%;" />
                                </el-form-item>
                              </el-col>
                              <el-col :span="6">
                                <el-form-item :label="$t('config.form.duration')" prop="timeout">
                                  <el-input-number v-model.number="currentStep.timeout" :min="1" style="width: 100%;" />
                                </el-form-item>
                              </el-col>
                          </el-row>
                          <el-row :gutter="10">
                            <el-col :span="6">
                              <el-form-item :label="$t('config.form.startarea')" prop="context.fromRegion">
                                <el-select v-model="currentStep.context.fromRegion" clearable>
                                  <el-option v-for="(color,obj, index) in props.currentMainLabels" :key="index" :label="obj" :value="obj" :disabled="currentStep.context.expectedObject === obj || currentStep.context.toRegion === obj"/>
                                </el-select>
                              </el-form-item>
                            </el-col>
                            <el-col :span="6">
                              <el-form-item :label="$t('config.form.targetarea')" prop="context.toRegion">
                                <el-select v-model="currentStep.context.toRegion" clearable>
                                  <el-option v-for="(color,obj, index) in props.currentMainLabels" :key="index" :label="obj" :value="obj" :disabled="currentStep.context.expectedObject === obj || currentStep.context.fromRegion === obj"/>
                                </el-select>
                              </el-form-item>
                            </el-col>
                            <el-col :span="12">
                              <el-form-item :label="$t('config.form.expectedMdetectStage')">
                                <el-checkbox-group v-model="currentObjectDetectionPhases">
                                    <el-checkbox value="source" :label="$t('config.form.startarea')" />
                                    <el-checkbox value="transit" :label="$t('config.form.transitionarea')" />
                                    <el-checkbox value="target" :label="$t('config.form.targetarea')" />
                                </el-checkbox-group>
                            </el-form-item>
                            </el-col>
                            
                            

                          </el-row>
                          <el-row :gutter="10">
                            <el-col :span="6">
                              <el-form-item :label="$t('config.form.allowlostframequantity')" prop="context.missTolerance">
                                <el-input-number v-model.number="currentStep.context.missTolerance" :min="1" />
                                <span style="margin-left: 10px;">
                                  <el-tooltip :trigger="['hover','click']" :content="$t('description.config.allowlostframequantity')">
                                    <el-icon><QuestionFilled /></el-icon>
                                  </el-tooltip>
                                </span>
                              </el-form-item>
                            </el-col>
                            <el-col :span="6">
                              <el-form-item :label="$t('config.form.hands')">
                                <el-select multiple v-model="currentHands" clearable @change="handleChangeHands">
                                  <el-option v-for="(obj, index) in handsOpthion" :key="index" :label="obj.label" :value="obj.value"/>
                                </el-select>
                              </el-form-item>
                            </el-col>
                            <el-col :span="6">
                              <el-form-item :label="$t('config.form.handmargin')" prop="context.handMargin">
                                <el-input-number v-model.number="currentStep.context.handMargin" :min="1" />
                                <span style="margin-left: 10px;">
                                  <el-tooltip :trigger="['hover','click']" :content="$t('description.config.handmargin')">
                                    <el-icon><QuestionFilled /></el-icon>
                                  </el-tooltip>
                                </span>
                              </el-form-item>
                            </el-col>
                          </el-row>
                          <div v-if="currentHands.length" class="hands-point-container">
                                <b>{{ $t('displaytext.handkeypoints') }}</b>
                                <div class="hands-point-wrapper" v-if="currentHands.includes('l')">
                                    <div class="hands-point-field">L</div>
                                    <div v-if="currentStep.context.handPoints" style="display: flex;gap:5px;flex-wrap: wrap;">
                                      <el-tag effect="dark" round size="small" v-for="item in currentStep.context.handPoints.l" :key="item">{{ item }}</el-tag>
                                    </div>
                                    
                                    <div class="hands-point-oprator">
                                      <el-icon color="var(--bs-success-color)" @click="handlePointPointsOprator(true,'l')" size="18" :title="$t('button.title.selectall')"><CircleCheck /></el-icon>
                                      <el-icon  size="18" :title="$t('button.title.unselectall')" @click="handlePointPointsOprator(false,'l')"><CircleClose /></el-icon>
                                    </div>
                                    
                                  </div>
                                <div class="hands-point-wrapper" v-if="currentHands.includes('r')">
                                  <div class="hands-point-field">R</div>
                                  <div v-if="currentStep.context.handPoints" style="display: flex;gap:5px;flex-wrap: wrap;">
                                    <el-tag effect="dark" round size="small" v-for="item in currentStep.context.handPoints.r" :key="item">{{ item }}</el-tag>
                                  </div>
                                  <div class="hands-point-oprator">
                                    <el-icon color="var(--bs-success-color)"  size="18" :title="$t('button.title.selectall')" @click="handlePointPointsOprator(true,'r')"><CircleCheck /></el-icon>
                                    <el-icon  size="18" :title="$t('button.title.unselectall')" @click="handlePointPointsOprator(false,'r')"><CircleClose /></el-icon>
                                  </div>
                                </div>
                              </div>
                        </el-form>
                      </div>
                  </div>
              </el-splitter-panel>
              <el-splitter-panel size="300px" min="200px" :collapsible="true">
                  <div class="config-container right-sidebar">
                      <div class="config-title">{{ $t('button.customize') }}</div>
                      <div class="right-sidebar-wrapper" v-if="currentStep && currentHands.length">
                        <Hands :handsPoints="currentStep.context.handPoints" @update:handsPoints="currentStep.context.handPoints = $event"/>
                      </div>
                  </div>
              </el-splitter-panel>
          </el-splitter>
      </div>
      <template #footer>
        <el-button type="primary" plain @click="handleReset">{{ $t('button.reset') }}</el-button>
        <el-button v-if="modelCameraForm.model" type="primary" size="large" @click="handleSave">{{ $t("button.save") }}</el-button>
      </template>
    </el-dialog>
</template>
<script setup lang="ts">
import { ref, reactive,computed, nextTick,watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, FormInstance, FormRules } from "element-plus";
import { Delete, Setting,Monitor,Warning } from "@element-plus/icons-vue";
import { MesAlertWTitle, MesConfirmWTitle } from "@/assets/js/secondpk";
import { UseDraggableReturn,VueDraggable } from 'vue-draggable-plus';
import Hands from './Hands.vue';
const el = ref<UseDraggableReturn>();

const { t } = useI18n();
const props = defineProps<{
  visible: boolean;
  modelCameraForm:any;
  modelsList: Record<string, boolean>;
  currentMainLabels: Record<string, string>;
  steps: any[];
}>();
const emit = defineEmits<{
  (e: "update:visible", val: boolean): void;
  (e: "close"): void;
  (e: "save", row: any): void;
  (e: "modelChanged", modelName: string): void;
  (e: "openBoxStyleDrawer"): void;
}>();
const steps_local = ref<any[]>([]);

watch(() => props.steps, (newSteps) => {steps_local.value = JSON.parse(JSON.stringify(newSteps)) || [];}, { immediate: true });
const activeStepIndex = ref(0);
const ruleStepRef = ref<FormInstance>();
const stepRules = reactive<FormRules>({
  name: [{ required: true, message: t('interacting.pls') + t('interacting.enter') + t('config.form.stepname'), trigger: ["blur", "change"] }],
  type: [{ required: true, message: t('interacting.pls') + t('interacting.enter') + t('config.form.stepdes'), trigger: ["change"] }],
});
const _types = reactive([
  { value: "p_object", label: t('config.form.type_vision') ,type:"P",color:"success"},
  { value: "t_object", label: t('config.form.type_timeseries'),type:"T",color:"primary"},
  { value: "signal", label: t('config.form.type_signal'),type:"S",color:"warning"},
]);
const handsOpthion=reactive([
  { value: "l", label: t('displaytext.left') },
  { value: "r", label: t('displaytext.right') },
]);
const getStepTypeLabel = (type: string) => {
  const foundType = _types.find(t => t.value === type);
  return foundType ? [foundType.type,foundType.color] : ['', 'info'];
};
const currentStep = computed(() => steps_local.value[activeStepIndex.value]);
const HAND_SIDES = ['l', 'r'] as const;
const ALL_HAND_POINTS = Array.from({ length: 21 },(_, index) => index);
const lastStep = computed(() => steps_local.value[steps_local.value.length - 1])
const currentObjectDetectionPhases = computed({
    get: () => {
      const context = currentStep.value?.context || {};
      const legacy = context.expectedObjectRequire;
      const config = context.objectDetection || (legacy && typeof legacy === 'object' ? legacy : {
          source: legacy !== false,
          transit: legacy === true,
          target: legacy !== false,
      });
      const phases: string[] = [];
      if (config.source) { phases.push('source') };
      if (config.transit) {phases.push('transit')};
      if (config.target) {phases.push('target')};
      return phases
    },

    set: (phases: string[]) => {
      if (!currentStep.value) return
      currentStep.value.context.objectDetection = {
        source: phases.includes('source'),
        transit: phases.includes('transit'),
        target: phases.includes('target'),
      }
    },
})
const currentHands = computed<string[]>({
  get: () => {
    const handPoints = currentStep.value?.context?.handPoints || {};
    return HAND_SIDES.filter(hand =>Array.isArray(handPoints[hand]) && handPoints[hand].length > 0);
  },
  set: (hands: string[]) => {
    if (!currentStep.value) return;
    ensureHandPoints();
    for (const hand of HAND_SIDES) {
      const isEnabled = hands.includes(hand);
      if (isEnabled) {
        // 新启用一只手时，如果当前没有关键点，
        // 默认选择全部 21 个关键点。
        if (currentStep.value.context.handPoints[hand].length === 0) {
          currentStep.value.context.handPoints[hand] = [4,8,12];
        }
      } else {
        // 取消选择手 = 清空该手全部关键点
        currentStep.value.context.handPoints[hand] = [];
      }
    }
  },
});
const ensureHandPoints = () => {
  if (!currentStep.value) return;
  const context = currentStep.value.context;
  if (!context.handPoints || typeof context.handPoints !== 'object' || Array.isArray(context.handPoints)) {
    context.handPoints = {l: [],r: [],};
  }
  for (const hand of HAND_SIDES) {
    if (!Array.isArray(context.handPoints[hand])) {
      context.handPoints[hand] = [];
    }
  }
};
const isStepRequiredFieldsValid = (step: any) => {return !!(step?.name && step?.type && step?.target)};
const handleAddNewStep = async ()=>{
  // 先检查最后一个已存在步骤是否填写了必要信息，避免切换步骤后校验失效
  if (lastStep.value && !isStepRequiredFieldsValid(lastStep.value)) {
    activeStepIndex.value = steps_local.value.length - 1;
    await nextTick();
    try {
      await ruleStepRef.value?.validate();
    } catch {
      ElMessage.warning(t('config.rejectstep'));
      return;
    }
    return;
  }
  const newId = steps_local.value.length ? Math.max(...steps_local.value.map(s => s.id)) + 1 : 1;
  steps_local.value.push({
    id: newId,
    name: '安装P1零件',
    type: 'p_object',
    hint: '捡起P1零件并放置到CY中',
    target: 1,
    timeout: 30,
    context: { expectedObject: 'P1', fromRegion: '', toRegion: 'CY', expectedObjectRequire: {source:true,transit:false,target:true},missTolerance:5, handMargin: 5,  handPoints: { 'l': [], 'r': [] } },
    doneWhen: []
  });
  activeStepIndex.value = steps_local.value.length - 1;
}
const handleDeleteStep = ()=>{
  steps_local.value.splice(activeStepIndex.value, 1);
  if (activeStepIndex.value >= steps_local.value.length) {
    activeStepIndex.value = steps_local.value.length - 1;
  }
}
const handleReset = ()=>{
  steps_local.value = JSON.parse(JSON.stringify(props.steps)) || [];
  activeStepIndex.value = 0;
}
const handleSave = ()=>{
  for (const step of steps_local.value) {
        const error = validateVisionStep(step)
        if (error) return ElMessage.error(error)
    }
  const newConfig = {
    camera: props.modelCameraForm.camera,
    model: props.modelCameraForm.model,
    confidence: props.modelCameraForm.confidence / 100,
    steps: steps_local.value.map(step => ({
      id: step.id,
      name: step.name,
      type: step.type,
      hint: step.hint,
      target: step.target,
      timeout: step.timeout,
      context: { ...step.context },
      doneWhen: [...step.doneWhen]
    }))
  }
  emit("save", newConfig);
};
const validateVisionStep = (step: any,): string => {
  if (step.type !== 'p_object') return '';
  const context = step.context || {};
  const legacyObjectDetection = context.expectedObjectRequire;
  const objectDetection = context.objectDetection || (legacyObjectDetection && typeof legacyObjectDetection === 'object' ? legacyObjectDetection : {source: legacyObjectDetection !== false,transit: legacyObjectDetection === true,target: legacyObjectDetection !== false, });
  const objectRequired = (objectDetection.source || objectDetection.transit || objectDetection.target);
  const hasExpectedObject = Boolean(context.expectedObject);
  const hasFromRegion = Boolean(context.fromRegion);
  const hasToRegion =  Boolean(context.toRegion);     
  const handPoints = context.handPoints || {};
  const hasValidHand = HAND_SIDES.some(hand => Array.isArray(handPoints[hand]) && handPoints[hand].length > 0);
    if (!hasToRegion) return `步骤 ${step.id}：必须配置目标区域`;   
    // 未配置来源区时，从整个画面任意位置寻找 expectedObject，
    // 并持续跟踪到目标区域。 
    if (!hasFromRegion) {
        if (!hasExpectedObject) return `步骤 ${step.id}：未配置来源区域时，必须配置期望物料`;
        if (!objectDetection.target) return `步骤 ${step.id}：未配置来源区域时，必须启用目标区域物料检测`;
        return '';
    }  
    if (objectRequired  && !hasExpectedObject) return  `步骤 ${step.id}：` + `已启用期望物料检测阶段，` + `但未配置期望物料`;
    if ( !objectRequired && !hasValidHand) return `步骤 ${step.id}：` + `未启用任何物料检测阶段，` + `必须配置有效手部关键点`;
    if ( !objectDetection.source && !hasValidHand) return  `步骤 ${step.id}：` + `来源阶段不检测物料时，` + `必须使用手部识别`;
    if ( !objectDetection.transit && !hasValidHand) return `步骤 ${step.id}：` + `搬运阶段不检测物料时，` + `必须使用手部识别`;
    if ( !objectDetection.target && !hasValidHand) return `步骤 ${step.id}：` + `目标阶段不检测物料时，` + `必须使用手部识别`;
    return ''
}
const handleChangeHands = (value: string[]) => {
  console.log('Selected hands:', value);
  // if (currentStep.value) {
  //   currentStep.value.context.expectedObject = value;
  // }
};
const handlePointPointsOprator = (isSelectAll: boolean,hand: 'l' | 'r') => {
  if (!currentStep.value) return;
  ensureHandPoints();
  currentStep.value.context.handPoints[hand] = isSelectAll ? [...ALL_HAND_POINTS] : [];
};
const handleClosed = () => {
  emit("close");
};


</script>
<style scoped lang="scss">
.ghost {
  opacity: 0.5;
  background: var(--bs-info-color);
}
.sop-layout {
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background-color: #fff;
  color:#000;
  .right-sidebar,
  .steps-sidebar{
    display: flex;
    flex-direction: column;
  }

  .step-list-wrapper {
    flex: 1;
    min-height: 0;
    overflow: auto;
    .step-item {
      // &:first-child {
      //   border-top: 1px solid #e0e0e0;
      // }
      padding: 12px;
      border-bottom: 1px solid var(--bs-radio-bscolor);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }
  .right-sidebar-wrapper {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }
  .config-container{
    height: 100%;
    padding: 5px;
    box-sizing: border-box;
    .config-wrapper{
      padding: 0 12px;
      .hands-point-container{
        display: flex;
        flex-direction: column;
        gap: 5px;
        padding: 5px;
        border: 1px #000 dashed;
        .hands-point-wrapper{
          box-shadow: inset 0 0 5px rgba(0,0,0,.2);
          padding: 5px;
          background-color: var(--bs-element-bgcolor);
          display: flex;
          align-items: center;
          gap: 5px;
          .hands-point-field {
            margin-right: 5px;
            border-right:1px solid #000;
            padding-right: 5px;
          }
          .hands-point-oprator{
            margin-left: auto;
            display: flex;
            gap: 5px;
          }
        }
      }
      
    }
  }
}
.isActivate {
    background-color: var(--bs-primary-hover-icon-color);
  } 
.config-title{
    text-align: center;
    border-bottom: 1px solid #000;
    font-size: 18px;
    font-weight: 600;
    padding: 5px 0;
}

// 以下暂时不用
.left-side{
    height: 100%;
  min-height: 0;
    background-color: #f5f5f5;
  overflow: auto;
}

.right-side {
  height: 100%;
  min-height: 0;
  background-color: #f5f5f5;
  overflow: auto;
}

.main-pane {
  height: 100%;
  min-height: 0;
  overflow: auto;
}
</style>