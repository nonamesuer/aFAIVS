<template>
  <div class="process-editor">
    <!-- 1. 左侧：工序步骤列表（支持拖拽排序） -->
    <div class="steps-sidebar">
      <h3>工序链配置</h3>
      <div class="step-list-wrapper">
        <div 
          v-for="(step, index) in steps" 
          :key="step.id" 
          :class="['step-item', { active: activeIndex === index }]"
          @click="activeIndex = index"
        >
          <span class="step-num">{{ index + 1 }}</span>
          <span class="step-name">{{ step.name || '未命名步骤' }}</span>
          <span :class="['type-badge', step.type]">{{ typeMap[step.type] }}</span>
        </div>
      </div>
      <button class="add-btn" @click="addNewStep">+ 新增工序步骤</button>
    </div>

    <!-- 2. 右侧：当前步骤的属性编辑器 -->
    <div class="step-editor-panel" v-if="currentStep">
      <h3>属性配置 - 步骤 {{ activeIndex + 1 }}</h3>
      
      <form @submit.prevent>
        <!-- 基础配置 -->
        <div class="form-group">
          <label>步骤名称</label>
          <input v-model="currentStep.name" placeholder="请输入步骤名称，如：螺丝锁附" />
        </div>

        <div class="form-group">
          <label>步骤类型</label>
          <select v-model="currentStep.type">
            <option value="manual">🧑‍🏭 纯人工 (仅展示提示与计数)</option>
            <option value="auto">🤖 自动化 (机器人/硬触发)</option>
            <option value="hybrid">🦾 人机协同 (人工+信号关联)</option>
          </select>
        </div>

        <div class="form-group">
          <label>作业提示 (SOP Hint)</label>
          <textarea v-model="currentStep.hint" placeholder="提示操作工的注意事项..."></textarea>
        </div>

        <div class="form-group">
          <label>目标次数 (Target)</label>
          <input type="number" v-model.number="currentStep.target" min="1" />
        </div>

        <!-- 动态配置：当包含自动/协同逻辑时展示物料和区域 -->
        <fieldset v-if="currentStep.type !== 'manual'" class="action-fieldset">
          <legend>物理动作与区域配置</legend>
          
          <div class="form-row">
            <div class="form-group">
              <label>期望物料</label>
              <select v-model="currentStep.context.expectedObject">
                <option v-for="obj in objectOptions" :key="obj" :value="obj">{{ obj }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>起始区域</label>
              <select v-model="currentStep.context.fromRegion">
                <option v-for="r in regionOptions" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>目标区域</label>
              <select v-model="currentStep.context.toRegion">
                <option v-for="r in regionOptions" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>
          </div>

          <!-- 触发条件可视化配置 (done_when) -->
          <div class="form-group">
            <label>完成触发条件 (Done When)</label>
            <div class="trigger-builder">
              <div v-for="(trigger, tIdx) in currentStep.doneWhen" :key="tIdx" class="trigger-tag">
                <code>{{ trigger }}</code>
                <span class="delete-tag" @click="removeTrigger(tIdx)">x</span>
              </div>
              <button class="small-add-btn" @click="addTrigger">添加触发条件</button>
            </div>
          </div>
        </fieldset>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

// 模拟一些全局可选择的物理常量定义（通常从后台 API 获取）
const objectOptions = ['P1 (电机)', 'P2 (螺丝)', 'W-102 (底座)']
const regionOptions = ['tray_A', 'tray_B', 'assembly_area', 'reject_bin']

const typeMap = {
  manual: '人工',
  auto: '自动',
  hybrid: '协同'
}

// 响应式配置数据
const steps = ref([
  {
    id: 1,
    name: '工件上料与对位',
    type: 'manual',
    hint: '确认工件方向与定位销一致',
    target: 1,
    context: { expectedObject: '', fromRegion: '', toRegion: '' },
    doneWhen: []
  },
  {
    id: 2,
    name: '拿取螺丝并放入装配区',
    type: 'auto',
    hint: '自动吸取螺丝并移至目标点位',
    target: 1,
    context: { expectedObject: 'P2', fromRegion: 'tray_A', toRegion: 'assembly_area' },
    doneWhen: ['pick:P2:tray_A', 'place:P2:assembly_area']
  }
])

const activeIndex = ref(0)
const currentStep = computed(() => steps.value[activeIndex.value])

// 方法
const addNewStep = () => {
  const newId = steps.value.length ? Math.max(...steps.value.map(s => s.id)) + 1 : 1
  steps.value.push({
    id: newId,
    name: '新工序步骤',
    type: 'manual',
    hint: '',
    target: 1,
    context: { expectedObject: '', fromRegion: '', toRegion: '' },
    doneWhen: []
  })
  activeIndex.value = steps.value.length - 1
}

const addTrigger = () => {
  // 这里可以弹出一个 Modal，让用户下拉选择 [动作] + [物料] + [位置] 组装生成
  // 简易起见，这里直接生成一个符合格式2的默认字符串
  const ctx = currentStep.value.context
  const mockTrigger = `pick:${ctx.expectedObject || 'OBJ'}:${ctx.fromRegion || 'REGION'}`
  currentStep.value.doneWhen.push(mockTrigger)
}

const removeTrigger = (index) => {
  currentStep.value.doneWhen.splice(index, 1)
}
</script>

<style scoped>
/* 推荐后台管理系统经典的“左侧列表、右侧表单”布局，使用 Flex/Grid 保持屏幕自适应 */
.process-editor {
  display: flex;
  gap: 24px;
  height: 600px;
  font-family: sans-serif;
}
.steps-sidebar {
  width: 280px;
  border-right: 1px solid #eee;
  display: flex;
  flex-direction: column;
}
.step-list-wrapper {
  flex: 1;
  overflow-y: auto;
}
.step-item {
  padding: 12px;
  border: 1px solid #e0e0e0;
  margin-bottom: 8px;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-item.active {
  border-color: #409eff;
  background-color: #ecf5ff;
}
.type-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
  margin-left: auto;
}
.type-badge.manual { background: #e6a23c; color: white; }
.type-badge.auto { background: #409eff; color: white; }
.type-badge.hybrid { background: #67c23a; color: white; }

.step-editor-panel {
  flex: 1;
  padding: 16px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  overflow-y: auto;
}
.form-group {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
}
.form-row {
  display: flex;
  gap: 16px;
}
.action-fieldset {
  border: 1px dashed #ccc;
  padding: 16px;
  border-radius: 6px;
}
.trigger-tag {
  display: inline-flex;
  align-items: center;
  background: #f4f4f5;
  padding: 4px 8px;
  margin-right: 8px;
  border-radius: 4px;
  border: 1px solid #e9e9eb;
}
.delete-tag {
  margin-left: 8px;
  cursor: pointer;
  color: #f56c6c;
}
</style>
