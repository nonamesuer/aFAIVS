<template>
  <el-dialog :model-value="visible" :title="$t('config.user_management.title')" width="760px" modal-class="bs-shade" destroy-on-close @close="closeDialog">
    <div class="login-setting-row">
      <div><div class="setting-title">{{ $t('config.user_management.enable_login') }}</div><div class="setting-description">{{ $t('config.user_management.enable_login_description') }}</div></div>
      <el-switch v-model="loginEnabled" @change="handleLoginEnabledChange" />
    </div>
    <div class="user-toolbar"><el-input v-model="keyword" clearable :placeholder="$t('config.user_management.search_placeholder')" @keyup.enter="loadUsers"><template #append><el-button :icon="Search" @click="loadUsers" /></template></el-input><el-button type="primary" :icon="Plus" @click="openCreate">{{ $t('button.add') }}</el-button></div>
    <el-table stripe :data="users" max-height="420" border empty-text="No data">
      <el-table-column prop="employeeId" :label="$t('auth.employee_id')" min-width="150" />
      <el-table-column prop="name" :label="$t('auth.name')" min-width="170" />
      <el-table-column prop="role" :label="$t('auth.role')" width="130"><template #default="scope"><el-tag :type="scope.row.role === 'admin' ? 'danger' : 'info'">{{ $t(`auth.role_${scope.row.role}`) }}</el-tag></template></el-table-column>
      <el-table-column :label="$t('button.operate')" width="150" fixed="right">
        <template #default="scope">
          <div class="operate-icons">
            <el-icon class="operate-icon" size="18px" @click="openEdit(scope.row)" :title="$t('button.modify')"><Edit /></el-icon>
            <el-icon class="operate-icon is-danger" size="18px" v-if="scope.row.employeeId !== currentEmployeeId" @click="removeUser(scope.row)" :title="$t('button.delete')"><Delete /></el-icon>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <template #footer><el-button plain @click="closeDialog">{{ $t('button.close') }}</el-button></template>
  </el-dialog>

  <el-dialog v-model="editorVisible" :title="$t(editorMode === 'create' ? 'config.user_management.add_user' : 'config.user_management.edit_user')" width="480px" modal-class="bs-shade" append-to-body destroy-on-close>
    <el-form ref="userFormRef" :model="userForm" :rules="rules" label-position="top">
      <el-form-item :label="$t('auth.employee_id')" prop="employeeId"><el-input v-model="userForm.employeeId" maxlength="32" /></el-form-item>
      <el-form-item :label="$t('auth.name')" prop="name"><el-input v-model="userForm.name" maxlength="64" /></el-form-item>
      <el-form-item :label="$t('auth.role')" prop="role"><el-select v-model="userForm.role" style="width: 100%;"><el-option :label="$t('auth.role_operator')" value="operator" /><el-option :label="$t('auth.role_admin')" value="admin" /></el-select></el-form-item>
    </el-form>
    <template #footer><el-button plain @click="editorVisible = false">{{ $t('button.cancel') }}</el-button><el-button type="primary" @click="saveUser">{{ $t('button.save') }}</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { Plus, Search } from "@element-plus/icons-vue";
import api from "@/api/index";
import { MesConfirmWTitle } from "@/assets/js/secondpk";
import { useAppStore } from "@/stores/store";

interface UserInfo {employeeId: string;name: string;role: "admin" | "operator"}
const props = defineProps<{visible: boolean}>();const emit = defineEmits<{(event: "update:visible", value: boolean): void}>();const { t } = useI18n();const appStore = useAppStore();
const users = ref<UserInfo[]>([]);const keyword = ref("");const loginEnabled = ref(false);const currentEmployeeId = ref("");const editorVisible = ref(false);const editorMode = ref<"create" | "edit">("create");const originalEmployeeId = ref("");const userFormRef = ref<FormInstance>();const userForm = reactive<UserInfo>({employeeId: "",name: "",role: "operator"});
const rules: FormRules = {employeeId: [{required: true,message: t("auth.employee_id_required"),trigger: "blur"},{pattern: /^[A-Za-z0-9_.-]{1,32}$/,message: t("auth.employee_id_invalid"),trigger: "blur"}],name: [{required: true,message: t("auth.name_required"),trigger: "blur"}],role: [{required: true,message: t("auth.role_required"),trigger: "change"}]};

watch(() => props.visible,async value => {if (value) await initialize();});
const initialize = async () => {appStore.setLoading(true);try {const status = await api.getAuthStatus({});loginEnabled.value = Boolean(status.data?.data?.loginEnabled);currentEmployeeId.value = status.data?.data?.user?.employeeId || "";await loadUsers();} finally {appStore.setLoading(false);}};
const loadUsers = async () => {const response = await api.getUsers({keyword: keyword.value.trim()});if (!response.data?.status) return ElMessage.error(response.data?.msg);users.value = response.data.data || [];};
const closeDialog = () => emit("update:visible",false);
const resetForm = () => {userForm.employeeId = "";userForm.name = "";userForm.role = "operator";originalEmployeeId.value = "";};
const openCreate = () => {editorMode.value = "create";resetForm();editorVisible.value = true;};
const openEdit = (user: UserInfo) => {editorMode.value = "edit";originalEmployeeId.value = user.employeeId;Object.assign(userForm,user);editorVisible.value = true;};
const saveUser = async () => {
  if (!userFormRef.value || !(await userFormRef.value.validate().catch(() => false))) return;
  appStore.setLoading(true);
  try {const payload = {employeeId: userForm.employeeId.trim(),name: userForm.name.trim(),role: userForm.role};const response = editorMode.value === "create" ? await api.createUser(payload) : await api.updateUser(originalEmployeeId.value,payload);if (!response.data?.status) return ElMessage.error(response.data?.msg);editorVisible.value = false;ElMessage.success(t("message.success"));await loadUsers();window.dispatchEvent(new CustomEvent("faivs-auth-state-changed"));}
  catch (error: any) {ElMessage.error(error?.response?.data?.detail || error?.message || t("message.error"));} finally {appStore.setLoading(false);}
};
const removeUser = async (user: UserInfo) => {try {await MesConfirmWTitle("warning",t("button.delete"),t("config.user_management.delete_user"),t("config.user_management.delete_confirm",{name: user.name,employeeId: user.employeeId}),t("button.confirm"),t("button.cancel"));} catch {return;}appStore.setLoading(true);try {const response = await api.deleteUser(user.employeeId);if (!response.data?.status) return ElMessage.error(response.data?.msg);ElMessage.success(t("message.success"));await loadUsers();} finally {appStore.setLoading(false);}};
const handleLoginEnabledChange = async (value: string | number | boolean) => {const enabled = Boolean(value);appStore.setLoading(true);try {const response = await api.setLoginEnabled({enabled});if (!response.data?.status) {loginEnabled.value = !enabled;return ElMessage.error(response.data?.msg);}ElMessage.success(t("config.user_management.setting_saved"));window.dispatchEvent(new CustomEvent("faivs-auth-state-changed"));} catch (error: any) {loginEnabled.value = !enabled;ElMessage.error(error?.response?.data?.detail || error?.message);} finally {appStore.setLoading(false);}};
</script>

<style scoped lang="scss">
.login-setting-row { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 16px; margin-bottom: 18px; background: var(--bs-element-bgcolor); }
.setting-title { font-weight: 700; }.setting-description { margin-top: 5px; color: var(--el-text-color-secondary); }.user-toolbar { display: flex; gap: 12px; margin-bottom: 14px; }.user-toolbar .el-input { max-width: 360px; }
.operate-icons { display: inline-flex; align-items: center; gap: 12px; }
.operate-icon { cursor: pointer; color: var(--el-text-color-regular); }
.operate-icon.is-danger { color: var(--el-color-danger); }
</style>
