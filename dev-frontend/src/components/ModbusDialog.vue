<template>
  <el-dialog
    :model-value="visible"
    :title="$t('config.modbus_config')"
    width="520px"
    modal-class="bs-shade"
    destroy-on-close
    @closed="handleClosed"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form ref="modbusFormRef" :model="modbusForm" :rules="modbusRules" label-position="top" size="large">
      <el-form-item :label="$t('config.modbus_host')" prop="host">
        <el-input v-model="modbusForm.host" :placeholder="$t('config.enter_modbus_host')" clearable @input="resetTestStatus"/>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('config.modbus_port')" prop="port">
            <el-input-number
              v-model="modbusForm.port"
              :min="1"
              :max="65535"
              :step="1"
              step-strictly
              style="width: 100%"
              @change="resetTestStatus"
            />
          </el-form-item>
        </el-col>

        <el-col :span="12">
          <el-form-item :label="$t('config.modbus_timeout')" prop="timeout">
            <el-input-number
              v-model="modbusForm.timeout"
              :min="0.1"
              :max="60"
              :step="0.5"
              style="width: 100%"
              @change="resetTestStatus"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <div class="connection-test-row">
        <el-button
          type="primary"
          plain
          :loading="testing"
          @click="handleTestConnection"
        >
          {{ $t('button.test') }}
        </el-button>

        <div
          v-if="testStatus !== 'idle'"
          class="connection-status"
          :class="`is-${testStatus}`"
        >
          <el-icon v-if="testStatus === 'success'" size="26">
            <CircleCheckFilled />
          </el-icon>
          <el-icon v-else size="26">
            <CircleCloseFilled />
          </el-icon>
          <span>{{ testStatusText }}</span>
        </div>
      </div>
    </el-form>

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
import { computed, reactive, ref, watch } from 'vue'
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useI18n } from 'vue-i18n'
import api from '@/api/index'
import { MesAlertWTitle } from '@/assets/js/secondpk'

interface ModbusConfig {
  host: string
  port: number
  timeout: number
}

type TestStatus = 'idle' | 'success' | 'failed'

const props = defineProps<{
  visible: boolean
  modbusConfig: ModbusConfig
}>()

const emit = defineEmits<{
  (event: 'update:visible', value: boolean): void
  (event: 'update:modbusConfig', value: ModbusConfig): void
}>()

const { t } = useI18n()
const modbusFormRef = ref<FormInstance>()
const testing = ref(false)
const saving = ref(false)
const testStatus = ref<TestStatus>('idle')
const testMessage = ref('')

const createModbusForm = (config?: Partial<ModbusConfig>): ModbusConfig => ({
  host: String(config?.host || '127.0.0.1'),
  port: Number(config?.port ?? 502),
  timeout: Number(config?.timeout ?? 3),
})

const modbusForm = reactive<ModbusConfig>(createModbusForm(props.modbusConfig))

const modbusRules = reactive<FormRules<ModbusConfig>>({
  host: [
    {
      required: true,
      whitespace: true,
      message: t('config.enter_modbus_host'),
      trigger: ['blur', 'change'],
    },
  ],
  port: [
    {
      required: true,
      type: 'number',
      min: 1,
      max: 65535,
      message: t('config.invalid_modbus_port'),
      trigger: ['blur', 'change'],
    },
  ],
  timeout: [
    {
      required: true,
      type: 'number',
      min: 0.1,
      max: 60,
      message: t('config.invalid_modbus_timeout'),
      trigger: ['blur', 'change'],
    },
  ],
})

const testStatusText = computed(() => {
  if (testMessage.value) return testMessage.value
  return testStatus.value === 'success' ? t('message.messagetext.modbusConnectionSuccess') : t('message.messagetext.modbusConnectionFailed')
})

const resetTestStatus = () => {
  testStatus.value = 'idle'
  testMessage.value = ''
}

const syncForm = (config?: Partial<ModbusConfig>) => {
  Object.assign(modbusForm, createModbusForm(config))
  resetTestStatus()
}

watch(
  () => [props.visible, props.modbusConfig] as const,
  ([visible]) => {
    if (visible) syncForm(props.modbusConfig)
  },
  { immediate: true, deep: true },
)

const validateForm = async (): Promise<boolean> => {
  try {
    await modbusFormRef.value?.validate()
    return true
  } catch {
    return false
  }
}

const buildPayload = (): ModbusConfig => ({
  host: modbusForm.host.trim(),
  port: Number(modbusForm.port),
  timeout: Number(modbusForm.timeout),
})

const handleTestConnection = async () => {
  if (!(await validateForm())) return
  testing.value = true
  resetTestStatus()
  try {
    const { data: response } = await api.testModbusConnection(buildPayload());
    testStatus.value = response.status ? 'success' : 'failed'
    testMessage.value = response.status ? t('message.messagetext.modbusConnectionSuccess') : response.msg || t('message.messagetext.modbusConnectionFailed')
  } 
  catch (error: any) {
    testStatus.value = 'failed'
    testMessage.value = error?.message || t('message.messagetext.modbusConnectionFailed')
  }
   finally {
    testing.value = false
  }
}

const handleSave = async () => {
  if (!(await validateForm())) return
  saving.value = true
  const payload = buildPayload()
  try {
    const { data: response } = await api.modifyConfig({ modbus: payload })
    if (!response.status) {
      MesAlertWTitle('error',t('message.error'),t('message.messagetext.failedsave'),response.msg,t('button.ok'))
      return
    }
    emit('update:modbusConfig', payload)
    emit('update:visible', false)
    ElMessage.success(t('message.messagetext.successsave'))
  } catch (error: any) {
    MesAlertWTitle('error',t('message.error'),t('message.messagetext.failedsave'),error?.message || t('message.messagetext.error_service'),t('button.ok'))
  } finally {
    saving.value = false
  }
}

const handleCancel = () => emit('update:visible', false)

const handleClosed = () => syncForm(props.modbusConfig)
</script>

<style scoped>
.connection-test-row {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.connection-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-weight: 700;
}

.connection-status.is-success {
  color: var(--bs-success-color);
}

.connection-status.is-failed {
  color: var(--bs-danger-color);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
