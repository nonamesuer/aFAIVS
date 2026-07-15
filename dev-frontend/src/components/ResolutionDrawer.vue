<template>
  <el-drawer
    modal-class="bs-shade"
    :model-value="visible"
    :title="$t('camera.settingstitle')"
    @closed="handleClosed"
    @update:model-value="$emit('update:visible', $event)"
  >
    <el-form label-position="top" size="large" ref="resolutionFormRef" :model="localResolutionForm" :rules="resolutionRules">
      <el-form-item :label="$t('camera.resolution')">
        <el-select v-model="localResolutionForm.resolutions" placeholder="Select" style="width: 100%">
          <el-option
            v-for="(item, index) in resolutionsList"
            :key="index"
            :label="`${item[0]}*${item[1]}`"
            :value="`${item[0]}*${item[1]}`"
          >
            <span style="float: left">{{ `${item[0]}*${item[1]}` }}</span>
            <span
              style="float: right; display: flex; align-items: center; height: 100%; z-index: 2"
              @click.stop="$emit('deleteResolution', `${item[0]}*${item[1]}`)"
            >
              <el-icon style="vertical-align: middle" color="red" size="18px">
                <Delete />
              </el-icon>
            </span>
          </el-option>
          <template #footer>
            <el-button v-if="!isAdding" text size="small" :title="$t('button.title.customize')" @click="isAdding = true">
              {{ $t('button.customize') }}
            </el-button>
            <template v-else>
              <el-form size="small" label-position="top" :model="addResolutionForm" ref="addResolutionFormRef" :rules="addResolutionRules">
                <el-row :gutter="10" align="middle">
                  <el-col :span="9">
                    <el-form-item prop="width" :label="$t('camera.resolution') + '(' + $t('camera.width') + ')'">
                      <el-input-number v-model="addResolutionForm.width" :min="0" :step="32" size="small" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="2">
                    <div style="text-align: center">x</div>
                  </el-col>
                  <el-col :span="9">
                    <el-form-item prop="height" :label="$t('camera.resolution') + '(' + $t('camera.height') + ')'">
                      <el-input-number v-model="addResolutionForm.height" :min="0" :step="32" size="small" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                </el-row>
              </el-form>
              <el-button type="primary" size="small" @click="handleAddResolution">{{ $t('button.add') }}</el-button>
              <el-button type="primary" size="small" plain @click="cancelAddResolution">{{ $t('button.cancel') }}</el-button>
            </template>
          </template>
        </el-select>
      </el-form-item>
      <el-divider />
      <el-form-item prop="area" :label="$t('camera.area') + '(' + $t('camera.areades') + ')'">
        <el-input-number v-model="localResolutionForm.area" :min="0" :step="32" style="width: 100%" />
      </el-form-item>
      <el-alert type="info" show-icon :closable="false">
        <p>{{ $t('camera.msg.areatip') }}</p>
      </el-alert>
      <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; margin-top: 10px">
        <div style="font-weight: 700; color: red">↓↓↓{{ $t('camera.areaexapmle') }}↓↓↓</div>
        <img src="@/assets/img/area.jpg" alt="" width="50%" height="50%" />
      </div>
      <el-divider />
      <el-form-item :label="$t('camera.displayclarity') + '(' + $t('camera.displayclaritydes') + ')'">
        <el-slider v-model="localResolutionForm.clarity" :max="100" :min="1" show-input />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="drawer-footer">
        <el-button plain type="primary" @click="handleCancel">{{ $t('button.cancel') }}</el-button>
        <el-button type="primary" @click="handleSubmit">{{ $t('button.confirm') }}</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, FormInstance, FormRules } from "element-plus";
import { Delete } from "@element-plus/icons-vue";

const { t } = useI18n();

const props = defineProps<{
  visible: boolean;
  resolutionForm: { resolutions: string; area: number; clarity: number };
  resolutionsList: number[][];
  defaultResolution: { width: number; height: number; area: number; clarity: number };
}>();

const emit = defineEmits<{
  (e: "update:visible", val: boolean): void;
  (e: "submitResolution", data: { resolutions: string; area: number; clarity: number }): void;
  (e: "addResolution", data: { width: number; height: number }): void;
  (e: "deleteResolution", resolutionStr: string): void;
}>();

// 内部拷贝分辨率表单，避免直接修改 prop
const localResolutionForm = reactive({
  resolutions: props.resolutionForm.resolutions,
  area: props.resolutionForm.area,
  clarity: props.resolutionForm.clarity,
});

const resetResolutionForm = () => {
  localResolutionForm.resolutions = props.resolutionForm.resolutions;
  localResolutionForm.area = props.resolutionForm.area;
  localResolutionForm.clarity = props.resolutionForm.clarity;
};

watch(
  () => props.resolutionForm,
  () => resetResolutionForm(),
  { deep: true }
);

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      resetResolutionForm();
      cancelAddResolution();
    }
  },
  { immediate: true }
);

const isAdding = ref(false);
const addResolutionForm = reactive({ width: 0, height: 0 });
const addResolutionFormRef = ref<FormInstance>();
const resolutionFormRef = ref<FormInstance>();

const areaMax = computed(() => {
  if (!localResolutionForm.resolutions) return 0;
  return Math.max(...localResolutionForm.resolutions.split("*").map(Number));
});

// 验证规则
const validateWidth = (rule: any, value: any, callback: any) => {
  if (value === "") {
    callback(new Error(t("interacting.pls") + t("interacting.enter") + t("camera.width")));
  } else if (value < 320) {
    callback(new Error(t("camera.msg.validwidth")));
  } else if (value % 2 !== 0) {
    callback(new Error(t("camera.msg.validresolution")));
  } else if (value / addResolutionForm.height < 0.5 || value / addResolutionForm.height > 2.5) {
    callback(new Error(t("camera.msg.validresolution1")));
  } else {
    callback();
  }
};
const validateHeight = (rule: any, value: any, callback: any) => {
  if (value === "") {
    callback(new Error(t("interacting.pls") + t("interacting.enter") + t("camera.height")));
  } else if (value < 240) {
    callback(new Error(t("camera.msg.validheight")));
  } else if (value % 2 !== 0) {
    callback(new Error(t("camera.msg.validresolution")));
  } else if (addResolutionForm.width / value < 0.5 || addResolutionForm.width / value > 2.5) {
    callback(new Error(t("camera.msg.validresolution1")));
  } else {
    callback();
  }
};
const validateArea = (rule: any, value: any, callback: any) => {
  if (value === "") {
    callback(new Error(t("interacting.pls") + t("interacting.enter") + t("camera.area")));
  } else if (localResolutionForm.area < 0 || (0 < value && value < 240)) {
    callback(new Error(t("camera.msg.validarea")));
  } else if (value > areaMax.value) {
    callback(new Error(t("camera.msg.validarea2") + areaMax.value));
  } else if (value % 2 !== 0) {
    callback(new Error(t("camera.msg.validarea1")));
  } else {
    callback();
  }
};

const resolutionRules = reactive<FormRules>({
  resolutions: [{ required: true, message: t("interacting.pls") + t("interacting.select") + t("camera.resolution"), trigger: "blur" }],
  area: [{ required: true, validator: validateArea, trigger: "blur" }],
});
const addResolutionRules = reactive<FormRules>({
  width: [{ required: true, validator: validateWidth, trigger: "blur" }],
  height: [{ required: true, validator: validateHeight, trigger: "blur" }],
});

const handleAddResolution = async () => {
  if (!addResolutionFormRef.value) return;
  const valid = await addResolutionFormRef.value.validate().then(() => true).catch(() => false);
  if (!valid) {
    ElMessage({ message: t("message.messagetext.field_lack_tip"), type: "error" });
    return;
  }
  const newResolution = { width: addResolutionForm.width, height: addResolutionForm.height };
  const exists = props.resolutionsList.some(
    (item) => item[0] === newResolution.width && item[1] === newResolution.height
  );
  if (exists) {
    ElMessage({ message: t("message.messagetext.resolutionexists"), type: "warning" });
    return;
  }
  emit("addResolution", newResolution);
  cancelAddResolution();
};

const cancelAddResolution = () => {
  isAdding.value = false;
  addResolutionForm.width = 0;
  addResolutionForm.height = 0;
};

const handleCancel = () => {
  resetResolutionForm();
  cancelAddResolution();
  emit("update:visible", false);
};

const handleClosed = () => {
  resetResolutionForm();
  cancelAddResolution();
  emit("update:visible", false);
};

const handleSubmit = async () => {
  if (!resolutionFormRef.value) return;
  const valid = await resolutionFormRef.value.validate().then(() => true).catch(() => false);
  if (!valid) {
    ElMessage({ message: t("message.messagetext.field_lack_tip"), type: "error" });
    return;
  }
  emit("submitResolution", {
    resolutions: localResolutionForm.resolutions,
    area: localResolutionForm.area,
    clarity: localResolutionForm.clarity,
  });
};
</script>

<style scoped>
.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>