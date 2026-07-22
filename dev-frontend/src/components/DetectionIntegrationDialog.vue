<template>
  <el-dialog
    :model-value="visible"
    :title="$t('config.detection_integration_config')"
    width="60%"
    top="10vh"
    modal-class="bs-shade"
    destroy-on-close
    @closed="handleClosed"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-scrollbar max-height="65vh">
      <div class="integration-form">
        <section class="config-section">
          <div class="section-heading">
            <div>
              <div class="section-title">{{ $t('config.trigger_methods') }}</div>
              <div class="section-description">
                {{ $t('config.trigger_methods_description') }}
              </div>
            </div>
          </div>

          <div class="trigger-list">
            <div class="trigger-item">
              <div class="setting-row">
                <div>
                  <div class="setting-title">{{ $t('config.http_api_trigger') }}</div>
                  <div class="setting-description">
                    {{ $t('config.http_api_trigger_description') }}
                  </div>
                </div>
                <el-switch v-model="form.triggers.httpApi" />
              </div>

              <div v-if="form.triggers.httpApi" class="trigger-details">
                <div class="detail-toolbar">
                  <span>{{ $t('config.http_parameter_count', { count: form.triggers.httpParameters.length }) }}</span>
                  <el-button
                    type="primary"
                    plain
                    :icon="Plus"
                    :disabled="form.triggers.httpParameters.length >= MAX_HTTP_PARAMETERS"
                    @click="addHttpParameter"
                  >
                    {{ $t('config.add_http_parameter') }}
                  </el-button>
                </div>

                <div v-if="form.triggers.httpParameters.length === 0" class="empty-detail">
                  {{ $t('config.no_http_parameters') }}
                </div>
                <div v-else class="detail-list">
                  <el-row
                    v-for="(_, index) in form.triggers.httpParameters"
                    :key="index"
                    :gutter="12"
                    class="detail-row"
                    align="middle"
                  >
                    <el-col :span="22">
                      <el-input
                        v-model="form.triggers.httpParameters[index]"
                        :placeholder="$t('config.http_parameter_name_placeholder')"
                        maxlength="50"
                      />
                    </el-col>
                    <el-col :span="2" class="delete-column">
                      <el-icon color="red" size="20px" @click="removeHttpParameter(index)">
                        <Delete />
                      </el-icon>
                    </el-col>
                  </el-row>
                </div>
              </div>
            </div>

            <div class="trigger-item">
              <div class="setting-row">
                <div>
                  <div class="setting-title">{{ $t('config.usb_scanner_trigger') }}</div>
                  <div class="setting-description">
                    {{ $t('config.usb_scanner_trigger_description') }}
                  </div>
                </div>
                <el-switch v-model="form.triggers.usbScanner" />
              </div>

              <div v-if="form.triggers.usbScanner" class="trigger-details">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-form-item :label="$t('config.usb_min_length')">
                      <el-input-number
                        v-model="form.triggers.usbScannerLength.min"
                        :min="1"
                        :max="9999"
                        :step="1"
                        step-strictly
                        style="width: 100%"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item :label="$t('config.usb_max_length')">
                      <el-input-number
                        v-model="form.triggers.usbScannerLength.max"
                        :min="1"
                        :max="9999"
                        :step="1"
                        step-strictly
                        style="width: 100%"
                      />
                    </el-form-item>
                  </el-col>
                </el-row>
              </div>
            </div>

            <div class="trigger-item">
              <div class="setting-row">
                <div>
                  <div class="setting-title">{{ $t('config.modbus_trigger') }}</div>
                  <div class="setting-description">
                    {{ $t('config.modbus_trigger_description') }}
                  </div>
                </div>
                <el-switch v-model="form.triggers.modbus" />
              </div>

              <div v-if="form.triggers.modbus" class="trigger-details">
                <div class="detail-toolbar">
                  <span>{{ $t('config.modbus_signal_count', { count: form.triggers.modbusSignals.length }) }}</span>
                  <el-button
                    type="primary"
                    plain
                    :icon="Plus"
                    :disabled="form.triggers.modbusSignals.length >= MAX_MODBUS_SIGNALS"
                    @click="addModbusSignal"
                  >
                    {{ $t('config.add_modbus_signal') }}
                  </el-button>
                </div>

                <div v-if="form.triggers.modbusSignals.length === 0" class="empty-detail">
                  {{ $t('config.no_modbus_signals') }}
                </div>
                <div v-else class="detail-list">
                  <div
                    v-for="(signal, index) in form.triggers.modbusSignals"
                    :key="index"
                    class="modbus-signal-card"
                  >
                    <div class="signal-header">
                      <span>{{ $t('config.modbus_signal') }} {{ index + 1 }}</span>
                      <el-icon color="red" size="20px" @click="removeModbusSignal(index)">
                        <Delete />
                      </el-icon>
                    </div>

                    <el-row :gutter="12">
                      <el-col :span="5">
                        <el-form-item :label="$t('config.modbus_slave_address')">
                          <el-input-number
                            v-model="signal.slaveAddress"
                            :min="1"
                            :max="247"
                            :step="1"
                            step-strictly
                            controls-position="right"
                            style="width: 100%"
                          />
                        </el-form-item>
                      </el-col>
                      <el-col :span="7">
                        <el-form-item :label="$t('config.modbus_data_type')">
                          <el-select
                            v-model="signal.dataType"
                            @change="handleModbusDataTypeChange(signal)"
                          >
                            <el-option :label="$t('config.modbus_type_coil')" value="coil" />
                            <el-option :label="$t('config.modbus_type_discrete_input')" value="discreteInput" />
                            <el-option :label="$t('config.modbus_type_holding_register')" value="holdingRegister" />
                            <el-option :label="$t('config.modbus_type_input_register')" value="inputRegister" />
                          </el-select>
                        </el-form-item>
                      </el-col>
                      <el-col :span="6">
                        <el-form-item :label="$t('config.modbus_trigger_address')">
                          <el-input-number
                            v-model="signal.address"
                            :min="0"
                            :max="65535"
                            :step="1"
                            step-strictly
                            controls-position="right"
                            style="width: 100%"
                          />
                        </el-form-item>
                      </el-col>
                      <el-col :span="6">
                        <el-form-item :label="$t('config.modbus_trigger_value')">
                          <el-select
                            v-if="isBitDataType(signal.dataType)"
                            v-model="signal.triggerValue"
                          >
                            <el-option :label="$t('config.modbus_bit_on')" :value="true" />
                            <el-option :label="$t('config.modbus_bit_off')" :value="false" />
                          </el-select>
                          <el-input-number
                            v-else
                            v-model="signal.triggerValue"
                            :min="0"
                            :max="65535"
                            :step="1"
                            step-strictly
                            controls-position="right"
                            style="width: 100%"
                          />
                        </el-form-item>
                      </el-col>
                    </el-row>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="config-section">
          <div class="section-heading feedback-heading">
            <div>
              <div class="section-title">{{ $t('config.result_feedback') }}</div>
              <div class="section-description">
                {{ $t('config.result_feedback_description') }}
              </div>
            </div>
            <el-switch v-model="form.resultFeedback.enabled" />
          </div>

          <div class="endpoint-toolbar">
            <span class="endpoint-count">
              {{ $t('config.feedback_endpoint_count', { count: form.resultFeedback.endpoints.length }) }}
            </span>
            <el-button
              type="primary"
              plain
              :icon="Plus"
              :disabled="form.resultFeedback.endpoints.length >= MAX_ENDPOINTS"
              @click="addEndpoint"
            >
              {{ $t('config.add_feedback_endpoint') }}
            </el-button>
          </div>

          <el-empty
            v-if="form.resultFeedback.endpoints.length === 0"
            :description="$t('config.no_feedback_endpoints')"
            :image-size="72"
          />

          <div v-else class="endpoint-list">
            <div
              v-for="(endpoint, index) in form.resultFeedback.endpoints"
              :key="index"
              class="endpoint-card"
            >
              <div class="endpoint-card-header">
                <span>{{ $t('config.feedback_endpoint') }} {{ index + 1 }}</span>
                <div class="endpoint-actions">
                  <el-switch
                    v-model="endpoint.enabled"
                    :active-text="$t('config.feedback_endpoint_enabled')"
                  />
                  <el-icon size="20px" color="red" style="margin-left: 20px;" @click="removeEndpoint(index)"><Delete /></el-icon>
                  <!-- <el-button type="danger" text :icon="Delete" @click="removeEndpoint(index)"/> -->
                </div>
              </div>

              <el-row :gutter="12">
                <el-col :span="8">
                  <el-input
                    v-model="endpoint.name"
                    :placeholder="$t('config.feedback_endpoint_name_placeholder')"
                    maxlength="50"
                    show-word-limit
                  />
                </el-col>
                <el-col :span="16">
                  <el-input
                    v-model="endpoint.url"
                    :placeholder="$t('config.feedback_endpoint_url_placeholder')"
                    clearable
                  >
                    <template #prepend>POST</template>
                  </el-input>
                </el-col>
              </el-row>
            </div>
          </div>
        </section>
      </div>
    </el-scrollbar>

    <template #footer>
      <div class="dialog-footer">
        <el-button plain @click="handleCancel">
          {{ $t('button.cancel') }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ $t('button.save') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import api from '@/api/index'
import { MesAlertWTitle } from '@/assets/js/secondpk'

type ModbusDataType = 'coil' | 'discreteInput' | 'holdingRegister' | 'inputRegister'

interface ModbusTriggerSignal {
  slaveAddress: number
  dataType: ModbusDataType
  address: number
  triggerValue: boolean | number
}

interface TriggerConfig {
  httpApi: boolean
  httpParameters: string[]
  usbScanner: boolean
  usbScannerLength: {
    min: number
    max: number
  }
  modbus: boolean
  modbusSignals: ModbusTriggerSignal[]
}

interface FeedbackEndpoint {
  name: string
  url: string
  enabled: boolean
}

interface DetectionIntegrationConfig {
  triggers: TriggerConfig
  resultFeedback: {
    enabled: boolean
    endpoints: FeedbackEndpoint[]
  }
}

const MAX_ENDPOINTS = 5
const MAX_HTTP_PARAMETERS = 3
const MAX_MODBUS_SIGNALS = 3
const MODBUS_DATA_TYPES: ModbusDataType[] = [
  'coil',
  'discreteInput',
  'holdingRegister',
  'inputRegister',
]

const props = defineProps<{
  visible: boolean
  integrationConfig: DetectionIntegrationConfig
}>()

const emit = defineEmits<{
  (event: 'update:visible', value: boolean): void
  (event: 'update:integrationConfig', value: DetectionIntegrationConfig): void
}>()

const { t } = useI18n()
const saving = ref(false)

const clampInteger = (
  value: unknown,
  fallback: number,
  min: number,
  max: number,
): number => {
  const parsed = Number(value)
  if (!Number.isInteger(parsed)) return fallback
  return Math.min(max, Math.max(min, parsed))
}

const isBitDataType = (dataType: ModbusDataType): boolean =>
  dataType === 'coil' || dataType === 'discreteInput'

const normalizeHttpParameter = (parameter: unknown): string => {
  if (typeof parameter === 'string') return parameter
  if (parameter && typeof parameter === 'object' && 'name' in parameter) {
    return String(parameter.name || '')
  }
  return ''
}

const normalizeModbusSignal = (
  signal?: Partial<ModbusTriggerSignal>,
): ModbusTriggerSignal => {
  const dataType = MODBUS_DATA_TYPES.includes(signal?.dataType as ModbusDataType)
    ? signal?.dataType as ModbusDataType
    : 'coil'

  return {
    slaveAddress: clampInteger(signal?.slaveAddress, 1, 1, 247),
    dataType,
    address: clampInteger(signal?.address, 0, 0, 65535),
    triggerValue: isBitDataType(dataType)
      ? signal?.triggerValue === true || signal?.triggerValue === 1
      : clampInteger(signal?.triggerValue, 0, 0, 65535),
  }
}

const createForm = (
  config?: Partial<DetectionIntegrationConfig>,
): DetectionIntegrationConfig => {
  const triggers = config?.triggers
  const minLength = clampInteger(triggers?.usbScannerLength?.min, 1, 1, 9999)
  const maxLength = Math.max(
    minLength,
    clampInteger(triggers?.usbScannerLength?.max, 128, 1, 9999),
  )

  return {
    triggers: {
      httpApi: Boolean(triggers?.httpApi),
      httpParameters: Array.isArray(triggers?.httpParameters)
        ? triggers.httpParameters
            .slice(0, MAX_HTTP_PARAMETERS)
            .map((parameter) => normalizeHttpParameter(parameter))
        : [],
      usbScanner: Boolean(triggers?.usbScanner),
      usbScannerLength: {
        min: minLength,
        max: maxLength,
      },
      modbus: Boolean(triggers?.modbus),
      modbusSignals: Array.isArray(triggers?.modbusSignals)
        ? triggers.modbusSignals
            .slice(0, MAX_MODBUS_SIGNALS)
            .map((signal) => normalizeModbusSignal(signal))
        : [],
    },
    resultFeedback: {
      enabled: Boolean(config?.resultFeedback?.enabled),
      endpoints: Array.isArray(config?.resultFeedback?.endpoints)
        ? config.resultFeedback.endpoints.slice(0, MAX_ENDPOINTS).map((endpoint) => ({
            name: String(endpoint?.name || ''),
            url: String(endpoint?.url || ''),
            enabled: Boolean(endpoint?.enabled),
          }))
        : [],
    },
  }
}

const form = reactive<DetectionIntegrationConfig>(createForm(props.integrationConfig))

const syncForm = (config?: Partial<DetectionIntegrationConfig>) => {
  const nextForm = createForm(config)
  Object.assign(form.triggers, nextForm.triggers)
  form.resultFeedback.enabled = nextForm.resultFeedback.enabled
  form.resultFeedback.endpoints.splice(
    0,
    form.resultFeedback.endpoints.length,
    ...nextForm.resultFeedback.endpoints,
  )
}

watch(
  () => [props.visible, props.integrationConfig] as const,
  ([visible]) => {
    if (visible) syncForm(props.integrationConfig)
  },
  { immediate: true, deep: true },
)

const addHttpParameter = () => {
  if (form.triggers.httpParameters.length >= MAX_HTTP_PARAMETERS) {
    ElMessage.warning(t('config.max_http_parameters'))
    return
  }
  form.triggers.httpParameters.push('')
}

const removeHttpParameter = (index: number) => {
  form.triggers.httpParameters.splice(index, 1)
}

const addModbusSignal = () => {
  if (form.triggers.modbusSignals.length >= MAX_MODBUS_SIGNALS) {
    ElMessage.warning(t('config.max_modbus_signals'))
    return
  }
  form.triggers.modbusSignals.push(normalizeModbusSignal())
}

const removeModbusSignal = (index: number) => {
  form.triggers.modbusSignals.splice(index, 1)
}

const handleModbusDataTypeChange = (signal: ModbusTriggerSignal) => {
  signal.triggerValue = isBitDataType(signal.dataType) ? false : 0
}

const addEndpoint = () => {
  if (form.resultFeedback.endpoints.length >= MAX_ENDPOINTS) {
    ElMessage.warning(t('config.max_feedback_endpoints'))
    return
  }

  form.resultFeedback.endpoints.push({
    name: `API ${form.resultFeedback.endpoints.length + 1}`,
    url: '',
    enabled: true,
  })
}

const removeEndpoint = (index: number) => {
  form.resultFeedback.endpoints.splice(index, 1)
}

const isValidHttpUrl = (value: string): boolean => {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && Boolean(url.hostname)
  } catch {
    return false
  }
}

const validateTriggers = (): boolean => {
  if (form.triggers.httpApi) {
    if (!form.triggers.httpParameters.length) {
      ElMessage.warning(t('config.http_parameter_required'))
      return false
    }

    const parameterNames = new Set<string>()
    for (const parameter of form.triggers.httpParameters) {
      const name = parameter.trim()
      if (!name) {
        ElMessage.warning(t('config.http_parameter_fields_required'))
        return false
      }
      if (parameterNames.has(name)) {
        ElMessage.warning(t('config.duplicate_http_parameter'))
        return false
      }
      parameterNames.add(name)
    }
  }

  if (form.triggers.usbScanner) {
    const minLength = Number(form.triggers.usbScannerLength.min)
    const maxLength = Number(form.triggers.usbScannerLength.max)
    if (
      !Number.isInteger(minLength) ||
      !Number.isInteger(maxLength) ||
      minLength < 1 ||
      maxLength < minLength
    ) {
      ElMessage.warning(t('config.invalid_usb_length_range'))
      return false
    }
  }

  if (form.triggers.modbus) {
    if (!form.triggers.modbusSignals.length) {
      ElMessage.warning(t('config.modbus_signal_required'))
      return false
    }

    for (const signal of form.triggers.modbusSignals) {
      if (
        !Number.isInteger(signal.slaveAddress) ||
        signal.slaveAddress < 1 ||
        signal.slaveAddress > 247 ||
        !Number.isInteger(signal.address) ||
        signal.address < 0 ||
        signal.address > 65535
      ) {
        ElMessage.warning(t('config.invalid_modbus_signal'))
        return false
      }

      if (
        !isBitDataType(signal.dataType) &&
        (typeof signal.triggerValue !== 'number' ||
          !Number.isInteger(signal.triggerValue) ||
          signal.triggerValue < 0 ||
          signal.triggerValue > 65535)
      ) {
        ElMessage.warning(t('config.invalid_modbus_register_value'))
        return false
      }
    }
  }

  return true
}

const validateFeedback = (): boolean => {
  if (!form.resultFeedback.enabled) return true

  const enabledEndpoints = form.resultFeedback.endpoints.filter(
    (endpoint) => endpoint.enabled,
  )
  if (!enabledEndpoints.length) {
    ElMessage.warning(t('config.feedback_enabled_endpoint_required'))
    return false
  }

  for (const endpoint of enabledEndpoints) {
    if (!endpoint.name.trim() || !endpoint.url.trim()) {
      ElMessage.warning(t('config.feedback_endpoint_required'))
      return false
    }
    if (!isValidHttpUrl(endpoint.url.trim())) {
      ElMessage.warning(t('config.invalid_feedback_url'))
      return false
    }
  }

  return true
}

const buildPayload = (): DetectionIntegrationConfig => ({
  triggers: {
    httpApi: Boolean(form.triggers.httpApi),
    httpParameters: form.triggers.httpParameters
      .slice(0, MAX_HTTP_PARAMETERS)
      .map((parameter) => parameter.trim()),
    usbScanner: Boolean(form.triggers.usbScanner),
    usbScannerLength: {
      min: Number(form.triggers.usbScannerLength.min),
      max: Number(form.triggers.usbScannerLength.max),
    },
    modbus: Boolean(form.triggers.modbus),
    modbusSignals: form.triggers.modbusSignals
      .slice(0, MAX_MODBUS_SIGNALS)
      .map((signal) => ({
        slaveAddress: Number(signal.slaveAddress),
        dataType: signal.dataType,
        address: Number(signal.address),
        triggerValue: isBitDataType(signal.dataType)
          ? Boolean(signal.triggerValue)
          : Number(signal.triggerValue),
      })),
  },
  resultFeedback: {
    enabled: Boolean(form.resultFeedback.enabled),
    endpoints: form.resultFeedback.endpoints.slice(0, MAX_ENDPOINTS).map((endpoint) => ({
      name: endpoint.name.trim(),
      url: endpoint.url.trim(),
      enabled: Boolean(endpoint.enabled),
    })),
  },
})

const handleSave = async () => {
  if (!validateTriggers() || !validateFeedback()) return

  saving.value = true
  const payload = buildPayload()
  try {
    const { data: response } = await api.modifyConfig({
      detectionIntegration: payload,
    })
    if (!response.status) {
      MesAlertWTitle(
        'error',
        t('message.error'),
        t('message.messagetext.failedsave'),
        response.msg,
        t('button.ok'),
      )
      return
    }

    emit('update:integrationConfig', payload)
    emit('update:visible', false)
    ElMessage.success(t('message.messagetext.successsave'))
  } catch (error: any) {
    MesAlertWTitle(
      'error',
      t('message.error'),
      t('message.messagetext.failedsave'),
      error?.message || t('message.messagetext.error_service'),
      t('button.ok'),
    )
  } finally {
    saving.value = false
  }
}

const handleCancel = () => emit('update:visible', false)
const handleClosed = () => syncForm(props.integrationConfig)
</script>

<style scoped>
.integration-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-right: 10px;
  color:#000;
}

.config-section {
  border-left: 5px solid var(--bs-primary-color);
  background: var(--bs-bgcolor);
  padding: 18px;
}

.section-heading,
.setting-row,
.endpoint-toolbar,
.endpoint-card-header,
.endpoint-actions {
  display: flex;
  align-items: center;
}

.section-heading,
.setting-row,
.endpoint-toolbar,
.endpoint-card-header {
  justify-content: space-between;
}

.section-title {
  font-size: 17px;
  font-weight: 700;
}

.section-description,
.setting-description,
.endpoint-count {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.trigger-list,
.endpoint-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.setting-row,
.endpoint-card {
  padding: 13px 14px;
  border-bottom: 1px solid var(--bs-info-color);
}

.setting-title,
.endpoint-card-header {
  font-weight: 700;
}

.feedback-heading {
  gap: 20px;
}

.endpoint-toolbar {
  margin-top: 14px;
}

.endpoint-card-header {
  margin-bottom: 12px;
}

.endpoint-actions {
  gap: 8px;
}

.trigger-details {
  margin: 0 14px 14px;
  padding: 14px;
  background: var(--el-fill-color-lighter);
}

.detail-toolbar,
.signal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 700;
}

.detail-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.detail-row {
  width: 100%;
  margin-left: 0 !important;
  margin-right: 0 !important;
}

.empty-detail {
  padding: 18px 0 4px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.delete-column,
.signal-header .el-icon,
.endpoint-actions .el-icon {
  display: flex;
  justify-content: center;
  cursor: pointer;
}

.modbus-signal-card {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--bs-bgcolor);
}

.signal-header {
  margin-bottom: 10px;
}

:deep(.trigger-details .el-form-item) {
  margin-bottom: 0;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
