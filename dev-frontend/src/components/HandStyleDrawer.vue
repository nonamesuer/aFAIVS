<template>
  <el-drawer
    modal-class="bs-shade"
    :model-value="visible"
    :title="$t('config.hand_style_config')"
    size="720px"
    @closed="handleClosed"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-tabs v-model="activeSide">
      <div style="margin-top: 10px;"></div>
      <el-tab-pane
        v-for="side in handSides"
        :key="side.key"
        :label="$t(side.label)"
        :name="side.key"
      >
        <el-form
          label-position="top"
          size="large"
          :model="handStyleForm[side.key]"
          class="hand-style-form"
        >
          <el-form-item :label="$t('config.hand_keypoint_size')">
            <el-input-number
              v-model="handStyleForm[side.key].keypointSize"
              :min="1"
              :max="20"
              :step="1"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item :label="$t('config.hand_keypoint_color')">
            <el-color-picker
              v-model="handStyleForm[side.key].keypointColor"
              color-format="hex"
            />
          </el-form-item>
          <el-form-item :label="$t('config.hand_connection_width')">
            <el-input-number
              v-model="handStyleForm[side.key].connectionWidth"
              :min="1"
              :max="10"
              :step="1"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item :label="$t('config.hand_connection_color')">
            <el-color-picker
              v-model="handStyleForm[side.key].connectionColor"
              color-format="hex"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <section class="preview-section">
      <div class="preview-header">
        <div>
          <div class="preview-title">{{ $t("config.hand_style_preview") }}</div>
          <div class="preview-description">
            {{ $t("config.hand_style_preview_description") }}
          </div>
        </div>
        <el-button :loading="previewLoading" @click="requestPreview">
          {{ $t("config.refresh_preview") }}
        </el-button>
      </div>

      <div class="preview-frame" v-loading="previewLoading">
        <img
          v-if="previewFrame"
          :src="previewFrame"
          :alt="$t('config.hand_style_preview')"
        />
        <el-empty v-else :description="$t('config.preview_not_available')" />
      </div>
      <el-alert
        v-if="previewError"
        :title="previewError"
        type="error"
        :closable="false"
        show-icon
      />
    </section>

    <template #footer>
      <div class="drawer-footer">
        <el-button plain type="primary" @click="handleCancel">
          {{ $t("button.cancel") }}
        </el-button>
        <el-button type="primary" @click="handleSave">
          {{ $t("button.save") }}
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import api from "@/api/index";
import { MesAlertWTitle } from "@/assets/js/secondpk";
import { useAppStore } from "@/stores/store";

interface HandSideStyle {
  keypointSize: number;
  keypointColor: string;
  connectionWidth: number;
  connectionColor: string;
}

interface HandStyleConfig {
  left: HandSideStyle;
  right: HandSideStyle;
}

type HandSide = keyof HandStyleConfig;

const DEFAULT_HAND_STYLE: HandStyleConfig = {
  left: {
    keypointSize: 4,
    keypointColor: "#FF0000",
    connectionWidth: 2,
    connectionColor: "#FF0000",
  },
  right: {
    keypointSize: 4,
    keypointColor: "#00FF00",
    connectionWidth: 2,
    connectionColor: "#00FF00",
  },
};

const props = defineProps<{
  visible: boolean;
  handStyleConfig: HandStyleConfig;
}>();

const emit = defineEmits<{
  (event: "update:visible", value: boolean): void;
  (event: "update:handStyleConfig", value: HandStyleConfig): void;
}>();

const { t } = useI18n();
const appStore = useAppStore();
const activeSide = ref<HandSide>("left");
const previewFrame = ref("");
const previewLoading = ref(false);
const previewError = ref("");
const handSides: Array<{ key: HandSide; label: string }> = [
  { key: "left", label: "config.left_hand" },
  { key: "right", label: "config.right_hand" },
];

const clampInteger = (
  value: unknown,
  fallback: number,
  minimum: number,
  maximum: number,
): number => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.round(parsed)));
};

const normalizeColor = (value: unknown, fallback: string): string => {
  const color = String(value || "").trim();
  return /^#[0-9a-fA-F]{6}$/.test(color) ? color.toUpperCase() : fallback;
};

const normalizeSide = (
  value: Partial<HandSideStyle> | undefined,
  fallback: HandSideStyle,
): HandSideStyle => ({
  keypointSize: clampInteger(value?.keypointSize, fallback.keypointSize, 1, 20),
  keypointColor: normalizeColor(value?.keypointColor, fallback.keypointColor),
  connectionWidth: clampInteger(
    value?.connectionWidth,
    fallback.connectionWidth,
    1,
    10,
  ),
  connectionColor: normalizeColor(
    value?.connectionColor,
    fallback.connectionColor,
  ),
});

const createHandStyleForm = (
  config?: Partial<HandStyleConfig>,
): HandStyleConfig => ({
  left: normalizeSide(config?.left, DEFAULT_HAND_STYLE.left),
  right: normalizeSide(config?.right, DEFAULT_HAND_STYLE.right),
});

const handStyleForm = ref<HandStyleConfig>(
  createHandStyleForm(props.handStyleConfig),
);

let previewTimer: ReturnType<typeof setTimeout> | null = null;
let previewRequestId = 0;

const requestPreview = async () => {
  const requestId = ++previewRequestId;
  previewLoading.value = true;
  previewError.value = "";
  try {
    const payload = createHandStyleForm(handStyleForm.value);
    const { data: response } = await api.displayHandStyleConfig({
      handStyle: payload,
    });
    if (requestId !== previewRequestId) return;
    if (!response.status) {
      previewError.value = response.msg || t("config.preview_not_available");
      return;
    }
    previewFrame.value = response.frame;
  } catch (error: any) {
    if (requestId !== previewRequestId) return;
    previewError.value =
      error.message || t("config.preview_not_available");
  } finally {
    if (requestId === previewRequestId) {
      previewLoading.value = false;
    }
  }
};

const schedulePreview = () => {
  if (!props.visible) return;
  if (previewTimer) window.clearTimeout(previewTimer);
  previewTimer = window.setTimeout(requestPreview, 180);
};

watch(
  () => [props.visible, props.handStyleConfig] as const,
  ([visible]) => {
    if (!visible) return;
    handStyleForm.value = createHandStyleForm(props.handStyleConfig);
    activeSide.value = "left";
    previewFrame.value = "";
    previewError.value = "";
    schedulePreview();
  },
  { immediate: true, deep: true },
);

watch(handStyleForm, schedulePreview, { deep: true });

const handleSave = async () => {
  const payload = createHandStyleForm(handStyleForm.value);
  appStore.setLoading(true);
  try {
    const { data: response } = await api.setHandStyleConfig({
      handStyle: payload,
    });
    if (!response.status) {
      MesAlertWTitle("error", t("message.error"), "", response.msg, "OK");
      return;
    }
    emit("update:handStyleConfig", payload);
    emit("update:visible", false);
    ElMessage.success(t("message.messagetext.successsave"));
  } catch (error: any) {
    MesAlertWTitle(
      "error",
      t("message.error"),
      "",
      error.message || t("message.messagetext.failedsave"),
      "OK",
    );
  } finally {
    appStore.setLoading(false);
  }
};

const handleCancel = () => {
  emit("update:visible", false);
};

const handleClosed = () => {
  if (previewTimer) {
    window.clearTimeout(previewTimer);
    previewTimer = null;
  }
  previewRequestId += 1;
  previewLoading.value = false;
  emit("update:visible", false);
};
</script>

<style scoped>
.hand-style-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
}

.preview-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 22px;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.preview-title {
  font-size: 16px;
  font-weight: 700;
}

.preview-description {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.preview-frame {
  min-height: 330px;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  background: #20242a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-frame img {
  display: block;
  width: 100%;
  height: auto;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
