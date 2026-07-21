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
            <div class="setting-row">
              <div>
                <div class="setting-title">{{ $t('config.http_api_trigger') }}</div>
                <div class="setting-description">
                  {{ $t('config.http_api_trigger_description') }}
                </div>
              </div>
              <el-switch v-model="form.triggers.httpApi" />
            </div>

            <div class="setting-row">
              <div>
                <div class="setting-title">{{ $t('config.usb_scanner_trigger') }}</div>
                <div class="setting-description">
                  {{ $t('config.usb_scanner_trigger_description') }}
                </div>
              </div>
              <el-switch v-model="form.triggers.usbScanner" />
            </div>

            <div class="setting-row">
              <div>
                <div class="setting-title">{{ $t('config.modbus_trigger') }}</div>
                <div class="setting-description">
                  {{ $t('config.modbus_trigger_description') }}
                </div>
              </div>
              <el-switch v-model="form.triggers.modbus" />
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

interface TriggerConfig {
  httpApi: boolean
  usbScanner: boolean
  modbus: boolean
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

const createForm = (
  config?: Partial<DetectionIntegrationConfig>,
): DetectionIntegrationConfig => ({
  triggers: {
    httpApi: Boolean(config?.triggers?.httpApi),
    usbScanner: Boolean(config?.triggers?.usbScanner),
    modbus: Boolean(config?.triggers?.modbus),
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
})

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
    usbScanner: Boolean(form.triggers.usbScanner),
    modbus: Boolean(form.triggers.modbus),
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
  if (!validateFeedback()) return

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

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
