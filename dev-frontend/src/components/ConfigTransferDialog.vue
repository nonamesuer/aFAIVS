<template>
  <el-dialog :model-value="visible" :title="$t('config.config_transfer.title')" width="680px" destroy-on-close modal-class="bs-shade" @close="emit('update:visible', false)">
    <el-alert type="warning" :closable="false" show-icon :title="$t('config.config_transfer.description')"/>
    <div class="config-file-grid">
      <div v-for="item in configFiles" :key="item.type" class="config-file-card" >
        <el-icon class="config-file-card__icon"><Document /></el-icon>
        <div class="config-file-card__body">
          <div class="config-file-card__title">{{ item.title }}</div>
          <div class="config-file-card__description">
            {{ item.description }}
          </div>
          <div class="config-file-card__actions">
            <el-button :icon="Download" type="primary" link  @click="downloadFile(item.type)">
              {{ $t("button.download") }}
            </el-button>
            <el-button type="danger" link :icon="Upload" @click="openFilePicker(item.type)">
              {{ $t("config.config_transfer.import") }}
            </el-button>
          </div>
        </div>
      </div>
    </div>
    <input ref="mainInput" hidden type="file" accept=".enc,.json,application/json"  @change="(event) => handleSelectedFile('main', event)"/>
    <input ref="sopInput" hidden type="file" accept=".enc,.json,application/json" @change="(event) => handleSelectedFile('sop', event)"/>
    <template #footer>
      <el-button @click="emit('update:visible', false)" plain>{{ $t("button.close") }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { Document, Download, Upload } from "@element-plus/icons-vue";
import { MesAlertWTitle, MesConfirmWTitle } from "@/assets/js/secondpk";
import { useAppStore } from "@/stores/store";
import api from "@/api/index";
const appStore = useAppStore();
type ConfigType = "main" | "sop";
defineProps<{visible: boolean}>();
const emit = defineEmits<{
  (event: "update:visible", value: boolean): void;
  (event: "imported", configType: ConfigType): void;
}>();

const { t } = useI18n();
const mainInput = ref<HTMLInputElement>();
const sopInput = ref<HTMLInputElement>();

const configFiles = computed(() => [
  {
    type: "main" as const,
    title: t("config.config_transfer.main_title"),
    description: t("config.config_transfer.main_description"),
  },
  {
    type: "sop" as const,
    title: t("config.config_transfer.sop_title"),
    description: t("config.config_transfer.sop_description"),
  },
]);

const inputFor = (configType: ConfigType) => {
  return configType === "main" ? mainInput.value : sopInput.value;
};

const openFilePicker = (configType: ConfigType) => {
  const input = inputFor(configType);
  if (!input) return;
  input.value = "";
  input.click();
};

const downloadFile = async (configType: ConfigType) => {
  try {
    appStore.setLoading(true);
    const response = await api.downloadConfigFile(configType);
    const blob = new Blob([response.data], {
      type: "application/octet-stream",
    });
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download =
      configType === "main" ? "config.enc" : "sop_config.enc";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  } catch (error: any) {
    MesAlertWTitle("error", t('displaytext.failed'), t("config.config_transfer.download_failed"), error?.response?.data?.msg || error?.message || t("config.config_transfer.download_failed"), t("button.ok"));
  } finally {
    appStore.setLoading(false);
  }
};

const handleSelectedFile = async (configType: ConfigType,event: Event,) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  try {
    const suffix = file.name.toLowerCase();
    if (!suffix.endsWith(".enc") && !suffix.endsWith(".json")) {
      ElMessage.error(t("config.config_transfer.invalid_type"));
      return;
    }
    if (file.size <= 0 || file.size > 10 * 1024 * 1024) {
      ElMessage.error(t("config.config_transfer.invalid_size"));
      return;
    }
    const title = configType === "main" ? t("config.config_transfer.main_title") : t("config.config_transfer.sop_title");
    await MesConfirmWTitle("warning",t('config.config_transfer.import'),t("config.config_transfer.import_confirm_title"),t("config.config_transfer.import_confirm",{name:title}),t('config.config_transfer.import'),t('button.cancel'));
    appStore.setLoading(true);
    const formData = new FormData();
    formData.append("file", file, file.name);
    const response = await api.uploadConfigFile(configType, formData);
    if (!response.data?.status) {
      throw new Error(
        response.data?.msg || t("config.config_transfer.import_failed"),
      );
    }
    ElMessage.success(t("config.config_transfer.import_success"));
    emit("imported", configType);
  } catch (error: any) {
    if (error === "cancel" || error === "close") return;
    MesAlertWTitle("error", t('displaytext.failed'), t("config.config_transfer.import_failed"), error?.response?.data?.msg || error?.message || t("config.config_transfer.import_failed"), t("button.ok"));
  } finally {
    appStore.setLoading(false);
    input.value = "";
  }
};
</script>

<style scoped lang="scss">
.config-file-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 20px;
}

.config-file-card {
  display: flex;
  gap: 14px;
  min-height: 150px;
  padding: 18px;
  color:#000;
  background: var(--bs-bgcolor);

  &__icon {
    flex: 0 0 auto;
    padding-top: 2px;
    color: var(--el-color-primary);
    font-size: 32px;
  }

  &__body {
    display: flex;
    flex: 1;
    min-width: 0;
    flex-direction: column;
  }

  &__title {
    font-size: 16px;
    font-weight: 700;
  }

  &__description {
    flex: 1;
    margin-top: 8px;
    line-height: 1.5;
  }

  &__actions {
    display: flex;
    margin-top: 16px;
  }
}

@media (max-width: 720px) {
  .config-file-grid {
    grid-template-columns: 1fr;
  }
}
</style>
