<template>
  <el-dialog :model-value="visible" :title="$t('auth.login_title')" width="420px" modal-class="bs-shade" align-center :close-on-click-modal="false" :close-on-press-escape="false" :show-close="false">
    <div class="login-description">{{ $t('auth.login_description') }}</div>
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large" @submit.prevent="submitLogin">
      <el-form-item :label="$t('auth.employee_id')" prop="employeeId"><el-input ref="employeeInputRef" v-model="form.employeeId" maxlength="32" clearable autofocus :placeholder="$t('auth.employee_id_placeholder')" @keyup.enter="submitLogin" /></el-form-item>
    </el-form>
    <template #footer><el-button type="primary" style="width: 100%;" @click="submitLogin">{{ $t('auth.login') }}</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { nextTick, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import api from "@/api/index";
import { setAuthToken } from "@/api/request";
import { useAppStore } from "@/stores/store";

const props = defineProps<{visible: boolean}>();
const emit = defineEmits<{(event: "logged-in", user: Record<string,any>): void}>();
const { t } = useI18n();const appStore = useAppStore();const formRef = ref<FormInstance>();const employeeInputRef = ref();const form = reactive({employeeId: ""});
const rules: FormRules = {employeeId: [{required: true,message: t("auth.employee_id_required"),trigger: "blur"},{pattern: /^[A-Za-z0-9_.-]{1,32}$/,message: t("auth.employee_id_invalid"),trigger: "blur"}]};

watch(() => props.visible,value => {if (value) nextTick(() => employeeInputRef.value?.focus());});

const submitLogin = async () => {
  if (!formRef.value || !(await formRef.value.validate().catch(() => false))) return;
  appStore.setLoading(true);
  try {
    const response = await api.login({employeeId: form.employeeId.trim()});
    if (!response.data?.status) {ElMessage.error(response.data?.msg || t("auth.login_failed"));return;}
    setAuthToken(response.data.data.token);form.employeeId = "";emit("logged-in",response.data.data.user);ElMessage.success(t("auth.login_success"));
  } catch (error: any) {ElMessage.error(error?.response?.data?.detail || error?.message || t("auth.login_failed"));}
  finally {appStore.setLoading(false);}
};
</script>

<style scoped>.login-description { margin-bottom: 20px; color: var(--el-text-color-secondary); line-height: 1.6; }</style>
