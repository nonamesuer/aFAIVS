<template>
  <el-dialog
    class="sop-dialog"
    :model-value="visible"
    modal-class="bs-shade"
    fullscreen
    @closed="handleClosed"
    @update:model-value="$emit('update:visible', $event)"
  >
    <template #header>
      <el-form v-if="visible" :model="modelCameraForm" :inline="true">
        <el-form-item :label="$t('config.model')" prop="model" required style="margin-right: 5px;">
          <el-select v-model="modelCameraForm.model" style="width: 200px" @change="(model) => $emit('modelChanged', model)">
            <el-option
              v-for="(available, model, index) in modelsList"
              :key="index"
              :label="model"
              :value="model"
              :disabled="!available"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button
            v-show="modelCameraForm.model"
            :title="$t('button.title.box_style_setting')"
            :icon="Setting"
            size="small"
            link
            circle
            @click="$emit('openBoxStyleDrawer')"
          />
        </el-form-item>
        <el-form-item :label="$t('config.confidence')">
          <div style="width: 280px">
            <el-slider v-model="modelCameraForm.confidence" :format-tooltip="value => value / 100" />
          </div>
          <b class="confidence-value">{{ modelCameraForm.confidence / 100 }}</b>
        </el-form-item>
      </el-form>
    </template>

    <div v-if="modelCameraForm.model && visible" class="sop-layout">
      <el-splitter>
        <el-splitter-panel size="400px" min="240px">
          <div class="config-container steps-sidebar">
            <div class="config-title">
              {{ $t('config.sop_step_config.process_chain_config') }}
              <el-icon
                v-if="stepsLocal.length"
                class="delete-step"
                color="red"
                @click="handleDeleteStep"
              >
                <Delete />
              </el-icon>
            </div>

            <div class="step-list-wrapper">
              <VueDraggable v-model="stepsLocal" :animation="150" ghost-class="ghost">
                <div
                  v-for="(step, index) in stepsLocal"
                  :key="step.id"
                  :class="['step-item', { isActivate: activeStepIndex === index }]"
                  @click="activeStepIndex = index"
                >
                  <el-icon v-if="!validateVisionStep(step).valid" class="assistant-error-dot" color="red" size="20px"><BellFilled /></el-icon>
                  <span class="step-num">{{ index + 1 }}</span>
                  <span class="step-name">{{ step.name || 'Unnamed step' }}</span>
                  <el-tag effect="dark" :type="getStepTypeLabel(step.type)[1]">
                    {{ getStepTypeLabel(step.type)[0] }}
                  </el-tag>
                </div>
              </VueDraggable>
            </div>

            <el-button type="primary" plain size="small" class="add-step" @click="handleAddNewStep">
              + {{ $t('button.add') }}
            </el-button>
          </div>
        </el-splitter-panel>

        <el-splitter-panel min="50%">
          <div class="config-container">
            <div class="config-title">{{ $t('config.sop_step_config.property_config') }}</div>
            <div v-if="currentStep" class="config-wrapper">
              <h3>{{ $t('interacting.step') }}-{{ activeStepIndex + 1 }}</h3>

              <el-form ref="ruleStepRef" :model="currentStep" :rules="stepRules" label-position="top">
                <el-form-item :label="$t('config.form.stepname')" prop="name">
                  <el-input v-model="currentStep.name" />
                </el-form-item>

                <el-form-item :label="$t('config.form.stepdes')" prop="hint">
                  <el-input v-model="currentStep.hint" type="textarea" />
                </el-form-item>

                <el-row :gutter="10">
                  <el-col :span="6">
                    <el-form-item :label="$t('config.form.steptype')" prop="type">
                      <el-select v-model="currentStep.type">
                        <el-option
                          v-for="typeItem in stepTypes"
                          :key="typeItem.value"
                          :value="typeItem.value"
                          :label="typeItem.label"
                        />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item :label="$t('config.form.expectedM')" prop="context.expectedObject">
                      <el-select v-model="currentStep.context.expectedObject" clearable>
                        <el-option
                          v-for="(_color, label) in currentMainLabels"
                          :key="label"
                          :label="label"
                          :value="label"
                          :disabled="currentStep.context.fromRegion === label || currentStep.context.toRegion === label"
                        />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item :label="$t('config.form.targettimes')" prop="target">
                      <el-input-number v-model.number="currentStep.target" :min="1" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item :label="$t('config.form.duration')" prop="timeout">
                      <el-input-number v-model.number="currentStep.timeout" :min="0" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-row :gutter="10">
                  <el-col :span="6">
                    <el-form-item :label="$t('config.form.startarea')" prop="context.fromRegion">
                      <el-select v-model="currentStep.context.fromRegion" clearable>
                        <el-option
                          v-for="(_color, label) in currentMainLabels"
                          :key="label"
                          :label="label"
                          :value="label"
                          :disabled="currentStep.context.expectedObject === label || currentStep.context.toRegion === label"
                        />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item :label="$t('config.form.targetarea')" prop="context.toRegion" required>
                      <el-select v-model="currentStep.context.toRegion" clearable>
                        <el-option
                          v-for="(_color, label) in currentMainLabels"
                          :key="label"
                          :label="label"
                          :value="label"
                          :disabled="currentStep.context.expectedObject === label || currentStep.context.fromRegion === label"
                        />
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
                  <el-col :span="8">
                    <el-form-item :label="$t('config.form.allowlostframequantity')" prop="context.missTolerance">
                      <el-input-number v-model.number="currentStep.context.missTolerance" :min="0" />
                      <el-tooltip :content="$t('description.config.allowlostframequantity')">
                        <el-icon class="help-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item :label="$t('config.form.hands')">
                      <el-select v-model="currentHands" multiple clearable>
                        <el-option
                          v-for="option in handOptions"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item :label="$t('config.form.handmargin')" prop="context.handMargin">
                      <el-input-number v-model.number="currentStep.context.handMargin" :min="0" />
                      <el-tooltip :content="$t('description.config.handmargin')">
                        <el-icon class="help-icon"><QuestionFilled /></el-icon>
                      </el-tooltip>
                    </el-form-item>
                  </el-col>
                </el-row>

                <div v-if="currentHands.length" class="hands-point-container">
                  <b>{{ $t('displaytext.handkeypoints') }}</b>
                  <div v-for="side in currentHands" :key="side" class="hands-point-wrapper">
                    <div class="hands-point-field">{{ side.toUpperCase() }}</div>
                    <div class="point-tags">
                      <el-tag v-for="point in currentStep.context.handPoints[side]" :key="point" effect="dark" round size="small">
                        {{ point }}
                      </el-tag>
                    </div>
                    <div class="hands-point-operator">
                      <el-icon color="var(--bs-success-color)" size="20px" @click="handlePointPointsOperator(true, side)">
                        <CircleCheck />
                      </el-icon>
                      <el-icon size="20px" @click="handlePointPointsOperator(false, side)">
                        <CircleClose />
                      </el-icon>
                    </div>
                  </div>
                </div>
              </el-form>
            </div>
          </div>
        </el-splitter-panel>

        <el-splitter-panel size="320px" min="240px" :collapsible="true">
          <div class="config-container right-sidebar">
            <div class="config-title">{{ $t('button.customize') }}</div>
            <div v-if="currentStep && currentHands.length" class="right-sidebar-wrapper">
              <Hands
                :hands-points="currentStep.context.handPoints"
                @update:hands-points="currentStep.context.handPoints = $event"
              />
            </div>
          </div>
        </el-splitter-panel>
      </el-splitter>
    </div>
    <!-- SOP 执行链浮动助手 -->
    <div v-if="modelCameraForm.model && visible && currentStep" class="sop-execution-assistant" @mouseenter="handleExecutionPreviewEnter" @mouseleave="handleExecutionPreviewLeave">
      <!-- 对话气泡 -->
      <transition name="assistant-bubble">
        <section v-show="executionPreviewVisible" class="assistant-preview-panel" @click.stop>
          <header class="assistant-preview-header">
            <div class="assistant-preview-title">
              <div class="assistant-title-robot">
                <img :src="robotImage" :alt="$t('robot.alt')" draggable="false" />
              </div>
              <div>
                <div>{{ $t('robot.alt') }}</div>
                <small>{{ currentStep.name || `${$t('interacting.process')} ${activeStepIndex + 1}` }}</small>
              </div>
            </div>

            <el-button class="assistant-close-button" link circle :title="$t('robot.hideassistant')" @click.stop="hideExecutionPreview">
              <el-icon>
                <Close />
              </el-icon>
            </el-button>
          </header>

          <div class="assistant-preview-content">
            <!-- 合法配置 -->
            <template v-if="currentValidation.valid">
              <div class="assistant-valid-content">
                <div class="assistant-message">{{ $t('robot.effectiveconfig') }}</div>
                <div v-if="currentValidation.plan.length" class="assistant-plan-scroll-wrapper">
                  <ol ref="assistantPlanListRef" class="assistant-execution-plan" @scroll="handlePlanScroll">
                    <li v-for="(item, index) in currentValidation.plan" :key="`${index}-${item}`">
                      <span class="assistant-plan-index">{{ index + 1 }}</span>
                      <span>{{ item }}</span>
                    </li>
                  </ol>
                  <div v-if="showPlanScrollTopHint" class="assistant-scroll-hint assistant-scroll-hint-top">
                    <el-icon><CaretTop /></el-icon>
                  </div>
                  <div v-if="showPlanScrollBottomHint" class="assistant-scroll-hint assistant-scroll-hint-bottom">
                    <el-icon><CaretBottom /></el-icon>
                  </div>
                </div>
                <div v-else class="assistant-empty">{{ $t('robot.noconfig') }}</div>
                <div v-if="Number(currentStep.target || 1) > 1" class="assistant-baseline-note">
                  <el-icon>
                    <InfoFilled />
                  </el-icon>
                  <span>
                    {{ $t('robot.needdo') }} {{ currentStep.target }}, {{ $t('robot.needdoexplain') }}
                  </span>
                </div>
              </div>
            </template>
            <!-- 非法配置 -->
            <template v-else>
              <div class="assistant-invalid-message">
                <el-icon>
                  <WarningFilled />
                </el-icon>
                <div>
                  <strong>{{ $t('robot.cannotdo') }}</strong>
                  <p>{{ currentValidation.message }}</p>
                </div>
              </div>
            </template>
          </div>
          <!-- 气泡尾部 -->
          <div class="assistant-bubble-arrow"></div>
        </section>
      </transition>
      <!-- 机器人入口 -->
      <button
        type="button"
        class="assistant-robot-button"
        :class="{'is-open': executionPreviewVisible,'has-error': !currentValidation.valid}"
        :title="executionPreviewVisible ? $t('robot.alt') : t('robot.hoveralt')"
        @click.stop="pinExecutionPreview"
      >
        <img :src="robotImage" class="assistant-robot-image" :alt="$t('robot.alt')" draggable="false"/>
        <el-icon v-if="!currentValidation.valid" class="assistant-error-dot" color="red" size="20px"><BellFilled /></el-icon>
        <!-- <span v-if="!currentValidation.valid" class="assistant-error-dot"></span> -->
      </button>
    </div>
    <template #footer>
      <el-button type="primary" plain @click="handleReset">{{ $t('button.reset') }}</el-button>
      <el-button v-if="modelCameraForm.model" type="primary" size="large" @click="handleSave">
        {{ $t('button.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
// import { Delete, Setting } from '@element-plus/icons-vue'
import robotImage from '@/assets/img/robot.png';
import { ArrowDownBold, ArrowUpBold, Close,Delete,InfoFilled,Setting,WarningFilled } from '@element-plus/icons-vue';
import { VueDraggable } from 'vue-draggable-plus';
import Hands from './Hands.vue';
import { normalizeObjectDetection, normalizeVisionStepForSave,validateVisionStep} from '@/assets/js/sopRuleEngine';

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  modelCameraForm: any
  modelsList: Record<string, boolean>
  currentMainLabels: Record<string, string>
  steps: any[]
}>()

const emit = defineEmits<{
  (event: 'update:visible', value: boolean): void
  (event: 'close'): void
  (event: 'save', row: any): void
  (event: 'modelChanged', modelName: string): void
  (event: 'openBoxStyleDrawer'): void
}>()

const HAND_SIDES = ['l', 'r'] as const
const ALL_HAND_POINTS = Array.from({ length: 21 }, (_value, index) => index)
const stepsLocal = ref<any[]>([])
const activeStepIndex = ref(0)
const ruleStepRef = ref<FormInstance>();
const stepRules = reactive<FormRules>({
  name: [{ required: true, message: t('interacting.pls') + t('interacting.enter') + t('config.form.stepname'), trigger: ['blur', 'change'] }],
  type: [{ required: true, message: t('interacting.pls') + t('interacting.enter') + t('config.form.steptype'), trigger: ['change'] }],
  target: [{ required: true, message: t('config.form.targettimes'), trigger: ['blur', 'change'] }],
})

const stepTypes = reactive([
  { value: 'p_object', label: t('config.form.type_vision'), type: 'P', color: 'success' },
  { value: 't_object', label: t('config.form.type_timeseries'), type: 'T', color: 'primary' },
  { value: 'signal', label: t('config.form.type_signal'), type: 'S', color: 'warning' },
])

const handOptions = reactive([
  { value: 'l', label: t('displaytext.left') },
  { value: 'r', label: t('displaytext.right') },
])

watch(
  () => props.steps,
  newSteps => {
    stepsLocal.value = JSON.parse(JSON.stringify(newSteps || []))
    activeStepIndex.value = Math.min(activeStepIndex.value, Math.max(stepsLocal.value.length - 1, 0))
  },
  { immediate: true, deep: true },
)

const currentStep = computed(() => stepsLocal.value[activeStepIndex.value] || null)
const lastStep = computed(() => stepsLocal.value[stepsLocal.value.length - 1] || null)
const currentValidation = computed(() =>
  currentStep.value?.type === 'p_object' ? validateVisionStep(currentStep.value) : { valid: true, code: '', message: '', plan: [] },
)

const getStepTypeLabel = (type: string) => {
  const found = stepTypes.find(item => item.value === type)
  return found ? [found.type, found.color] : ['', 'info']
}

const ensureContext = () => {
  if (!currentStep.value) return
  currentStep.value.context ||= {}
  currentStep.value.context.handPoints ||= { l: [], r: [] }
  for (const side of HAND_SIDES) {
    if (!Array.isArray(currentStep.value.context.handPoints[side])) {
      currentStep.value.context.handPoints[side] = []
    }
  }
}

const currentObjectDetectionPhases = computed<string[]>({
  get: () => {
    const phases = normalizeObjectDetection(currentStep.value?.context || {})
    return (['source', 'transit', 'target'] as const).filter(phase => phases[phase])
  },
  set: phases => {
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
    const points = currentStep.value?.context?.handPoints || {}
    return HAND_SIDES.filter(side => Array.isArray(points[side]) && points[side].length > 0)
  },
  set: hands => {
    if (!currentStep.value) return
    ensureContext()
    for (const side of HAND_SIDES) {
      if (hands.includes(side)) {
        if (!currentStep.value.context.handPoints[side].length) {
          currentStep.value.context.handPoints[side] = [4, 8, 12]
        }
      } else {
        currentStep.value.context.handPoints[side] = []
      }
    }
  },
})

const isStepRequiredFieldsValid = (step: any) => Boolean(step?.name && step?.type && Number(step?.target) >= 1)

const handleAddNewStep = async () => {
  if (lastStep.value && !isStepRequiredFieldsValid(lastStep.value)) {
    activeStepIndex.value = stepsLocal.value.length - 1
    await nextTick()
    try {
      await ruleStepRef.value?.validate()
    } catch {
      ElMessage.warning(t('config.rejectstep'))
    }
    return
  }

  const newId = stepsLocal.value.length
    ? Math.max(...stepsLocal.value.map(step => Number(step.id) || 0)) + 1
    : 1

  stepsLocal.value.push({
    id: newId,
    name: '安装P1零件',
    type: 'p_object',
    hint: '捡起P1零件并放置到CY中',
    target: 1,
    timeout: 30,
    context: {
      expectedObject: 'P1',
      fromRegion: '',
      toRegion: 'CY',
      objectDetection: { source: true, transit: false, target: true },
      missTolerance: 5,
      handMargin: 5,
      handPoints: { l: [], r: [] },
    },
    doneWhen: [],
    ngWhen: [],
  })
  activeStepIndex.value = stepsLocal.value.length - 1
}

const handleDeleteStep = () => {
  if (!stepsLocal.value.length) return
  stepsLocal.value.splice(activeStepIndex.value, 1)
  activeStepIndex.value = Math.min(activeStepIndex.value, Math.max(stepsLocal.value.length - 1, 0))
}

const handleReset = () => {
  stepsLocal.value = JSON.parse(JSON.stringify(props.steps || []))
  activeStepIndex.value = 0
}

const handleSave = async () => {
  if(!stepsLocal.value.length) {
    ElMessage.error(t('message.messagetext.blankSopConfig'))
    return
  }
  for (let index = 0; index < stepsLocal.value.length; index += 1) {
    const rawStep = stepsLocal.value[index]
    if (!isStepRequiredFieldsValid(rawStep)) {
      activeStepIndex.value = index
      await nextTick()
      ElMessage.error(`${t('interacting.step')} ${rawStep?.id ?? index + 1}： ${t('message.messagetext.requiredFieldsMissing')}`)
      return
    }

    if (rawStep.type === 'p_object') {
      const validation = validateVisionStep(rawStep)
      if (!validation.valid) {
        activeStepIndex.value = index
        await nextTick()
        ElMessage.error(validation.message)
        return
      }
    }
  }

  const normalizedSteps = stepsLocal.value.map(step =>
    step.type === 'p_object' ? normalizeVisionStepForSave(step) : JSON.parse(JSON.stringify(step)),
  )

  emit('save', {
    camera: props.modelCameraForm.camera,
    model: props.modelCameraForm.model,
    confidence: props.modelCameraForm.confidence / 100,
    steps: normalizedSteps.map(step => ({
      id: step.id,
      name: step.name,
      type: step.type,
      hint: step.hint,
      target: step.target,
      timeout: step.timeout,
      context: { ...(step.context || {}) },
      doneWhen: [...(step.doneWhen || [])],
      ngWhen: [...(step.ngWhen || [])],
    })),
  })
}

const handlePointPointsOperator = (selectAll: boolean, side: 'l' | 'r') => {
  if (!currentStep.value) return
  ensureContext()
  currentStep.value.context.handPoints[side] = selectAll ? [...ALL_HAND_POINTS] : []
}

const handleClosed = () => emit('close');
//机器人浮动
const executionPreviewPinned = ref(true);
const executionPreviewHovered = ref(false);
const executionPreviewDismissedWhileHover = ref(false);
const assistantPlanListRef = ref<HTMLOListElement | null>(null)
const showPlanScrollTopHint = ref(false)
const showPlanScrollBottomHint = ref(false)

const updatePlanScrollHints = () => {
  const element = assistantPlanListRef.value
  if (!element) {
    showPlanScrollTopHint.value = false
    showPlanScrollBottomHint.value = false
    return
  }

  const canScroll = element.scrollHeight - element.clientHeight > 1
  if (!canScroll) {
    showPlanScrollTopHint.value = false
    showPlanScrollBottomHint.value = false
    return
  }

  showPlanScrollTopHint.value = element.scrollTop > 2
  showPlanScrollBottomHint.value = element.scrollTop + element.clientHeight < element.scrollHeight - 2
}

const handlePlanScroll = () => updatePlanScrollHints()

const handleWindowResize = () => {
  updatePlanScrollHints()
}

const executionPreviewVisible = computed(() => {
  if (executionPreviewPinned.value) return true;
  return (executionPreviewHovered.value &&!executionPreviewDismissedWhileHover.value);
});

watch(
  [
    executionPreviewVisible,
    () => currentValidation.value.valid,
    () => currentValidation.value.plan.length,
    () => currentStep.value?.target,
  ],
  async () => {
    await nextTick()
    updatePlanScrollHints()
  },
  { immediate: true },
)

onMounted(() => {
  window.addEventListener('resize', handleWindowResize)
  nextTick(() => {
    updatePlanScrollHints()
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
})

const handleExecutionPreviewEnter = () => {
  executionPreviewHovered.value = true
};

const handleExecutionPreviewLeave = () => {
  executionPreviewHovered.value = false
  executionPreviewDismissedWhileHover.value = false
};

const pinExecutionPreview = () => {
  executionPreviewPinned.value = true
  executionPreviewDismissedWhileHover.value = false
};

const hideExecutionPreview = () => {
  executionPreviewPinned.value = false
  executionPreviewDismissedWhileHover.value = true
};
</script>

<style scoped lang="scss">
.ghost { opacity: 0.5; background: var(--bs-info-color); }
.confidence-value { margin-left: 5px; }
.sop-layout { height: 100%; min-height: 0; overflow: hidden; background: #fff; color: #000; }
.config-container { height: 100%; padding: 5px; box-sizing: border-box; }
.steps-sidebar, .right-sidebar { display: flex; flex-direction: column; }
.config-title { position: relative; text-align: center; border-bottom: 1px solid #000; font-size: 18px; font-weight: 600; padding: 5px 0; }
.delete-step { position: absolute; right: 5px; top: 8px; cursor: pointer; }
.step-list-wrapper { flex: 1; min-height: 0; overflow: auto; }
.step-item { padding: 12px; border-bottom: 1px solid var(--bs-radio-bscolor); cursor: pointer; display: flex; align-items: center; gap: 8px; }
.step-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.isActivate { background: var(--bs-primary-hover-icon-color); }
.add-step { width: 100%; }
.config-wrapper { padding: 0 12px 24px; overflow: auto; height: calc(100% - 42px); box-sizing: border-box; }
.help-icon { margin-left: 10px; cursor: help; }
.hands-point-container { display: flex; flex-direction: column; gap: 5px; padding: 8px; border: 1px dashed #000; }
.hands-point-wrapper { box-shadow: inset 0 0 5px rgba(0, 0, 0, 0.2); padding: 5px; background: var(--bs-element-bgcolor); display: flex; align-items: center; gap: 5px; }
.hands-point-field { border-right: 1px solid #000; padding-right: 8px; }
.point-tags { display: flex; gap: 5px; flex-wrap: wrap; }
.hands-point-operator { margin-left: auto; display: flex; gap: 8px; cursor: pointer; }
// .validation-alert { margin-top: 16px; }
.right-sidebar-wrapper { flex: 1; min-height: 0; overflow: auto; }
/* =========================================================
 * SOP 执行链浮动助手
 * ======================================================= */

.sop-execution-assistant {
  position: fixed;
  right: 28px;
  bottom: 84px;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  .assistant-preview-panel {
    position: absolute;
    right: 0;
    bottom: 96px;
    width: min(390px, calc(100vw - 48px));
    max-height: min(520px, calc(100vh - 180px));
    display: flex;
    flex-direction: column;
    overflow: visible;
    border: 1px solid var(--el-border-color-light);
    background: var(--bs-bgcolor);
    border-radius: 14px;
    color: #000;
    box-shadow:0 18px 48px rgba(0, 0, 0, 0.2),0 4px 12px rgba(0, 0, 0, 0.1);
    .assistant-preview-header {
      flex-shrink: 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      min-height: 58px;
      padding: 10px 12px 10px 14px;
      border-bottom: 1px solid var(--el-border-color-lighter);
      border-radius: 14px 14px 0 0;
      color:#fff;
      background:linear-gradient(135deg, var(--faivs-color-1), var(--faivs-color-2));
      .assistant-preview-title {
        min-width: 0;
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 15px;
        font-weight: 600;

        small {
          display: block;
          max-width: 270px;
          margin-top: 2px;
          overflow: hidden;
          font-size: 12px;
          font-weight: 400;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .assistant-title-robot {
          flex: 0 0 42px;
          width: 42px;
          height: 42px;
          display: flex;
          align-items: center;
          justify-content: center;
          img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: contain;
            pointer-events: none;
            user-select: none;
            filter: drop-shadow(0 0 10px #fff);
          }
        }
        
      }
      .assistant-close-button {
        flex-shrink: 0;
        color:#fff !important;
      }
    }
    .assistant-preview-content {
      flex: 1;
      min-height: 0;
      padding: 14px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      .assistant-valid-content {
        display: flex;
        flex: 1;
        min-height: 0;
        flex-direction: column;
      }
      .assistant-message {
        flex-shrink: 0;
        margin-bottom: 12px;
        color: var(--el-text-color-regular);
        font-size: 14px;
        line-height: 1.6;
      }
      .assistant-execution-plan {
        flex: 1;
        min-height: 0;
        display: flex;
        flex-direction: column;
        gap: 9px;
        margin: 0;
        padding: 0;
        list-style: none;
        overflow-y: auto;

        li {
          display: flex;
          align-items: flex-start;
          gap: 9px;
          padding: 9px 10px;
          border: 1px solid var(--el-border-color-lighter);
          border-radius: 8px;
          background: #fff;
          font-size: 13px;
          line-height: 1.55;
          .assistant-plan-index {
            flex: 0 0 22px;
            width: 22px;
            height: 22px;
            display: inline-flex;
            justify-content: center;
            align-items: center;
            border-radius: 50%;
            background: var(--bs-primary-color);
            color: #fff;
            font-size: 12px;
            font-weight: 600;
          }
        }
      }
      .assistant-plan-scroll-wrapper {
        position: relative;
        display: flex;
        flex: 1;
        min-height: 0;
      }
      .assistant-scroll-hint {
        position: absolute;
        left: 50%;
        z-index: 2;
        width: 24px;
        height: 24px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border: 1px solid var(--el-border-color-lighter);
        border-radius: 50%;
        background: var(--bs-primary-hover-icon-color);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
        transform: translateX(-50%);
        pointer-events: none;
      }
      .assistant-scroll-hint-top {
        top: 0px;
      }
      .assistant-scroll-hint-bottom {
        bottom: 6px;
      }
      .assistant-baseline-note {
        flex-shrink: 0;
        display: flex;
        align-items: flex-start;
        gap: 7px;
        margin-top: 13px;
        padding: 9px 10px;
        color: var(--bs-turquoise-color);
        font-size: 14px;
        .el-icon {
          flex-shrink: 0;
          margin-top: 2px;
          color: var(--bs-turquoise-color);
        }
      }
      .assistant-empty {
        flex: 1;
        min-height: 0;
        padding: 18px 10px;
        color: var(--el-text-color-secondary);
        text-align: center;
        font-size: 13px;
        overflow-y: auto;
      }
      .assistant-invalid-message {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 12px;
        // border: 1px solid var(--el-color-danger-light-7);
        border-radius: 9px;
        background: var(--bs-alert-error-bgcolor);

        > .el-icon {
          flex-shrink: 0;
          margin-top: 2px;
          color: var(--bs-danger-color);
          font-size: 20px;
        }

        strong {
          color: var(--bs-danger-color);
          font-size: 14px;
        }

        p {
          margin: 6px 0 0;
          color: #000;
          font-size: 13px;
          line-height: 1.55;
        }
      }
    }
    .assistant-bubble-arrow {
      position: absolute;
      right: 32px;
      bottom: -7px;
      width: 14px;
      height: 14px;
      border-right: 1px solid var(--el-border-color-light);
      border-bottom: 1px solid var(--el-border-color-light);
      background: var(--bs-bgcolor);
      transform: rotate(45deg);
    }
  }
  .assistant-robot-button {
    position: relative;
    width: 82px;
    height: 82px;
    padding: 0;
    border: none;
    background: transparent;
    cursor: pointer;
    outline: none;
    transition:transform 0.2s ease,filter 0.2s ease;
    animation: assistant-robot-normal 1.8s ease-in-out infinite;
    &:hover,
    &.is-open {
      transform: translateY(-4px) scale(1.06);
    }
    &:focus-visible {
      border-radius: 16px;
      outline: 2px solid var(--el-color-primary);
      outline-offset: 3px;
    }

    &.has-error {
      animation: assistant-robot-error 1.8s ease-in-out infinite;
    }
    .assistant-robot-image {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: contain;
      pointer-events: none;
      user-select: none;
      filter:
        drop-shadow(0 8px 8px rgba(0, 0, 0, 0.2))
        drop-shadow(0 2px 3px rgba(0, 0, 0, 0.15));
      transition: filter 0.2s ease;
    }
    .assistant-error-dot {
      position: absolute;
      top: 5px;
      right: 4px;
      // width: 13px;
      // height: 13px;
      // border: 3px solid var(--bs-bgcolor);
      // border-radius: 50%;
      // background: var(--bs-danger-color);
      // box-shadow: 0 0 0 2px rgba(245, 108, 108, 0.2);
      pointer-events: none;
    }
  }
  .assistant-robot-button:hover .assistant-robot-image,
  .assistant-robot-button.is-open .assistant-robot-image {
    filter:
      drop-shadow(0 12px 12px rgba(0, 0, 0, 0.24))
      drop-shadow(0 3px 4px rgba(0, 0, 0, 0.16));
  }
}
/* 打开/关闭动画 */
.assistant-bubble-enter-active,
.assistant-bubble-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
  transform-origin: right bottom;
}

.assistant-bubble-enter-from,
.assistant-bubble-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.96);
}

/* 小屏幕适配 */
@media (max-width: 900px) {
  .assistant-robot-button {
    width: 68px;
    height: 68px;
  }

  .assistant-preview-panel {
    bottom: 82px;
  }

  .assistant-bubble-arrow {
    right: 25px;
  }
}
@keyframes assistant-robot-warning {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-4px);
  }
}
@keyframes assistant-robot-normal {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-4px);
  }
}

@keyframes assistant-robot-error {
  0%,
  100% {
    transform: translateX(0) rotate(0deg) scale(1);
  }
  15% {
    transform: translateX(-8px) rotate(-5deg) scale(1.02);
  }
  30% {
    transform: translateX(8px) rotate(5deg) scale(0.98);
  }
  45% {
    transform: translateX(-6px) rotate(-3deg);
  }
  60% {
    transform: translateX(6px) rotate(3deg);
  }
  80% {
    transform: translateX(-3px) rotate(-1deg);
  }
}
</style>
