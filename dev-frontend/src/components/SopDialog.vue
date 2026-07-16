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
        <el-form-item :label="$t('config.model')" prop="model" required>
          <el-select
            v-model="modelCameraForm.model"
            style="width: 200px"
            @change="(model) => $emit('modelChanged', model)"
          >
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
                  <el-icon size="20px" v-if="!validateVisionStep(step).valid" color="var(--bs-danger-color)"><WarningFilled /></el-icon>
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
                      <el-tag
                        v-for="point in currentStep.context.handPoints[side]"
                        :key="point"
                        effect="dark"
                        round
                        size="small"
                      >
                        {{ point }}
                      </el-tag>
                    </div>
                    <div class="hands-point-operator">
                      <el-icon color="var(--bs-success-color)" @click="handlePointPointsOperator(true, side)">
                        <CircleCheck />
                      </el-icon>
                      <el-icon @click="handlePointPointsOperator(false, side)">
                        <CircleClose />
                      </el-icon>
                    </div>
                  </div>
                </div>
              </el-form>

              <!-- <el-alert
                v-if="!currentValidation.valid"
                class="validation-alert"
                type="error"
                :closable="false"
                show-icon
                :title="currentValidation.message"
              /> -->
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
    <div
      v-if="modelCameraForm.model && visible && currentStep"
      class="sop-execution-assistant"
      @mouseenter="handleExecutionPreviewEnter"
      @mouseleave="handleExecutionPreviewLeave"
    >
      <!-- 对话气泡 -->
      <transition name="assistant-bubble">
        <section v-show="executionPreviewVisible" class="assistant-preview-panel" @click.stop>
          <header class="assistant-preview-header">
            <div class="assistant-preview-title">
              <el-icon class="assistant-title-icon">
                <Cpu />
              </el-icon>
              <div>
                <div>执行链助手</div>
                <small>{{ currentStep.name || `工序 ${activeStepIndex + 1}` }}</small>
              </div>
            </div>

            <el-button class="assistant-close-button" link circle title="隐藏执行链预览" @click.stop="hideExecutionPreview">
              <el-icon>
                <Close />
              </el-icon>
            </el-button>
          </header>

          <div class="assistant-preview-content">
            <!-- 合法配置 -->
            <template v-if="currentValidation.valid">
              <div class="assistant-message">
                当前配置有效，系统将按照以下顺序执行：
              </div>
              <ol v-if="currentValidation.plan.length" class="assistant-execution-plan">
                <li v-for="(item, index) in currentValidation.plan" :key="`${index}-${item}`">
                  <span class="assistant-plan-index">{{ index + 1 }}</span>
                  <span>{{ item }}</span>
                </li>
              </ol>
              <div v-else class="assistant-empty">
                当前工序没有需要预览的视觉执行阶段。
              </div>
              <div v-if="Number(currentStep.target || 1) > 1" class="assistant-baseline-note">
                <el-icon>
                  <InfoFilled />
                </el-icon>
                <span>
                  当前工序需要执行 {{ currentStep.target }} 次。每轮都会重新记录开始区域和目标区域的数量基线，只计算相对于基线产生的新变化。
                </span>
              </div>
            </template>
            <!-- 非法配置 -->
            <template v-else>
              <div class="assistant-invalid-message">
                <el-icon>
                  <WarningFilled />
                </el-icon>
                <div>
                  <strong>当前配置暂时无法执行</strong>
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
        :title="executionPreviewVisible ? '执行链助手' : '悬浮查看执行链'"
        @click.stop="pinExecutionPreview"
      >
        <el-icon><Cpu /></el-icon>
        <span v-if="!currentValidation.valid" class="assistant-error-dot"></span>
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
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
// import { Delete, Setting } from '@element-plus/icons-vue'
import {
  Close,
  Cpu,
  Delete,
  InfoFilled,
  Setting,
  WarningFilled,
} from '@element-plus/icons-vue'
import { VueDraggable } from 'vue-draggable-plus'
import Hands from './Hands.vue'
import {
  normalizeObjectDetection,
  normalizeVisionStepForSave,
  validateVisionStep,
} from '@/assets/js/sopRuleEngine'

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
const ruleStepRef = ref<FormInstance>()

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
  currentStep.value?.type === 'p_object'
    ? validateVisionStep(currentStep.value)
    : { valid: true, code: '', message: '', plan: [] },
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
  for (let index = 0; index < stepsLocal.value.length; index += 1) {
    const rawStep = stepsLocal.value[index]
    if (!isStepRequiredFieldsValid(rawStep)) {
      activeStepIndex.value = index
      await nextTick()
      ElMessage.error(`步骤 ${rawStep?.id ?? index + 1}：名称、类型和目标次数不能为空`)
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
const executionPreviewPinned = ref(true)
const executionPreviewHovered = ref(false)
const executionPreviewDismissedWhileHover = ref(false)

const executionPreviewVisible = computed(() => {
  if (executionPreviewPinned.value) {
    return true
  }

  return (
    executionPreviewHovered.value &&
    !executionPreviewDismissedWhileHover.value
  )
})
/**
 * 鼠标进入整个助手区域。
 *
 * 当预览没有被固定时，悬浮机器人仍然可以临时打开预览。
 */
const handleExecutionPreviewEnter = () => {
  executionPreviewHovered.value = true
}

/**
 * 鼠标离开整个助手区域。
 *
 * 重置“本次悬浮期间主动关闭”的状态，
 * 从而允许下一次悬浮时重新显示。
 */
const handleExecutionPreviewLeave = () => {
  executionPreviewHovered.value = false
  executionPreviewDismissedWhileHover.value = false
}

/**
 * 用户点击机器人图标，固定打开执行链。
 */
const pinExecutionPreview = () => {
  executionPreviewPinned.value = true
  executionPreviewDismissedWhileHover.value = false
}

/**
 * 用户点击气泡右上角关闭按钮。
 *
 * 即使鼠标还停在气泡内，也应该立即关闭；
 * 下一次鼠标离开再重新进入时，才通过悬浮重新打开。
 */
const hideExecutionPreview = () => {
  executionPreviewPinned.value = false
  executionPreviewDismissedWhileHover.value = true
}
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
}

/* 机器人圆形入口 */
.assistant-robot-button {
  position: relative;
  width: 54px;
  height: 54px;
  padding: 0;
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 50%;
  background:
    linear-gradient(
      145deg,
      var(--el-color-primary-light-7),
      var(--el-color-primary)
    );
  color: #fff;
  box-shadow:
    0 8px 22px rgba(0, 0, 0, 0.18),
    0 2px 6px rgba(0, 0, 0, 0.12);
  cursor: pointer;
  outline: none;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    background 0.2s ease;

  .el-icon {
    font-size: 27px;
  }

  &:hover,
  &.is-open {
    transform: translateY(-2px) scale(1.04);
    box-shadow:
      0 12px 28px rgba(0, 0, 0, 0.22),
      0 3px 8px rgba(0, 0, 0, 0.14);
  }

  &.has-error {
    background:
      linear-gradient(
        145deg,
        var(--el-color-danger-light-5),
        var(--el-color-danger)
      );
    border-color: var(--el-color-danger-light-3);
  }
}

/* 非法配置时机器人上的红点 */
.assistant-error-dot {
  position: absolute;
  top: 1px;
  right: 1px;
  width: 11px;
  height: 11px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: var(--el-color-danger);
}

/* AI 对话气泡 */
.assistant-preview-panel {
  position: absolute;
  right: 0;
  bottom: 68px;
  width: min(390px, calc(100vw - 48px));
  max-height: min(520px, calc(100vh - 180px));
  display: flex;
  flex-direction: column;
  overflow: visible;
  border: 1px solid var(--el-border-color-light);
  border-radius: 14px;
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  box-shadow:
    0 18px 48px rgba(0, 0, 0, 0.2),
    0 4px 12px rgba(0, 0, 0, 0.1);
}

/* 对话气泡顶部 */
.assistant-preview-header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 58px;
  padding: 10px 12px 10px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  border-radius: 14px 14px 0 0;
  background:
    linear-gradient(
      135deg,
      var(--el-color-primary-light-9),
      var(--el-bg-color)
    );
}

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
    color: var(--el-text-color-secondary);
    font-size: 12px;
    font-weight: 400;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.assistant-title-icon {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 19px;
}

.assistant-close-button {
  flex-shrink: 0;
}

/* 可滚动的气泡内容 */
.assistant-preview-content {
  min-height: 0;
  padding: 14px;
  overflow-y: auto;
}

.assistant-message {
  margin-bottom: 12px;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.6;
}

/* 执行链列表 */
.assistant-execution-plan {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: flex;
    align-items: flex-start;
    gap: 9px;
    padding: 9px 10px;
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 8px;
    background: var(--el-fill-color-lighter);
    font-size: 13px;
    line-height: 1.55;
  }
}

.assistant-plan-index {
  flex: 0 0 22px;
  width: 22px;
  height: 22px;
  display: inline-flex;
  justify-content: center;
  align-items: center;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

/* target > 1 的数量基线说明 */
.assistant-baseline-note {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 13px;
  padding: 9px 10px;
  border-radius: 8px;
  background: var(--el-color-info-light-9);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.55;

  .el-icon {
    flex-shrink: 0;
    margin-top: 2px;
    color: var(--el-color-info);
  }
}

.assistant-empty {
  padding: 18px 10px;
  color: var(--el-text-color-secondary);
  text-align: center;
  font-size: 13px;
}

/* 非法配置时的助手消息 */
.assistant-invalid-message {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--el-color-danger-light-7);
  border-radius: 9px;
  background: var(--el-color-danger-light-9);

  > .el-icon {
    flex-shrink: 0;
    margin-top: 2px;
    color: var(--el-color-danger);
    font-size: 20px;
  }

  strong {
    color: var(--el-color-danger);
    font-size: 14px;
  }

  p {
    margin: 6px 0 0;
    color: var(--el-text-color-regular);
    font-size: 13px;
    line-height: 1.55;
  }
}

/* 指向机器人按钮的气泡小三角 */
.assistant-bubble-arrow {
  position: absolute;
  right: 18px;
  bottom: -7px;
  width: 14px;
  height: 14px;
  border-right: 1px solid var(--el-border-color-light);
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
  transform: rotate(45deg);
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
  .sop-execution-assistant {
    right: 16px;
    bottom: 76px;
  }

  .assistant-preview-panel {
    width: min(360px, calc(100vw - 32px));
    max-height: calc(100vh - 160px);
  }
}
</style>
