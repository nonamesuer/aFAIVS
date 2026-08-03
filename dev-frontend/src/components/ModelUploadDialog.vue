<template>
  <el-dialog
    :model-value="visible"
    :title="$t('config.model_upload.title')"
    width="560px"
    destroy-on-close
    modal-class="bs-shade"
    @close="closeDialog"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      :title="$t('config.model_upload.description')"
    />

    <el-upload
      ref="uploadRef"
      class="model-upload"
      drag
      accept=".zip,application/zip"
      :auto-upload="false"
      :limit="1"
      :file-list="fileList"
      :on-change="handleFileChange"
      :on-remove="handleFileRemove"
      :on-exceed="handleExceed"
    >
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">
        {{ $t("config.model_upload.drop_hint") }}
        <em>{{ $t("config.model_upload.choose_file") }}</em>
      </div>
      <template #tip>
        <div class="el-upload__tip">
          {{ $t("config.model_upload.file_tip") }}
        </div>
      </template>
    </el-upload>

    <div v-if="selectedFile" class="package-summary">
      <div>
        <span>{{ $t("config.model_upload.filename") }}</span>
        <strong>{{ selectedFile.name }}</strong>
      </div>
      <div>
        <span>{{ $t("config.model_upload.model_name") }}</span>
        <strong>{{ inferredModelName || $t("config.model_upload.pending_validation") }}</strong>
      </div>
    </div>

    <template #footer>
      <el-button @click="closeDialog">{{ $t("button.cancel") }}</el-button>
      <el-button
        type="primary"
        :loading="uploading"
        :disabled="!selectedFile"
        @click="submitUpload"
      >
        {{ $t("config.model_upload.upload") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  ElMessage,
  ElMessageBox,
  genFileId,
  type UploadFile,
  type UploadFiles,
  type UploadInstance,
  type UploadProps,
  type UploadRawFile,
  type UploadUserFile,
} from "element-plus";
import { UploadFilled } from "@element-plus/icons-vue";
import api from "@/api/index";

const props = defineProps<{
  visible: boolean;
}>();

const emit = defineEmits<{
  (event: "update:visible", value: boolean): void;
  (event: "uploaded", modelName: string): void;
}>();

const { t } = useI18n();
const uploadRef = ref<UploadInstance>();
const fileList = ref<UploadUserFile[]>([]);
const selectedFile = ref<File | null>(null);
const uploading = ref(false);

const inferredModelName = computed(() => {
  if (!selectedFile.value) return "";
  const match = selectedFile.value.name.match(
    /^eFAIVSModel[^_]+_([\w.-]+)_\d{14}\.zip$/i,
  );
  return match?.[1] || "";
});

watch(
  () => props.visible,
  (value) => {
    if (!value) resetSelection();
  },
);

const resetSelection = () => {
  selectedFile.value = null;
  fileList.value = [];
  uploadRef.value?.clearFiles();
};

const closeDialog = () => {
  if (uploading.value) return;
  resetSelection();
  emit("update:visible", false);
};

const validateFile = (file: File) => {
  if (!file.name.toLowerCase().endsWith(".zip")) {
    ElMessage.error(t("config.model_upload.invalid_type"));
    return false;
  }
  if (file.size <= 0) {
    ElMessage.error(t("config.model_upload.empty_file"));
    return false;
  }
  if (file.size > 1024 * 1024 * 1024) {
    ElMessage.error(t("config.model_upload.too_large"));
    return false;
  }
  if (!inferredNameFromFilename(file.name)) {
    ElMessage.error(t("config.model_upload.invalid_filename"));
    return false;
  }
  return true;
};

const inferredNameFromFilename = (filename: string) => {
  return /^eFAIVSModel[^_]+_([\w.-]+)_\d{14}\.zip$/i.exec(filename)?.[1] || "";
};

const handleFileChange = (
  uploadFile: UploadFile,
  uploadFiles: UploadFiles,
) => {
  const rawFile = uploadFile.raw;
  if (!rawFile || !validateFile(rawFile)) {
    selectedFile.value = null;
    fileList.value = [];
    return;
  }
  selectedFile.value = rawFile;
  fileList.value = uploadFiles.slice(-1);
};

const handleFileRemove = () => {
  selectedFile.value = null;
  fileList.value = [];
};

const handleExceed: UploadProps["onExceed"] = (files) => {
  const file = files[0] as UploadRawFile;
  file.uid = genFileId();
  if (!validateFile(file)) return;
  uploadRef.value?.clearFiles();
  uploadRef.value?.handleStart(file);
};

const uploadFile = async (overwrite: boolean) => {
  if (!selectedFile.value) return null;
  const formData = new FormData();
  formData.append("file", selectedFile.value, selectedFile.value.name);
  return api.uploadModelArchive(formData, overwrite);
};

const submitUpload = async () => {
  if (!selectedFile.value || uploading.value) return;
  uploading.value = true;
  try {
    let response = await uploadFile(false);
    if (
      !response?.data?.status &&
      response?.data?.code === "MODEL_ALREADY_EXISTS"
    ) {
      const modelName =
        response.data?.data?.modelName || inferredModelName.value;
      await ElMessageBox.confirm(
        t("config.model_upload.overwrite_confirm", { name: modelName }),
        t("config.model_upload.overwrite_title"),
        {
          type: "warning",
          confirmButtonText: t("button.confirm"),
          cancelButtonText: t("button.cancel"),
          modalClass: "bs-shade",
        },
      );
      response = await uploadFile(true);
    }
    if (!response?.data?.status) {
      throw new Error(
        response?.data?.msg || t("config.model_upload.failed"),
      );
    }
    const modelName =
      response.data?.data?.modelName || inferredModelName.value;
    ElMessage.success(
      t("config.model_upload.success", { name: modelName }),
    );
    emit("uploaded", modelName);
    closeDialog();
  } catch (error: any) {
    if (error === "cancel" || error === "close") return;
    ElMessage.error(
      error?.response?.data?.msg ||
        error?.message ||
        t("config.model_upload.failed"),
    );
  } finally {
    uploading.value = false;
  }
};
</script>

<style scoped lang="scss">
.model-upload {
  margin-top: 18px;
}

.package-summary {
  margin-top: 18px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);

  div {
    display: grid;
    grid-template-columns: 110px minmax(0, 1fr);
    gap: 12px;
    line-height: 28px;
  }

  strong {
    overflow-wrap: anywhere;
  }
}
</style>
