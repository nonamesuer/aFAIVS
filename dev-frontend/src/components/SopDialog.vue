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
                  <span class="step-num">{{ index + 1 }}</span>
                  <span class="step-name">{{ step.name || 'Unnamed step' }}</span>
                  <el-tag effect="dark" :type="getStepTypeLabel(step.type)[1]">
                    {{ getStepTypeLabel(step.type)[0] }}
                  </el-tag>
                  <el-icon v-if="!validateVisionStep(step).valid" color="var(--el-color-danger)">
                    <WarningFilled />
                  </el-icon>
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

              <el-alert
                class="validation-alert"
                :type="currentValidation.valid ? 'success' : 'error'"
                :closable="false"
                show-icon
                :title="currentValidation.valid ? '当前组合有效' : currentValidation.message"
              >
                <template #default>
                  <div v-if="currentValidation.valid && currentValidation.plan.length">
                    <div class="plan-title">本轮执行链：</div>
                    <ol class="execution-plan">
                      <li v-for="item in currentValidation.plan" :key="item">{{ item }}</li>
                    </ol>
                    <div class="baseline-note">
                      target &gt; 1 时，每轮都会重新记录开始区域和目标区域数量基线，只接受相对基线的新变化。
                    </div>
                  </div>
                </template>
              </el-alert>
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
import { Delete, Setting } from '@element-plus/icons-vue'
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

const handleClosed = () => emit('close')
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
.validation-alert { margin-top: 16px; }
.plan-title { font-weight: 600; margin-bottom: 4px; }
.execution-plan { margin: 4px 0 8px 20px; padding: 0; }
.baseline-note { color: var(--el-text-color-secondary); }
.right-sidebar-wrapper { flex: 1; min-height: 0; overflow: auto; }
</style>
