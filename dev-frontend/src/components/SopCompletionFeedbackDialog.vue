<template>
  <el-dialog
    :model-value="visible"
    :title="$t('config.sop_step_config.sop_completion_feedback')"
    width="920px"
    append-to-body
    destroy-on-close
    modal-class="bs-shade"
    @open="resetDraft"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      :title="$t('config.sop_step_config.sop_completion_feedback')"
      :description="$t('config.sop_step_config.sop_completion_feedback_dialog_description')"
    />
    <section class="feedback-channel" :class="{ enabled: draft.modbus.enabled }">
      <header>
        <div class="channel-title">
          <span class="channel-icon">
            <el-icon><Connection /></el-icon>
          </span>
          <div>
            <b>Modbus</b>
            <small>{{ $t("config.sop_step_config.feedback_channel_modbus_description") }}</small>
          </div>
        </div>
        <div class="channel-status">
          <el-tag :type="draft.modbus.enabled ? 'success' : 'info'" effect="dark">
            {{ draft.modbus.enabled ? $t("config.sop_step_config.feedback_status_enabled_count", {
                    count: draft.modbus.signals.length,
                  })
                : $t("config.sop_step_config.feedback_status_disabled")
            }}</el-tag
          ><el-switch v-model="draft.modbus.enabled" />
        </div>
      </header>
      <div v-if="draft.modbus.enabled" class="channel-content">
        <div class="signal-toolbar">
          <div>
            <b>{{ $t("config.sop_step_config.sop_completion_signals") }}</b
            ><span>{{
              $t("config.sop_step_config.feedback_signal_count", {
                count: draft.modbus.signals.length,
              })
            }}</span>
          </div>
          <el-button
            type="primary"
            size="small"
            plain
            :disabled="draft.modbus.signals.length >= MAX_SIGNALS"
            @click="addSignal"
            >+ {{ $t("config.sop_step_config.add_feedback_signal") }}</el-button
          >
        </div>
        <el-empty
          v-if="!draft.modbus.signals.length"
          :description="$t('config.sop_step_config.no_feedback_signals')"
          :image-size="54"
        />
        <article v-for="(signal, index) in draft.modbus.signals" :key="index" class="signal-card">
          <el-form label-position="top">
            <el-row :gutter="10">
              <el-col :span="4"
                ><el-form-item :label="$t('config.modbus_slave_address')"
                  ><el-input-number
                    v-model.number="signal.slaveAddress"
                    :min="1"
                    :max="247"
                    controls-position="right" /></el-form-item
              ></el-col>
              <el-col :span="5"
                ><el-form-item :label="$t('config.modbus_data_type')"
                  ><el-select
                    v-model="signal.dataType"
                    @change="changeDataType(signal)"
                    ><el-option
                      :label="$t('config.modbus_type_coil')"
                      value="coil" /><el-option
                      :label="$t('config.modbus_type_holding_register')"
                      value="holdingRegister" /></el-select></el-form-item
              ></el-col>
              <el-col :span="4"
                ><el-form-item :label="$t('config.modbus_trigger_address')"
                  ><el-input-number
                    v-model.number="signal.address"
                    :min="0"
                    :max="65535"
                    controls-position="right" /></el-form-item
              ></el-col>
              <el-col :span="5"
                ><el-form-item :label="$t('config.modbus_trigger_value')"
                  ><el-select
                    v-if="signal.dataType === 'coil'"
                    v-model="signal.triggerValue"
                    ><el-option
                      :label="$t('config.modbus_bit_on')"
                      :value="true" /><el-option
                      :label="$t('config.modbus_bit_off')"
                      :value="false" /></el-select
                  ><el-input-number
                    v-else
                    v-model.number="signal.triggerValue"
                    :min="0"
                    :max="65535"
                    controls-position="right" /></el-form-item
              ></el-col>
              <el-col :span="4"
                ><el-form-item :label="$t('config.modbus_instantaneous')"
                  ><el-tooltip
                    v-if="signal.dataType === 'coil'"
                    :content="$t('config.modbus_instantaneous_description')"
                    placement="top"
                    ><el-switch v-model="signal.instantaneous" /></el-tooltip
                  ><span v-else class="coil-only">{{
                    $t("config.modbus_coil_only")
                  }}</span></el-form-item
                ></el-col
              >
              <el-col :span="2" class="delete-cell">
                <el-icon @click="draft.modbus.signals.splice(index, 1)" color="red" :title="$t('button.delete')" size="20px"><Delete /></el-icon></el-col>
            </el-row>
          </el-form>
        </article>
      </div>
    </section>
    <section class="feedback-channel" :class="{enabled:draft.audio.enabled}">
      <header><div class="channel-title"><span class="channel-icon"><el-icon><Headset /></el-icon></span><div><b>{{ $t('config.sop_step_config.audio_channel_name') }}</b><small>{{ $t('config.sop_step_config.feedback_channel_audio_description') }}</small></div></div><div class="channel-status"><el-tag :type="draft.audio.enabled ? 'success' : 'info'" effect="dark">{{ draft.audio.enabled ? $t('config.sop_step_config.feedback_status_audio_enabled') : $t('config.sop_step_config.feedback_status_disabled') }}</el-tag><el-switch v-model="draft.audio.enabled" /></div></header>
      <div v-if="draft.audio.enabled" class="channel-content audio-channel-content"><el-alert v-if="!availableAudioResources.length" type="warning" :closable="false" show-icon :title="$t('config.sop_step_config.audio_feedback_unavailable')"/><el-form label-position="top"><el-row :gutter="16"><el-col :span="13"><el-form-item :label="$t('config.sop_step_config.sop_completion_audio')"><el-select v-model="draft.audio.audioId" clearable filterable :placeholder="$t('config.sop_step_config.select_audio_resource')"><el-option v-for="audio in availableAudioResources" :key="audio.id" :label="audio.name" :value="audio.id"><span>{{ audio.name }}</span><small class="audio-option-file">{{ audio.originalName }}</small></el-option></el-select></el-form-item></el-col><el-col :span="7"><el-form-item :label="$t('config.sop_step_config.audio_volume')"><el-slider v-model="draft.audio.volume" :min="0" :max="100" show-input /></el-form-item></el-col><el-col :span="4" class="preview-cell"><el-button :disabled="!draft.audio.audioId" @click="togglePreview"><el-icon><VideoPause v-if="previewing"/><VideoPlay v-else/></el-icon>{{ previewing ? $t('config.audio_resources.stop') : $t('config.audio_resources.preview') }}</el-button></el-col></el-row></el-form></div>
    </section>
    <template #footer
      ><div class="dialog-footer">
        <el-button @click="$emit('update:visible', false)" plain>{{ $t("button.cancel") }}</el-button
        ><el-button type="primary" @click="save">{{
          $t("button.save")
        }}</el-button>
      </div></template
    >
  </el-dialog>
</template>

<script setup lang="ts">
import { computed,onBeforeUnmount,reactive,ref } from "vue";
import { ElMessage } from "element-plus";
import { Connection, Delete, Headset, VideoPause, VideoPlay } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import api from '@/api/index';

type DataType = "coil" | "holdingRegister";
type Signal = {
  slaveAddress: number;
  dataType: DataType;
  address: number;
  triggerValue: boolean | number;
  instantaneous: boolean;
};
type Feedback = { modbus: { enabled: boolean; signals: Signal[] };audio:{enabled:boolean;audioId:string;volume:number} };
const props = defineProps<{ visible: boolean; modelValue: any;audioResources:Array<{id:string;name:string;originalName?:string;fileAvailable?:boolean}> }>();
const emit = defineEmits<{
  (event: "update:visible", value: boolean): void;
  (event: "save", value: Feedback): void;
}>();
const { t } = useI18n();
const MAX_SIGNALS = 3;
const availableAudioResources = computed(() => (props.audioResources || []).filter(audio => audio?.id && audio?.name && audio?.fileAvailable !== false));const availableAudioIds = computed(() => new Set(availableAudioResources.value.map(audio => audio.id)));
const createSignal = (): Signal => ({
  slaveAddress: 1,
  dataType: "coil",
  address: 0,
  triggerValue: true,
  instantaneous: false,
});
const normalizeSignal = (signal: any): Signal => {
  const dataType: DataType =
    signal?.dataType === "holdingRegister" ? "holdingRegister" : "coil";
  return {
    slaveAddress: Number.isInteger(signal?.slaveAddress)
      ? signal.slaveAddress
      : 1,
    dataType,
    address: Number.isInteger(signal?.address) ? signal.address : 0,
    triggerValue:
      dataType === "coil"
        ? Boolean(signal?.triggerValue ?? true)
        : Number.isInteger(signal?.triggerValue)
        ? signal.triggerValue
        : 0,
    instantaneous: dataType === "coil" && signal?.instantaneous === true,
  };
};
const normalize = (value: any): Feedback => ({
  modbus: {
    enabled: value?.modbus?.enabled === true,
    signals: Array.isArray(value?.modbus?.signals)
      ? value.modbus.signals.slice(0, MAX_SIGNALS).map(normalizeSignal)
      : [],
  },
  audio:{enabled:value?.audio?.enabled === true,audioId:typeof value?.audio?.audioId === 'string' ? value.audio.audioId : '',volume:Number.isInteger(value?.audio?.volume) ? Math.min(100,Math.max(0,value.audio.volume)) : 80},
});
const draft = reactive<Feedback>(normalize(null));
const resetDraft = () => Object.assign(draft, normalize(props.modelValue));
const previewing = ref(false);let previewAudio:HTMLAudioElement|null = null;let previewUrl = '';const stopPreview = () => {if (previewAudio) {previewAudio.pause();previewAudio.src = ''}previewAudio = null;previewing.value = false;if (previewUrl) URL.revokeObjectURL(previewUrl);previewUrl = ''};const togglePreview = async () => {if (previewing.value) return stopPreview();if (!draft.audio.audioId) return;try {const response = await api.getAudioResourceFile(draft.audio.audioId);previewUrl = URL.createObjectURL(response.data);previewAudio = new Audio(previewUrl);previewAudio.volume = draft.audio.volume / 100;previewAudio.onended = stopPreview;previewAudio.onerror = () => {stopPreview();ElMessage.error(t('config.audio_resources.preview_failed'))};previewing.value = true;await previewAudio.play()} catch (error:any) {stopPreview();ElMessage.error(error?.response?.data?.detail || error?.message || t('config.audio_resources.preview_failed'))}};onBeforeUnmount(stopPreview);
const addSignal = () =>
  draft.modbus.signals.length < MAX_SIGNALS
    ? draft.modbus.signals.push(createSignal())
    : ElMessage.warning(t("config.sop_step_config.max_step_feedback_signals"));
const changeDataType = (signal: Signal) => {
  signal.triggerValue = signal.dataType === "coil" ? true : 0;
  signal.instantaneous = false;
};
const validSignal = (signal: Signal) =>
  Number.isInteger(signal.slaveAddress) &&
  signal.slaveAddress >= 1 &&
  signal.slaveAddress <= 247 &&
  Number.isInteger(signal.address) &&
  signal.address >= 0 &&
  signal.address <= 65535 &&
  typeof signal.instantaneous === "boolean" &&
  (signal.dataType === "coil"
    ? typeof signal.triggerValue === "boolean"
    : !signal.instantaneous &&
      signal.dataType === "holdingRegister" &&
      Number.isInteger(signal.triggerValue) &&
      Number(signal.triggerValue) >= 0 &&
      Number(signal.triggerValue) <= 65535);
const save = () => {
  const value = normalize(draft);
  if (value.modbus.enabled && !value.modbus.signals.length)
    return ElMessage.error(
      t("config.sop_step_config.sop_completion_signal_required")
    );
  if (value.modbus.signals.some((signal) => !validSignal(signal)))
    return ElMessage.error(
      t("config.sop_step_config.invalid_step_modbus_signal")
    );
  if (value.audio.enabled && (!value.audio.audioId || !availableAudioIds.value.has(value.audio.audioId))) return ElMessage.error(t('config.sop_step_config.sop_completion_audio_required'));
  stopPreview();
  emit("save", value);
  emit("update:visible", false);
};
</script>

<style scoped lang="scss">

.channel-title small {
  font-size: 12px;
}
.feedback-channel {
  overflow: hidden;
  transition: 0.2s;
  // background-color:var(--bs-bgcolor);
  margin-top:10px;
  border: #000 1px solid;
}
.feedback-channel.enabled {

  box-shadow: 0 4px 16px rgba(0, 123, 192, 0.08);
}
.feedback-channel > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  background: var(--bs-bgcolor);
}
.channel-title,
.channel-status {
  display: flex;
  align-items: center;
  gap: 12px;
}
.channel-title > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.channel-icon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  color: #fff;
  background: var(--bs-primary-color);
  font-size: 19px;
}
.channel-content {
  padding: 16px 18px 6px;
}
.audio-channel-content :deep(.el-select){width:100%}.audio-option-file{float:right;margin-left:12px;color:var(--el-text-color-secondary)}.preview-cell{display:flex;align-items:center;padding-top:26px}.preview-cell .el-button{width:100%}
.signal-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.signal-toolbar > div {
  display: flex;
  align-items: center;
  gap: 12px;
}
.signal-toolbar span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.signal-card {
  padding: 12px 12px 0;
  margin-bottom: 10px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}

.signal-card :deep(.el-input-number),
.signal-card :deep(.el-select) {
  width: 100%;
}
.coil-only {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.delete-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  // padding-top: 20px;
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
