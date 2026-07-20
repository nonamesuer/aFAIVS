<template>
    <el-drawer modal-class="bs-shade" :model-value="visible" :title="$t('button.title.box_style_setting')" @closed="$emit('update:visible', false)" @update:model-value="$emit('update:visible', $event)">
        <el-form label-position="top" size="large" ref="boxStyleFormRef" :model="boxStyleForm" :inline="true">
            <el-form-item :label="$t('config.box_thickness')" prop="boxThickness">
                <el-input-number v-model="boxStyleForm.boxThickness" :min="1" :max="10" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="$t('config.font_thickness')" prop="fontThickness">
                <el-input-number v-model="boxStyleForm.fontThickness" :min="1" :max="10" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="$t('config.font_scale')" prop="fontScale">
                <el-input-number v-model="boxStyleForm.fontScale" :min="0.1" :max="2" :step="0.1" style="width: 100%" />
            </el-form-item>
            <el-form-item :label="$t('config.fromarea_fill')" prop="fromAreaFill">
                <el-switch v-model="boxStyleForm.fromAreaFill" />
            </el-form-item> 
            <el-form-item :label="$t('config.targetarea_fill')" prop="targetAreaFill">
                <el-switch v-model="boxStyleForm.targetAreaFill" />
            </el-form-item> 
        </el-form>
        <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; margin-top: 10px">
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
import { ref, reactive, watch,onMounted } from "vue";
import { useI18n } from "vue-i18n";
import api from "@/api/index";
import { ElMessage } from "element-plus";
import { MesAlertWTitle } from "@/assets/js/secondpk";
import { useAppStore } from "@/stores/store";
const appStore = useAppStore();

const { t } = useI18n();;
const props = defineProps<{
  visible: boolean;
  modelCameraForm: any; // 对象引用，直接修改
}>();
const emit = defineEmits<{
  (e: "update:visible", val: boolean): void;
}>();
onMounted(()=>{
getBoxStyleConfig()
})
const boxStyleFormRef = ref(null);

const boxStyleForm = ref({
    boxThickness: 2,
    fontThickness: 2,
    fontScale: 0.5,  
    fromAreaFill: false,
    targetAreaFill: false,
});
const getBoxStyleConfig=()=>{
    api.getBoxStyleConfig().then((res)=>{
        const resData = res.data;
        if(!resData.status)if (!resData.status) return MesAlertWTitle("error", t("message.error"), '', resData.msg, "OK");
        boxStyleForm.value = resData.datas;
    }).catch((err)=>{
        MesAlertWTitle("error", t("message.error"), '', err.message || t("message.messagetext.failedGetBoxStyleConfig"), "OK");
    });
}


watch(() => props.visible, (visible) => {
    if (visible) {getBoxStyleConfig(); }
}, {immediate: true,});

const handleSave = ()=>{
    api.setBoxStyleConfig({"boxStyle": boxStyleForm.value}).then((res)=>{
        const resData = res.data;
        if(!resData.status)if (!resData.status) return MesAlertWTitle("error", t("message.error"), '', resData.msg, "OK");
        ElMessage.success(t("message.messagetext.successsave"));
        emit("update:visible", false);
    }).catch((err)=>{
        MesAlertWTitle("error", t("message.error"), '', err.message || t("message.messagetext.failedsave"), "OK");
    });
    
};
const handleCancel = ()=>{
    emit("update:visible", false);
};
const displayBoxStyleExample = ()=>{
    appStore.setLoading(true);
    api.displayBoxStyleConfig({"boxStyle": boxStyleForm.value}).then((res)=>{
        const resData = res.data;
        if(!resData.status)if (!resData.status) return MesAlertWTitle("error", t("message.error"), '', resData.msg, "OK");
        const imgElement = document.getElementById("boxStyleExample") as HTMLImageElement;
        imgElement.src = resData.frame;
    }).catch((err)=>{
        MesAlertWTitle("error", t("message.error"), '', err.message || t("message.messagetext.failedgetboxstyleexample"), "OK");
    }).finally(()=>{
        appStore.setLoading(false)  ;
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