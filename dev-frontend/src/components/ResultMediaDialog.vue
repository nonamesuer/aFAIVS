<template>
  <el-dialog
    :model-value="visible"
    :title="$t('config.result_media.title')"
    width="620px"
    top="10vh"
    modal-class="bs-shade"
    destroy-on-close
    @closed="handleClosed"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-scrollbar max-height="65vh">
      <div class="media-config">
        <div class="setting-card">
          <div class="setting-row">
            <div>
              <div class="setting-title">{{ $t('config.result_media.enabled') }}</div>
              <div class="setting-description">
                {{ $t('config.result_media.enabled_description') }}
              </div>
            </div>
            <el-switch v-model="form.enabled" />
          </div>
        </div>

        <template v-if="form.enabled">
          <div class="setting-card">
            <div class="setting-row">
              <div>
                <div class="setting-title">
                  {{ $t('config.result_media.operation_error') }}
                </div>
                <div class="setting-description">
                  {{ $t('config.result_media.operation_error_description') }}
                </div>
              </div>
              <el-switch v-model="form.saveOperationError" />
            </div>

            <div v-if="form.saveOperationError" class="nested-settings">
              <el-checkbox v-model="form.saveNgRawImage">
                {{ $t('config.result_media.raw_image') }}
              </el-checkbox>
              <el-checkbox v-model="form.saveNgAnnotatedImage">
                {{ $t('config.result_media.annotated_image') }}
              </el-checkbox>
            </div>
          </div>

          <div class="setting-card">
            <div class="setting-row">
              <div>
                <div class="setting-title">
                  {{ $t('config.result_media.step_success') }}
                </div>
                <div class="setting-description">
                  {{ $t('config.result_media.step_success_description') }}
                </div>
              </div>
              <el-switch v-model="form.saveStepSuccess" />
            </div>
          </div>

          <div class="setting-card">
            <div class="setting-row">
              <div>
                <div class="setting-title">
                  {{ $t('config.result_media.run_completed') }}
                </div>
                <div class="setting-description">
                  {{ $t('config.result_media.run_completed_description') }}
                </div>
              </div>
              <el-switch v-model="form.saveRunCompleted" />
            </div>
          </div>

          <div class="setting-card form-card">
            <el-form label-position="top">
              <el-form-item :label="$t('config.result_media.jpeg_quality')">
                <el-slider
                  v-model="form.jpegQuality"
                  :min="60"
                  :max="100"
                  show-input
                />
              </el-form-item>

              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item :label="$t('config.result_media.min_free_disk')">
                    <el-input-number
                      v-model="form.minFreeDiskPercent"
                      :min="1"
                      :max="50"
                      :step="1"
                      step-strictly
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item :label="$t('config.result_media.queue_size')">
                    <el-input-number
                      v-model="form.queueSize"
                      :min="4"
                      :max="256"
                      :step="1"
                      step-strictly
                      style="width: 100%"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>
        </template>

        <el-alert
          :title="$t('config.result_media.apply_tip')"
          type="info"
          :closable="false"
          show-icon
        />
      </div>
    </el-scrollbar>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">
        {{ $t('button.cancel') }}
      </el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        {{ $t('button.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import api from '@/api/index'

interface ResultMediaConfig {
  enabled: boolean
  saveOperationError: boolean
  saveNgRawImage: boolean
  saveNgAnnotatedImage: boolean
  saveStepSuccess: boolean
  saveRunCompleted: boolean
  imageFormat: 'jpg'
  jpegQuality: number
  minFreeDiskPercent: number
  queueSize: number
}

const defaults: ResultMediaConfig = {
  enabled: true,
  saveOperationError: true,
  saveNgRawImage: true,
  saveNgAnnotatedImage: true,
  saveStepSuccess: true,
  saveRunCompleted: true,
  imageFormat: 'jpg',
  jpegQuality: 90,
  minFreeDiskPercent: 10,
  queueSize: 32,
}

const props = defineProps<{
  visible: boolean
  resultMediaConfig: ResultMediaConfig
}>()

const emit = defineEmits<{
  (event: 'update:visible', value: boolean): void
  (event: 'update:resultMediaConfig', value: ResultMediaConfig): void
}>()

const { t } = useI18n()
const saving = ref(false)
const form = reactive<ResultMediaConfig>({ ...defaults })

const normalize = (
  value?: Partial<ResultMediaConfig>,
): ResultMediaConfig => ({
  ...defaults,
  ...(value || {}),
  imageFormat: 'jpg',
  jpegQuality: Math.min(100, Math.max(60, Number(value?.jpegQuality ?? 90))),
  minFreeDiskPercent: Math.min(
    50,
    Math.max(1, Number(value?.minFreeDiskPercent ?? 10)),
  ),
  queueSize: Math.min(256, Math.max(4, Number(value?.queueSize ?? 32))),
})

const syncForm = () => Object.assign(form, normalize(props.resultMediaConfig))

watch(
  () => [props.visible, props.resultMediaConfig] as const,
  ([visible]) => {
    if (visible) syncForm()
  },
  { immediate: true, deep: true },
)

const handleSave = async () => {
  if (
    form.enabled &&
    form.saveOperationError &&
    !form.saveNgRawImage &&
    !form.saveNgAnnotatedImage
  ) {
    ElMessage.warning(t('config.result_media.ng_variant_required'))
    return
  }

  saving.value = true
  try {
    const payload = normalize(form)
    const response = await api.modifyConfig({ resultMedia: payload })
    if (!response.data?.status) {
      ElMessage.error(response.data?.msg || t('config.result_media.save_failed'))
      return
    }
    emit('update:resultMediaConfig', payload)
    emit('update:visible', false)
    ElMessage.success(t('config.result_media.save_success'))
  } catch (error: any) {
    ElMessage.error(
      error?.response?.data?.msg ||
        error?.message ||
        t('config.result_media.save_failed'),
    )
  } finally {
    saving.value = false
  }
}

const handleClosed = () => {
  syncForm()
}
</script>

<style scoped>
.media-config {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-right: 10px;
}

.setting-card {
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.setting-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.setting-description {
  margin-top: 5px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.nested-settings {
  display: flex;
  gap: 24px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.form-card :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}
</style>
