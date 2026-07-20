<template>
    <el-dialog :model-value="visible">
        <el-form
            ref="modbusFormRef"
            :model="modbusForm"
            label-position="top"
            size="large"
        >
        
        </el-form>

    </el-dialog>

</template>
<script setup lang="ts">
import { ref, watch } from 'vue'

import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import api from '@/api/index'
import { MesAlertWTitle } from '@/assets/js/secondpk';
const props = defineProps<{
  visible: boolean
}>();
const modbusForm = ref({})
</script>