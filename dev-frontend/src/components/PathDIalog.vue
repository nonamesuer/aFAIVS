<template>
  <el-dialog
    :model-value="visible"
    :title="$t('config.path_config')"
    width="50%"
    modal-class="bs-shade"
    destroy-on-close
    @closed="handleClosed"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form
      ref="pathFormRef"
      :model="pathForm"
      label-position="top"
      size="large"
    >
      <el-form-item :label="$t('config.model_path')" prop="modelPath">
        <el-input
          v-model="pathForm.modelPath"
          :placeholder="$t('config.enter_model_path')"
          clearable
        />
      </el-form-item>

      <el-form-item :label="$t('config.sop_path')" prop="sopPath">
        <el-input
          v-model="pathForm.sopPath"
          :placeholder="$t('config.enter_sop_path')"
          clearable
        />
      </el-form-item>

      <el-form-item
        :label="$t('config.result_storage_path')"
        prop="resultPath"
      >
        <el-input
          v-model="pathForm.resultPath"
          :placeholder="$t('config.enter_result_storage_path')"
          clearable
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel" plain>
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
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import api from '@/api/index'
import { MesAlertWTitle } from '@/assets/js/secondpk'

interface PathConfig {
  modelPath: string
  sopPath: string
  resultPath: string
  saveDetectionDatasets: boolean
}

const props = defineProps<{
  visible: boolean
  pathConfig: PathConfig
}>()

const emit = defineEmits<{
  (event: 'update:visible', value: boolean): void
  (event: 'update:pathConfig', value: PathConfig): void
  (event: 'saved'): void
}>()

const { t } = useI18n()
const pathFormRef = ref()
const saving = ref(false)
const pathForm = ref<PathConfig>(createPathForm())

function createPathForm(config?: Partial<PathConfig>): PathConfig {
  return {
    modelPath: config?.modelPath || '',
    sopPath: config?.sopPath || '',
    resultPath: config?.resultPath || '',
    saveDetectionDatasets: Boolean(config?.saveDetectionDatasets),
  }
}

watch(
  () => [props.visible, props.pathConfig] as const,
  ([visible]) => {
    if (visible) {
      pathForm.value = createPathForm(props.pathConfig)
    }
  },
  { immediate: true, deep: true },
)

const handleSave = async () => {
  saving.value = true

  try {
    const payload = createPathForm(pathForm.value)
    const { data: response } = await api.setConfigPath(payload)

    if (!response.status) {
      MesAlertWTitle(
        'error',
        t('message.error'),
        t('message.messagetext.failedsetconfigpath'),
        response.msg,
        t('button.ok'),
      )
      return
    }

    emit('update:pathConfig', payload)
    emit('saved')
    emit('update:visible', false)
    ElMessage.success(t('message.messagetext.successsave'))
  } catch (error: any) {
    MesAlertWTitle(
      'error',
      t('message.error'),
      t('message.messagetext.failedsetconfigpath'),
      error?.message || t('message.messagetext.error_service'),
      t('button.ok'),
    )
  } finally {
    saving.value = false
  }
}

const handleCancel = () => {
  emit('update:visible', false)
}

const handleClosed = () => {
  pathForm.value = createPathForm(props.pathConfig)
}
</script>

<style scoped>
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
