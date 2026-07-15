<template>
    <el-drawer modal-class="bs-shade" :model-value="visible" :title="$t('button.title.box_style_setting')" @closed="$emit('update:visible', false)" @update:model-value="$emit('update:visible', $event)">
        <el-form label-position="top" size="large" ref="boxStyleFormRef" :model="baseicConfig" :inline="true">
            <el-form-item :label="$t('config.box_thickness')" prop="boxThickness">
                <el-input-number v-model="baseicConfig.boxThickness" :min="1" :max="10" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="$t('config.font_thickness')" prop="fontThickness">
                <el-input-number v-model="baseicConfig.fontThickness" :min="1" :max="10" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="$t('config.font_scale')" prop="fontScale">
                <el-input-number v-model="baseicConfig.fontScale" :min="0.1" :max="2" :step="0.1" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="$t('config.show_result_left_top')" prop="showResultText">
                <el-switch v-model="baseicConfig.showResultText" />
            </el-form-item> 
        </el-form>
        <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; margin-top: 10px">
            <Loading v-show="loading" />
            <div style="font-weight: 700; color: green; margin: 10px 0;">↓↓↓{{ $t('config.click_show_example') }}↓↓↓</div>
            <img id="boxStyleExample" @click="displayBoxStyleExample" src="@/assets/img/FAIVS.jpg" alt="Box Style Example" width="50%" height="50%" />
        </div>
        <template #footer>
            <div class="drawer-footer">
                <el-button plain type="primary" @click="handleCancel">{{ $t('button.cancel') }}</el-button>
                <el-button type="primary"  @click="handleSave">{{ $t('button.save') }}</el-button>
            </div>
        </template>
    </el-drawer>
</template>
<script setup lang="ts">
import { ref, reactive, watch } from "vue";
import { useI18n } from "vue-i18n";
import api from "@/api/index";
import { ElMessage } from "element-plus";
import { MesAlertWTitle } from "@/assets/js/secondpk";
import Loading from "@/views/Loading.vue";
const { t } = useI18n();
const loading = ref(false);
const props = defineProps<{
  visible: boolean;
  modelCameraForm: any; // 对象引用，直接修改
}>();
const emit = defineEmits<{
  (e: "update:visible", val: boolean): void;
}>();
const boxStyleFormRef = ref(null);

const defaultBoxStyleForm = {
    boxThickness: 2,
    fontThickness: 2,
    fontScale: 0.5,  
    showResultText: false,
};

const getCurrentBoxStyleConfig = () => ({
    ...defaultBoxStyleForm,
    ...(props.modelCameraForm?.boxStyleConfig || {}),
});

const baseicConfig = reactive(getCurrentBoxStyleConfig());

const resetForm = () => {
    Object.assign(baseicConfig, getCurrentBoxStyleConfig());
};

watch(() => props.visible, (visible) => {
    if (visible) {
        resetForm();
    }
}, {
    immediate: true,
});

const handleSave = ()=>{
    props.modelCameraForm.boxStyleConfig = { ...baseicConfig };
    emit("update:visible", false);
};
const handleCancel = ()=>{
    resetForm();
    emit("update:visible", false);
};
const displayBoxStyleExample = ()=>{
    loading.value = true;
    api.displayBoxStyleConfig(baseicConfig).then((res)=>{
        const resData = res.data;
        if(!resData.status)if (!resData.status) return MesAlertWTitle("error", t("message.error"), '', resData.msg, "OK");
        const imgElement = document.getElementById("boxStyleExample") as HTMLImageElement;
        imgElement.src = resData.frame;
    }).catch((err)=>{
        MesAlertWTitle("error", t("message.error"), '', err.message || t("message.messagetext.failedgetboxstyleexample"), "OK");
    }).finally(()=>{
        loading.value = false;
    });
}
</script>
<style scoped>
.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>