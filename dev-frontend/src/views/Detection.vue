<template>
    <div class="layout-container">
        <el-container class="layout-container">
            <el-container>
                <el-main class="main-pane">
                    <div class="camera-layout">
                        <div class="camera-item-top" :style="{backgroundColor:streamConnected?'green':'red'}"></div>
                        <div class="camera-item-header flex-center">
                            <div class="header-left flex-center">
                                <div class="text-auto-hidden">{{ cameraName }}</div>
                                <el-divider direction="vertical" />
                                <div class="text-auto-hidden">{{ sopConfigrationData.model || '' }}</div>
                                <el-divider direction="vertical" />
                                <div class="text-auto-hidden">{{ sopConfigrationData.confidence || 0 }}</div>
                                <el-divider direction="vertical" />
                                <el-tag effect="dark" size="small" :type="detectionRunningStatus[1]">
                                    {{ detectionRunningStatus[0] }}
                                </el-tag>
                                <el-divider direction="vertical" />
                                <el-tag effect="dark"  :type="streamTransport === 'webrtc' ? 'success' : 'warning'">
                                    {{ streamTransport === 'webrtc' ? 'WebRTC' : 'MJPEG' }}
                                </el-tag>
                                <el-divider direction="vertical" />
                                <div v-if="showStepTimeout" class="header-timeout">
                                    <el-progress class="header-timeout-progress" :percentage="stepTimeoutPercentage" :stroke-width="7" :format="()=>`${formatTimeoutDuration(stepTimeoutElapsed - 1)} / ${formatTimeoutDuration(stepTimeoutTotal)}`"/>
                                </div>

                                

                            </div>
                            <div class="header-right">结果</div>
                        </div>

                        <div class="camera-item-body">
                            <div v-if="!streamConnected" class="reconnecting-message">
                                {{ streamErrorMessage || $t('message.messagetext.webrtcStreamError') }}
                            </div>
                            <el-alert :closable="true" @close="criticalAlerts = []" show-icon v-if="criticalAlerts.length" :title="`${criticalAlerts[0].code} ${criticalAlerts[0].message}`" type="error" effect="dark" />
                            <video
                                v-if="detectionActive  && streamTransport === 'webrtc'"
                                ref="streamVideoRef"
                                class="video-stream"
                                autoplay
                                playsinline
                                muted
                            ></video>

                            <img
                                v-else-if="detectionActive"
                                ref="streamImageRef"
                                class="video-stream"
                                :src="mjpegUrl"
                                alt="server-stream"
                                @load="modifyStreamAlert(true, '')"
                                @error="modifyStreamAlert(false,t('message.messagetext.mjpegStreamError'))"
                            />

                            <div class="current-step-overlay" v-if="currentStep">
                                <div class="overlay-title">当前工序</div>
                                <div class="overlay-name text-auto-hidden">{{ currentStep.name }}</div>
                                <div class="overlay-meta">目标 {{ currentStep.target }} | 当前 {{ currentStep.current }} | {{ getStepStatusLabel(currentStep.status) }}</div>
                                <div v-if="currentStep.reason" class="overlay-reason text-auto-hidden">{{ currentStep.reason }}</div>
                            </div>
                        </div>
                    </div>
                </el-main>

                <el-footer class="action-footer">
                    <div class="footer-progress">
                        <el-progress type="circle" color="var(--bs-primary-color)" :percentage="overallProgress" :width="58" :stroke-width="6" />
                        <span class="footer-title">总进度</span>
                    </div>
                    <div class="footer-current" v-if="currentStep">
                        <div class="footer-current-title">{{ currentStep.name }}</div>
                        <div ref="footerHintRef" class="footer-current-hint" :title="currentStep.hint || '等待工序提示'">
                            <div ref="footerHintTextRef" class="footer-current-hint-track" :class="{ 'is-scrolling': footerHintOverflow }">
                                <div class="footer-current-hint-text">
                                    {{ currentStep.hint || '等待工序提示' }}
                                    <div v-if="footerHintOverflow" class="footer-current-hint-end">-- 提示结束 --</div>
                                </div>
                                <div v-if="footerHintOverflow" class="footer-current-hint-text" aria-hidden="true">
                                    {{ currentStep.hint || '等待工序提示' }}
                                    <div class="footer-current-hint-end">-- 提示结束 --</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="footer-actions">
                        <el-button type="primary" :icon="VideoPlay" v-if="!detectionActive" @click="handleStartDetection">开始</el-button>
                        <el-button type="primary" plain :icon="VideoPause" v-if="detectionRunning" @click="handlePauseDetection">暂停</el-button>
                        <el-button type="primary" :icon="VideoPlay" v-if="detectionPaused" @click="handleResumeDetection">继续</el-button>
                        <el-button type="warning" v-if="detectionActive" @click="handleCloseDetection">复位</el-button>
                        <el-button type="success" @click="test">确认完成</el-button>
                        <el-button type="danger" plain>人工复检</el-button>
                    </div>
                </el-footer>
            </el-container>

            <el-aside width="340px" class="right-side">
                <el-card class="side-card side-card-current" shadow="never">
                    <template #header>
                        <div>当前工序</div>
                    </template>
                    <div class="current-section" v-if="currentStep">
                        <div class="current-name">{{ currentStep.name }}</div>
                        <div class="current-desc">{{ currentStep.hint }}</div>
                        <!-- <el-alert
                            v-if="currentStep.status === 'error' && currentStep.reason"
                            class="current-error-alert"
                            :closable="false"
                            show-icon
                            type="error"
                            :title="currentStep.reason"
                        /> -->
                        <div class="current-progress-row">
                            <div class="current-metrics">
                                <div class="current-metric current-metric-target">
                                    <span>目标</span>
                                    <strong>{{ currentStep.target }}</strong>
                                </div>
                                <div class="current-metric current-metric-current">
                                    <span>当前</span>
                                    <strong>{{ currentStep.current }}</strong>
                                </div>
                            </div>
                            <div class="current-progress-meter">
                                <span class="current-progress-label">进度</span>
                                <el-progress :percentage="currentStepProgress" :stroke-width="9" :show-text="false" />
                                <strong>{{ currentStepProgress }}%</strong>
                            </div>
                        </div>
                    </div>
                    
                </el-card>

                <el-card class="side-card side-card-steps" shadow="never">
                    <template #header>
                        <div>工序步骤：<span>{{okCount }}/{{ processSteps.length }}</span></div>
                    </template>
                    <div v-if="processSteps.length > 0">
                        <el-steps direction="vertical" class="bs-step-normal process-steps" :active="currentStepIndex" finish-status="success">
                            <el-step
                                v-for="step in processSteps"
                                :key="step.id"
                                :title="step.name"
                                :description="getStepDescription(step)"
                                :status="step.status"
                            />
                        </el-steps>
                    </div>
                </el-card>


                <el-card class="side-card side-card-alerts" shadow="never">
                    <template #header>
                        <div style="color:red">错误与告警：<span>{{ ngCount }}</span></div>
                    </template>
                    <div>
                        <div v-if="!unconfirmedAlerts.length" class="empty-state">暂无未确认告警</div>
                        <div v-else class="alert-list">
                            <div v-for="alert in unconfirmedAlerts" :key="alert.id" :title="`${alert.code} | ${alert.message}`" class="alert-item" :class="`alert-${alert.level}`">
                                <div class="alert-line">
                                    <el-tag size="small" :type="getTagType(alert.level)">{{ alert.code }}</el-tag>
                                    <span class="alert-message">{{ alert.message }}</span>
                                </div>
                                <!-- <el-button size="small" text @click="confirmAlert(alert.id)">确认</el-button> -->
                            </div>
                        </div>
                    </div>
                </el-card>


                <el-card class="side-card side-card-events" shadow="never">
                    <template #header>
                        <div>实时事件</div>
                    </template>
                    <div class="events-section">
                        <div class="event-list">
                            <div v-for="evt in events" :key="evt.id" :title="`${evt.time} | ${evt.step} | ${evt.text}`" class="event-item" :class="getEventClass(evt.level)">
                                <span class="event-time">{{ evt.time }}</span>
                                <span class="event-step text-auto-hidden">{{ evt.step }}</span>
                                <span class="event-text text-auto-hidden">{{ evt.text }}</span>
                            </div>
                        </div>

                    </div>
                </el-card>
            </el-aside>
        </el-container>
    </div>
</template>
<script setup>
/**
 * *********************************************************
 * Start 依赖与应用上下文
 * 这里统一放 Vue、接口、状态仓库、国际化等页面基础依赖。
 * *********************************************************
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { MesAlertWTitle, MesConfirmWTitle } from "@/assets/js/secondpk";
import { VideoPlay, VideoPause, Pointer,Warning } from "@element-plus/icons-vue";
import api from "@/api/index";
import { useAppStore } from "@/stores/store";   
import { useI18n } from "vue-i18n";
const appStore = useAppStore(); // 全局 store：主要用于控制页面 loading 状态。
const { t } = useI18n(); // 国际化函数：用于读取 lang 目录中的提示文案。
/**
 * *********************************************************
 * End 依赖与应用上下文
 * *********************************************************
 */


/**
 * *********************************************************
 * Start 页面基础状态变量
 * 这里统一放模板直接使用的响应式变量、DOM 引用和默认展示数据。
 * *********************************************************
 */
const cameraName = ref(t('displaytext.noconfigcamera')) // 当前摄像头名称，展示在顶部左侧。
const streamConnected = ref(false) // 视频流是否已连接，用于显示在线/离线和重连提示。
const streamErrorMessage = ref(t('message.messagetext.closedDetection')) // 视频流或检测接口异常时展示的提示文案。
const streamVideoRef = ref(null) // WebRTC video 元素引用，用于挂载后端视频流 MediaStream。
const streamImageRef = ref(null) // MJPEG img 元素引用，用于 Firefox 或兜底流显示。
const streamTransport = ref('webrtc') // 当前视频传输方式：webrtc 或 mjpeg。
const detectionRunning = ref(false) // 后端检测是否正在运行，用于按钮禁用和视频显示控制。
const detectionInitialized = ref(false) // 后端检测运行时是否已初始化，用于复位按钮状态。
const detectionPaused = ref(false) // 后端检测运行时是否已暂停，用于按钮禁用和视频显示控制。
const detectionActive = ref(false) // 后端检测运行时是否处于激活状态，用于按钮禁用和视频显示控制。
const okCount = ref(0) // 后端累计 OK 数量。
const ngCount = ref(0) // 后端累计 NG 数量。

const footerHintRef = ref(null) // 底部大号 hint 可视容器引用，用于判断是否溢出。
const footerHintTextRef = ref(null) // 底部大号 hint 文本轨道引用，用于纵向滚动动画。
const footerHintOverflow = ref(false) // 底部大号 hint 是否超过两行，超过时开启纵向滚动。

const detectionResult = ref({
    step: null, // 后端识别到的当前工序序号，从 1 开始。
    gesture: 'idle', // 后端返回的动作/手势状态，当前页面暂未直接展示。
    bbox: [], // 后端返回的主检测框数据，预留给画框使用。
    detections: [], // 后端返回的检测对象列表，预留给明细展示使用。
    score: 0, // 后端返回的置信度，范围通常是 0 到 1。
    ok_count: 0, // 后端返回的 OK 计数。
    ng_count: 0, // 后端返回的 NG 计数。
    updated_at: 0, // 后端结果更新时间戳。
    sop: null, // 后端 SOP 状态机结果。
})
// 工序步骤列表：右侧步骤条、当前工序卡片、底部提示都从这里取数据。
const processSteps = ref([])

const alerts = ref([]) // 告警列表：右侧“错误与告警”卡片的数据源。
const events = ref([]) // 实时事件列表：右侧“实时事件”卡片的数据源。
let lastSopEventKey = ''
/**
 * *********************************************************
 * End 页面基础状态变量
 * *********************************************************
 */


/**
 * *********************************************************
 * Start 页面样式状态与展示计算
 * 这里统一放会影响标签、进度、步骤状态、顶部状态条样式的 computed。
 * *********************************************************
 */
const detectionRunningStatus = computed(()=>{
    if(detectionPaused.value)return ['已暂停','warning'];
    if(detectionRunning.value)return ['运行中','success'];
    return ['未启动','info'];
})
const currentStepIndex = computed(() => {
    if (!detectionActive.value) return -1;
    const sopProgress = detectionResult.value.sop?.progress
    if (sopProgress && processSteps.value.length) {
        const currentIndex = Number(sopProgress.current_index || 0)
        return Math.min(Math.max(currentIndex, 0), processSteps.value.length - 1)
    }
    const idx = processSteps.value.findIndex((s) => s.status === 'process');
    return idx;
    // return idx === -1 ? 0 : idx
})

const currentStep = computed(() => {
    if (currentStepIndex.value < 0)return null;
    return processSteps.value[currentStepIndex.value] || null;
})

const overallProgress = computed(() => {
    const sopProgress = detectionResult.value.sop?.progress
    if (sopProgress?.total) {
        return Number(Math.min(100, (Number(sopProgress.done || 0) / Number(sopProgress.total)) * 100).toFixed(1))
    }
    const total = processSteps.value.length
    if (!total) {
        return 0
    }
    const done = processSteps.value.filter((s) => s.status === 'success').length
    const processRatio = currentStep.value && currentStep.value.target > 0
        ? (currentStep.value.current / currentStep.value.target)
        : 0
    const value = ((done + Math.min(1, processRatio)) / total) * 100
    return Number(value.toFixed(1))
})

const currentStepProgress = computed(() => {
    if (!currentStep.value || currentStep.value.target === 0) {
        return 0
    }
    return Number(Math.min(100, (currentStep.value.current / currentStep.value.target) * 100).toFixed(1))
})

const unconfirmedAlerts = computed(() => alerts.value.filter((a) => !a.confirmed))
// const criticalAlerts = computed(() => unconfirmedAlerts.value.filter((a) => a.level === 'error'))
const criticalAlerts = ref([]) // 当前未确认的严重告警列表，用于顶部红色提示条。
const sopConfigrationData = ref({}); // 当前启用的 SOP 配置对象。
let criticalAlertTimer = null;

/**
 * *********************************************************
 * End 页面样式状态与展示计算
 * *********************************************************
 */


/**
 * *********************************************************
 * Start 页面展示辅助方法
 * 这里统一放模板中使用的状态文本、标签类型、事件样式和告警确认方法。
 * *********************************************************
 */
const showCriticalAlert = (alert, duration = 5000) => {
    criticalAlerts.value = [alert]

    if (criticalAlertTimer) {
        clearTimeout(criticalAlertTimer)
        criticalAlertTimer = null
    }

    criticalAlertTimer = setTimeout(() => {
        criticalAlerts.value = []
        criticalAlertTimer = null
    }, duration)
}
const getTagType = (level) => {return level === 'error' ? 'danger' : level === 'warning' ? 'warning' : 'info'}

const getStepStatusLabel = (status) => {return status === 'success' ? '已完成' : status === 'process' ? '进行中' : status === 'error' ? '阻塞' : '未开始'}
//工序步骤中的状态
const getStepDescription = (step = {}) => {
    const baseText = `状态: ${getStepStatusLabel(step.status)} | 目标: ${step.target}`
    if (step.reason) {
        return `${baseText} | ${step.reason}`
    }
    return baseText
}

const getEventClass = (level) => {
    if (level === 'error') {
        return 'event-error'
    }
    if (level === 'warning') {
        return 'event-warning'
    }
    return 'event-info'
}

const getNowTime = () => {
    const now = new Date()
    return now.toLocaleTimeString('zh-CN', { hour12: false })
}

// const getSopEventLevel = (state) => {
//     if (state === 'failed') {
//         return 'error'
//     }
//     if (state === 'completed') {
//         return 'info'
//     }
//     return 'info'
// }

const getSopReasonText = (reason = '') => {
    if (!reason) {
        return '等待检测结果'
    }
    const wrongObjectMatch = reason.match(/^NG: Expected (.+), but (.+) entered (.+)$/)
    if (wrongObjectMatch) {
        return `异常: 当前工序应安装 ${wrongObjectMatch[1]}，检测到 ${wrongObjectMatch[2]} 进入 ${wrongObjectMatch[3]}`
    }
    if (reason.startsWith('NG: ')) {
        return reason.replace('NG: ', '异常: ')
    }
    if (reason.startsWith('Step timeout: ')) {
        return reason.replace('Step timeout: ', '工序超时: ')
    }
    if (reason.startsWith('Waiting for region ')) {
        return `等待区域 ${reason.replace('Waiting for region ', '')}`
    }
    if (reason.startsWith('Waiting for ')) {
        return `等待目标 ${reason.replace('Waiting for ', '')}`
    }
    if (reason.startsWith('Move ') && reason.includes(' into ')) {
        const [objectName, regionName] = reason.replace('Move ', '').split(' into ')
        return `请将 ${objectName} 放入 ${regionName}`
    }
    if (reason.includes(' entered ')) {
        const [objectName, regionName] = reason.split(' entered ')
        return `${objectName} 已进入 ${regionName}`
    }
    if (reason === 'All steps completed') {
        return '全部工序已完成'
    }
    return reason
}

const getSopAlertCode = (reason = '') => {
    if (reason.startsWith('Step timeout: ')) {
        return 'SOP_TIMEOUT'
    }
    if (reason.startsWith('NG: ')) {
        return 'SOP_NG'
    }
    return 'SOP_ERROR'
}

// const confirmAlert = (id) => {
//     const target = alerts.value.find((a) => a.id === id)
//     if (target) {
//         target.confirmed = true
//     }
// }
/**
 * *********************************************************
 * End 页面展示辅助方法
 * *********************************************************
 */


/**
 * *********************************************************
 * Start 底部当前工序 hint 自动滚动逻辑
 * 这里负责判断底部大号 hint 是否超过两行，超过后开启纵向滚动动画。
 * *********************************************************
 */
const updateFooterHintOverflow = async () => {
    footerHintOverflow.value = false
    await nextTick()
    const container = footerHintRef.value
    const text = footerHintTextRef.value
    const firstText = text?.firstElementChild
    footerHintOverflow.value = Boolean(container && firstText && firstText.scrollHeight > container.clientHeight + 1)
}
/**
 * *********************************************************
 * End 底部当前工序 hint 自动滚动逻辑
 * *********************************************************
 */


/**
 * *********************************************************
 * Start my featrue 自定义 SOP 配置逻辑
 * 这里负责读取后端启用的 SOP 配置，并把配置 steps 转成页面工序步骤。
 * 2026.06.30
 * *********************************************************
 */


/**
 * 
 * @param data
 * 校验sop配置参数
 */
const resolveSopConfig = (data = {}) => {
    if (Array.isArray(data.steps))return data
    return Object.values(data).find((item) => item && Array.isArray(item.steps)) || {}
}
/**
 * 
 * @param steps 
 * 将配置工序转换为页面工序步骤，保证每个步骤都有 id、name、target、current、status、hint。
 */
const buildProcessSteps = (steps = []) => {
    return steps.map((step, index) => ({
        ...step,
        id: step.id ?? index + 1,
        name: step.name || `工序${index + 1}`,
        target: Number(step.target ?? 1),
        current: 0,
        status: 'wait',
        hint: step.hint || '',
        reason: '',
    }))
}
const resetProcessSteps = () => {
    detectionResult.value.step = null
    detectionResult.value.sop = null
    processSteps.value.forEach((step) => {
        step.current = 0
        step.status = 'wait'
        step.reason = ''
    })

    lastSopEventKey = ''
}
const mapSopStepStatus = (state) => {
    if (state === 'done') {
        return 'success'
    }
    if (state === 'active') {
        return 'process'
    }
    if (state === 'failed') {
        return 'error'
    }
    return 'wait'
}

const buildProcessStepsFromSop = (sop = {}) => {
    const steps = Array.isArray(sop.steps) ? sop.steps : []
    if (!steps.length) {
        return
    }
    const failedReason = sop.state === 'failed' ? getSopReasonText(sop.reason || '') : ''
    processSteps.value = steps.map((step, index) => ({
        id: step.id ?? index + 1,
        name: step.name || `工序${index + 1}`,
        target: Number(step.target ?? 1),
        current: Number(step.matched_count ?? 0),
        status: mapSopStepStatus(step.state),
        hint: step.hint || '',
        reason: step.state === 'failed' ? failedReason : getSopReasonText(step.last_reason || ''),
    }))
}
// const getSopLiveEventLevel = (sop = {}) => {
//     const step = sop.current_step
//     if (sop.state === 'completed' || step?.state === 'done') return 'success'
//     // FAILED 的红色错误已经由告警区域单独显示。
//     // 阻塞后的实时操作过程继续作为普通实时事件显示。
//     return 'info'
// }
const getSopLiveEventLevel = (sop = {}) => {
    const step = sop.current_step
    if (sop.state === 'failed' || step?.state === 'failed') return 'error'
    if (sop.state === 'completed' || step?.state === 'done') return 'success'
    return 'info'
}
const appendSopEvent = (sop = {}) => {
    const step = sop.current_step;
    const isFailed = sop.state === 'failed' || step?.state === 'failed'
    const rawReason = isFailed ? (sop.reason || step?.last_reason || '') : (step?.last_reason || sop.reason || '')
    if(!rawReason)return;
    // 实时事件优先使用当前步骤实时状态。
    // sop.reason 在 FAILED 时保留原始阻塞原因。
    // const rawReason = step?.last_reason || sop.reason || '';
    const reasonText = getSopReasonText(rawReason)
    if (!reasonText)return;
    const eventKey = [
        sop.state,
        step?.state || '',
        step?.id || 'done',
        step?.pick_state || '',
        step?.matched_count || 0,
        step?.awaiting_cycle_reset || false,
        rawReason,
        sop.progress?.done || 0,
    ].join('-')
    // const eventKey = `${sop.state}-${step?.id || 'done'}-${reasonText}-${sop.progress?.done || 0}`
    if (eventKey === lastSopEventKey) {
        return
    }
    lastSopEventKey = eventKey
    events.value.unshift({
        id: `${Date.now()}-${Math.random()}`,
        time: getNowTime(),
        level: getSopLiveEventLevel(sop),
        step: step?.name || 'SOP',
        text: reasonText,
    })
    events.value = events.value.slice(0, 30)
}
let lastCriticalAlertKey = ''
const syncSopAlert = (sop = {}) => {
    const step = sop.current_step

    const isFailed =
        sop.state === 'failed' ||
        step?.state === 'failed'

    if (!isFailed) {
        lastCriticalAlertKey = ''
        return
    }

    const rawReason =
        sop.reason ||
        step?.last_reason ||
        'SOP 状态异常'

    const code = getSopAlertCode(rawReason)
    const message = getSopReasonText(rawReason)

    const alertKey = [
        step?.id || 'sop',
        code,
        rawReason,
    ].join('|')

    if (alertKey === lastCriticalAlertKey) {
        return
    }

    lastCriticalAlertKey = alertKey

    const alertItem = {
        id: `sop-${Date.now()}-${Math.random()}`,
        level: 'error',
        code,
        message,
        confirmed: false,
    }

    alerts.value.unshift(alertItem)
    alerts.value = alerts.value.slice(0, 50)

    showCriticalAlert(alertItem, 5000)
}

const applySopState = (sop) => {
    if (!sop || typeof sop !== 'object') {
        updateStepStatuses()
        return
    }
    buildProcessStepsFromSop(sop)
    appendSopEvent(sop)
    syncSopAlert(sop)
}

const getSopConfigration = async()=>{
    appStore.setLoading(true);
    try {
        const res = await api.getSopConfigration();
        const resData = res.data;
        if(!resData.status) return MesAlertWTitle('error',t("message.error"), t("message.messagetext.failed_get_config"), resData.msg, "OK")
        sopConfigrationData.value = resolveSopConfig(resData.data || {});
        cameraName.value = resData.enableCamera || t('displaytext.noconfigcamera');
        if(Object.keys(sopConfigrationData.value).length===0){
            console.log("这里需要根据是否有配置来决定检测页面的显示状况");
        }else{
            //处理processSteps
            let steps = sopConfigrationData.value.steps || [];
            processSteps.value = buildProcessSteps(steps);
            // updateStepStatuses();
        }
    } catch (error) {
        MesAlertWTitle("error", t("message.error"), t("message.messagetext.failed_get_config"), error.message, "OK")
    } finally {
        appStore.setLoading(false);
    }
}
/**
 * *********************************************************
 * End my featrue 自定义 SOP 配置逻辑
 * 2026.06.30
 * *********************************************************
 */
/**
 * 步骤超时时间Start
 */
//步骤的超时时间
const timeoutNow = ref(Date.now())
let timeoutTicker = null
const currentSopRuntimeStep = computed(() => {
    return detectionResult.value.sop?.current_step || null
})
const stepTimeoutTotal = computed(() => {
    const timeout = Number(currentSopRuntimeStep.value?.timeout || 0)

    if (!Number.isFinite(timeout) || timeout <= 0) {
        return 0
    }

    return timeout
})
const stepTimeoutElapsed = computed(() => {
    const sop = detectionResult.value.sop
    const step = currentSopRuntimeStep.value

    if (!sop || !step) {
        return 0
    }

    const serverElapsed = Math.max(
        0,
        Number(step.elapsed || 0)
    )

    const timeout = stepTimeoutTotal.value

    if (timeout <= 0) {
        return 0
    }

    /*
     * 只有 SOP 正在运行且检测没有暂停时，
     * 才在后端 elapsed 基础上进行本地补时。
     */
    const shouldAdvanceLocally =
        sop.state === 'running' &&
        detectionRunning.value &&
        !detectionPaused.value &&
        step.state === 'active'

    if (!shouldAdvanceLocally) {
        return Math.min(timeout, serverElapsed)
    }

    const serverUpdatedAtMs =
        Number(sop.updated_at || 0) * 1000

    if (!serverUpdatedAtMs) {
        return Math.min(timeout, serverElapsed)
    }

    const localDeltaSeconds = Math.max(
        0,
        (timeoutNow.value - serverUpdatedAtMs) / 1000
    )

    return Math.min(
        timeout,
        serverElapsed + localDeltaSeconds
    )
})
const stepTimeoutRemaining = computed(() => {
    return Math.max(
        0,
        stepTimeoutTotal.value - stepTimeoutElapsed.value
    )
})
const stepTimeoutPercentage = computed(() => {
    if (stepTimeoutTotal.value <= 0) {
        return 0
    }

    const percentage =
        (
            stepTimeoutElapsed.value /
            stepTimeoutTotal.value
        ) * 100

    return Number(
        Math.min(100, Math.max(0, percentage)).toFixed(1)
    )
})
const showStepTimeout = computed(() => {
    const sop = detectionResult.value.sop
    const step = currentSopRuntimeStep.value

    if (!detectionActive.value) {
        return false
    }

    if (!sop || !step) {
        return false
    }

    if (stepTimeoutTotal.value <= 0) {
        return false
    }

    if (sop.state === 'completed') {
        return false
    }

    return ['active', 'failed'].includes(step.state)
})

const formatTimeoutDuration = (seconds) => {
    const safeSeconds = Math.max(
        0,
        Math.ceil(Number(seconds || 0))
    )

    if (safeSeconds < 60) {
        return `${safeSeconds}秒`
    }

    const minutes = Math.floor(safeSeconds / 60)
    const remainingSeconds = safeSeconds % 60

    return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`
}
/**
 * end
 */

/**
 * *********************************************************
 * Start 检测运行状态与结果应用逻辑
 * 这里负责把后端运行状态和检测结果同步到页面步骤、计数、置信度。
 * *********************************************************
 */
const applyRuntimeStatus = (payload = {}) => {
    detectionInitialized.value = Boolean(payload.initialized)
    detectionRunning.value = Boolean(payload.running)
    detectionPaused.value = Boolean(payload.paused)
    detectionActive.value = Boolean(payload.active)
}

const updateStepStatuses = () => {
    // 检测没有开始，所有工序保持未开始状态
    if (!detectionActive.value || detectionResult.value.step == null) {
        processSteps.value.forEach((step) => {step.status = 'wait'})
        return
    }
    const activeStep = Number(detectionResult.value.step);
    processSteps.value.forEach((step, index) => {
        const stepNo = index + 1
        if (stepNo < activeStep) {
            step.status = 'success'
        } else if (stepNo === activeStep) {
            step.status = 'process'
            return
        } else {
            step.status = 'wait'
        }
    });
}

const applyDetectionResult = (payload) => {
    detectionResult.value = {
        step: payload?.step ?? detectionResult.value.step,
        gesture: payload?.gesture ?? detectionResult.value.gesture,
        bbox: Array.isArray(payload?.bbox) ? payload.bbox : [],
        detections: Array.isArray(payload?.detections) ? payload.detections : [],
        score: Number(payload?.score ?? detectionResult.value.score),
        ok_count: Number(payload?.ok_count ?? okCount.value),
        ng_count: Number(payload?.ng_count ?? ngCount.value),
        updated_at: Number(payload?.updated_at ?? Date.now() / 1000),
        sop: payload?.sop || detectionResult.value.sop,
    }
    okCount.value = detectionResult.value.ok_count
    ngCount.value = detectionResult.value.ng_count
    applySopState(detectionResult.value.sop)
}
/**
 * *********************************************************
 * End 检测运行状态与结果应用逻辑
 * *********************************************************
 */


/**
 * *********************************************************
 * Start 视频流接口地址与连接状态变量
 * 这里统一放 WebRTC、MJPEG、WebSocket 相关地址和连接实例。
 * *********************************************************
 */
const reconnectDelayMs = 3000 // 视频流或结果 WebSocket 断线后的重连延迟。
let reconnectTimer = null // WebRTC 视频流重连定时器。
let manuallyStopped = false // 是否由用户主动停止，用于阻止自动重连。
let resultSocket = null // 检测结果 WebSocket 实例。
let resultReconnectTimer = null // 检测结果 WebSocket 重连定时器。
let pc = null // 当前 WebRTC RTCPeerConnection 实例。
let webRtcStarting = false // WebRTC 是否正在启动，避免异步启动流程重入。
let webRtcStartToken = 0 // WebRTC 启动令牌，用于丢弃过期的异步启动结果。
const mjpegUrl = ref(`${api.mjpegBaseUrl}?ts=${Date.now()}`) // MJPEG 图片流 URL，加时间戳用于刷新连接。
/**
 * *********************************************************
 * End 视频流接口地址与连接状态变量
 * *********************************************************
 */


/**
 * *********************************************************
 * Start WebRTC ICE 配置逻辑
 * 这里根据环境变量生成 WebRTC ICE servers，默认使用公开 STUN。
 * *********************************************************
 */
const buildIceServers = () => {
    const urlsRaw = String(import.meta.env.VITE_WEBRTC_ICE_URLS || '').trim();
    const username = String(import.meta.env.VITE_WEBRTC_ICE_USERNAME || '').trim();
    const credential = String(import.meta.env.VITE_WEBRTC_ICE_CREDENTIAL || '').trim();
    const urls = urlsRaw? urlsRaw.split(',').map((item) => item.trim()).filter(Boolean) : [];
    if (!urls.length) return [{ urls: ['stun:stun.l.google.com:19302'] }] // WebRTC 默认 STUN 服务器配置。
    if (username && credential) return [{ urls, username, credential }];
    return [{ urls }]
}
/**
 * *********************************************************
 * End WebRTC ICE 配置逻辑
 * *********************************************************
 */


/**
 * *********************************************************
 * Start 视频流与结果通道逻辑
 * 这里负责 WebRTC/MJPEG 视频流、检测结果 WebSocket、断线重连和资源释放。
 * *********************************************************
 */
const clearReconnect = () => {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
    }
}

const clearResultReconnect = () => {
    if (resultReconnectTimer) {
        clearTimeout(resultReconnectTimer)
        resultReconnectTimer = null
    }
}

const scheduleResultSocketReconnect = () => {
    if (manuallyStopped || !detectionActive.value || resultReconnectTimer) {
        return
    }
    resultReconnectTimer = setTimeout(() => {
        resultReconnectTimer = null
        connectResultSocket()
    }, reconnectDelayMs)
}

const closeResultSocket = () => {
    clearResultReconnect()
    if (resultSocket) {
        try {
            resultSocket.onmessage = null
            resultSocket.onclose = null
            resultSocket.onerror = null
            resultSocket.close()
        } catch (err) {
            console.warn('关闭结果 websocket 失败:', err)
        }
        resultSocket = null
    }
}

const connectResultSocket = () => {
    // 检测结果走 WebSocket，视频流和结果数据解耦。
    closeResultSocket()
    if (!detectionActive.value) {
        return
    }
    try {
        resultSocket = new WebSocket(api.resultWsUrl)
        resultSocket.onmessage = (event) => {
            try {
                let payload = JSON.parse(event.data);
                console.log("streamTransport",streamTransport.value);
                if("ws_result" in payload){
                    payload = payload.ws_result
                    applyDetectionResult(payload)
                }else if("camera_status" in payload){
                    payload = payload.camera_status;
                    const status = payload.status;
                    if (status === 'reconnecting') {
                        if(streamTransport.value == 'mjpeg'){
                            mjpegUrl.value = null;
                        }
                        modifyStreamAlert(false,payload.message)
                    } else if (status === 'reconnected') {
                        if(streamTransport.value == 'mjpeg'){
                            mjpegUrl.value = `${api.mjpegBaseUrl}?ts=${Date.now()}`
                        }
                        modifyStreamAlert(true,'')
                    } else if (status === 'disconnected') {
                        stopClientStreams(payload.message)
                        modifyStreamAlert(false,payload.message)
                    }
                }
                
            } catch (err) {
                console.warn('解析检测结果失败:', err)
            }
        }
        resultSocket.onclose = (event) => {
            resultSocket = null
            if (event.code === 1000) {
                stopStream()
                modifyStreamAlert(null,t('message.messagetext.closedDetection'),true)
                return
            }
            if (manuallyStopped || !detectionRunning.value) {
                return
            }
            scheduleResultSocketReconnect()
        }
        resultSocket.onerror = () => {
            scheduleResultSocketReconnect()
        }
    } catch (err) {
        console.warn('连接结果 websocket 失败:', err)
        scheduleResultSocketReconnect()
    }
}

const closePeerConnection = () => {
    if (pc) {
        try {
            pc.ontrack = null
            pc.onconnectionstatechange = null
            pc.oniceconnectionstatechange = null
            pc.onicegatheringstatechange = null
            pc.onicecandidateerror = null
            pc.close()
        } catch (err) {
            console.warn('关闭 WebRTC 连接失败:', err)
        }
        pc = null
    }
}

const stopServerStream = () => {
    if (streamVideoRef.value) {
        streamVideoRef.value.srcObject = null
    }
    if (streamImageRef.value) {
        streamImageRef.value.src = ''
    }
}

// Firefox 使用低帧率 MJPEG，避开 WebRTC ICE 兼容性问题。
const startMjpegStream = () => {
    closePeerConnection()
    clearReconnect()
    streamTransport.value = 'mjpeg'
    modifyStreamAlert(false,t('message.messagetext.mipegconnnecting'))
    mjpegUrl.value = `${api.mjpegBaseUrl}?ts=${Date.now()}`
}

const scheduleReconnect = () => {
    if (manuallyStopped || !detectionRunning.value || reconnectTimer) {
        return
    }
    const token = webRtcStartToken
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        if (manuallyStopped || !detectionRunning.value || token !== webRtcStartToken) {
            return
        }
        startWebRtcStream()
    }, reconnectDelayMs)
}

const handleWebRtcError = () => {
    modifyStreamAlert(false,t('message.messagetext.webrtcStreamError'));
    stopServerStream()
    scheduleReconnect()
}

const waitForIceGatheringComplete = (peerConnection) => {
    if (peerConnection.iceGatheringState === 'complete') {
        return Promise.resolve()
    }
    return new Promise((resolve) => {
        const handler = () => {
            if (peerConnection.iceGatheringState === 'complete') {
                peerConnection.removeEventListener('icegatheringstatechange', handler)
                resolve()
            }
        }
        peerConnection.addEventListener('icegatheringstatechange', handler)
    })
}
// Chrome/Edge 使用 WebRTC 拉取后端处理后的实时视频。
const startWebRtcStream = async () => {
    if (webRtcStarting || !detectionRunning.value) {
        return
    }
    webRtcStarting = true
    const token = ++webRtcStartToken
    clearReconnect()
    streamTransport.value = 'webrtc';
    modifyStreamAlert(false,t('message.messagetext.webrtcconnnecting'))

    try {
        closePeerConnection()
        pc = new RTCPeerConnection({iceServers: buildIceServers()})
        pc.addTransceiver('video', { direction: 'recvonly' })
        pc.ontrack = (event) => {
            const [remoteStream] = event.streams
            if (streamVideoRef.value && remoteStream) {
                streamVideoRef.value.srcObject = remoteStream
                streamVideoRef.value.onloadedmetadata = () => {
                    modifyStreamAlert(true,'');
                    clearReconnect();

                }
            }
        }

        pc.onconnectionstatechange = () => {
            console.log('WebRTC connectionState:', pc.connectionState)  
            if (!pc) {
                return
            }
            if (pc.connectionState === 'connected') {
                modifyStreamAlert(true,'');
                clearReconnect();
                return
            }
            if (pc.connectionState === 'failed' || pc.connectionState === 'closed' || pc.connectionState === 'disconnected') {
                handleWebRtcError()
            }
        }

        pc.oniceconnectionstatechange = () => {
            if (!pc) {
                return
            }
            if (pc.iceConnectionState === 'failed') {
                modifyStreamAlert(null,t('message.messagetext.webrtcStreamError'),true)
            }
        }

        const offer = await pc.createOffer()
        if (manuallyStopped || !detectionActive.value || token !== webRtcStartToken || !pc) {
            return
        }
        await pc.setLocalDescription(offer)
        await waitForIceGatheringComplete(pc)
        if (manuallyStopped || !detectionActive.value || token !== webRtcStartToken || !pc) {
            return
        }

        const response = await fetch(api.webRTcOfferUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sdp: pc.localDescription?.sdp,
                type: pc.localDescription?.type,
            })
        })

        if (!response.ok) {
            throw new Error(`WebRTC 信令失败: HTTP ${response.status}`)
        }
        if (manuallyStopped || !detectionActive.value || token !== webRtcStartToken || !pc) {
            return
        }

        const answer = await response.json()
        if (manuallyStopped || !detectionActive.value || token !== webRtcStartToken || !pc) {
            return
        }
        await pc.setRemoteDescription(new RTCSessionDescription(answer))
    } catch (err) {
        if (manuallyStopped || !detectionActive.value || token !== webRtcStartToken) {
            return
        }
        console.warn('启动 WebRTC 视频流失败:', err)
        handleWebRtcError()
    } finally {
        if (token === webRtcStartToken) {
            webRtcStarting = false
        }
    }
}

const startClientStreams = () => {
    manuallyStopped = false
    clearReconnect()
    clearResultReconnect()
    const isFirefox = /firefox/i.test(window.navigator.userAgent) // 当前浏览器是否是 Firefox。
    const preferMjpegForFirefox = String(import.meta.env.VITE_WEBRTC_PREFER_MJPEG_FIREFOX || 'true').toLowerCase() === 'true' // Firefox 是否优先使用 MJPEG 兜底流。
    if (isFirefox && preferMjpegForFirefox) {
        startMjpegStream()
    } else {
        startWebRtcStream()
    }
    connectResultSocket()
}

const stopStream = () => {
    manuallyStopped = true
    // detectionRunning.value = false
    // detectionInitialized.value = false
    webRtcStartToken += 1
    webRtcStarting = false
    clearReconnect()
    closePeerConnection()
    stopServerStream();
    modifyStreamAlert(false,'')
}

const stopClientStreams = (message = t('message.messagetext.stopedDetection')) => {
    stopStream()
    closeResultSocket();
    modifyStreamAlert(null,message,true)
}

/**
 * *********************************************************
 * End 视频流与结果通道逻辑
 * *********************************************************
 */


/**
 * *********************************************************
 * Start 检测控制按钮接口逻辑
 * 这里负责开始、暂停、复位、刷新检测状态等按钮触发的后端 API 调用。
 * *********************************************************
 */
const refreshDetectionStatus = async () => {
    appStore.setLoading(true);
    api.statusDetection().then((res)=>{
        const resData = res.data;
        if (resData.running) {
            startClientStreams()
            return
        };
        modifyStreamAlert(false,t('message.messagetext.closedDetection'))
    }).catch((err)=>{
        modifyStreamAlert(false, err.message || t('message.messagetext.backendServerIssue'));
        MesAlertWTitle('error', t('message.error'), t('message.messagetext.backendServerIssue'), err.message, 'OK')
    }).finally(()=>{
        appStore.setLoading(false);
    })
}

const handleStartDetection = async () => {
    if(!cameraName.value || cameraName.value === t('displaytext.noconfigcamera')) {
        MesAlertWTitle('warning', t('message.warning'), t('message.messagetext.failedstart'), t('message.messagetext.pleaseConfigureCamera'), 'OK')
        return
    }
    appStore.setLoading(true);
    api.startDetection({"camera_name": cameraName.value,"project_name":sopConfigrationData.value.model}).then((res)=>{
        const resData = res.data;
        if(!resData.status){
            streamConnected.value = false;
            MesAlertWTitle('error', t('message.error'), t('message.messagetext.failedstart'), resData.msg || t('message.messagetext.faildStartDetection'), 'OK')
            return;
        };
        applyRuntimeStatus(resData.data);
        // 点击开始成功后，立即进入第一道工序
        detectionResult.value.step = 1;
        processSteps.value.forEach((step, index) => {
            step.current = 0
            step.reason = ''
            step.status = index === 0 ? 'process' : 'wait'
        });
        startClientStreams()
    }).catch((err)=>{
        modifyStreamAlert(false, err.message || t('message.messagetext.faildStartDetection'));
        MesAlertWTitle('error', t('message.error'), t('message.messagetext.failedstart'), err.message || t('message.messagetext.faildStartDetection'), 'OK')
    }).finally(()=>{
        appStore.setLoading(false);
    })
}
const handlePauseDetection = async () => {
    appStore.setLoading(true);
    api.pauseDetection().then((res)=>{
        const resData = res.data;
        if(!resData.status){
            modifyStreamAlert(false, resData.msg || t('message.messagetext.faildPauseDetection'));
            MesAlertWTitle('error', t('message.error'), t('message.messagetext.faildPauseDetection'), resData.msg || t('message.messagetext.faildPauseDetection'), 'OK')
            return;
        };
        applyRuntimeStatus(resData.data);
         modifyStreamAlert(null, t('message.messagetext.successPauseDetection'), true)
    }).catch((err)=>{
        modifyStreamAlert(false, err.message || t('message.messagetext.faildPauseDetection'));
        MesAlertWTitle('error', t('message.error'), t('message.messagetext.faildPauseDetection'), err.message || t('message.messagetext.faildPauseDetection'), 'OK')
    }).finally(()=>{
        appStore.setLoading(false);
    })
};
const handleResumeDetection = async () => {
    appStore.setLoading(true);
    api.resumeDetection().then((res)=>{
        const resData = res.data;
        if(!resData.status){
            modifyStreamAlert(false, resData.msg || t('message.messagetext.faildResumeDetection'));
            MesAlertWTitle('error', t('message.error'), t('message.messagetext.faildResumeDetection'), resData.msg || t('message.messagetext.faildResumeDetection'), 'OK')
            return;
        };
        applyRuntimeStatus(resData.data);
        // 正常情况下暂停没有断流。
        // 如果暂停期间恰好发生了断流，则这里主动恢复。
        if (!streamConnected.value) {startClientStreams()};
        modifyStreamAlert(true,'')
    }).catch((err)=>{
        modifyStreamAlert(false, err.message || t('message.messagetext.faildResumeDetection'));
        MesAlertWTitle('error', t('message.error'), t('message.messagetext.faildResumeDetection'), err.message || t('message.messagetext.faildResumeDetection'), 'OK')
    }).finally(()=>{
        appStore.setLoading(false);
    })
};
const handleStopDetection = async () => {
    appStore.setLoading(true);
    api.stopDetection().then((res)=>{
        const resData = res.data;
        if(!resData.status){
            modifyStreamAlert(false, resData.msg || t('message.messagetext.faildStopDetection'));
            MesAlertWTitle('error', t('message.error'), t('message.messagetext.faildStopDetection'), resData.msg || t('message.messagetext.faildStopDetection'), 'OK')
            return;
        };
        applyRuntimeStatus(resData.data);
        stopClientStreams(t('message.messagetext.stopedDetection'));
    }).catch((err)=>{
        modifyStreamAlert(false, err.message || t('message.messagetext.faildStopDetection'));
        MesAlertWTitle('error', t('message.error'), t('message.messagetext.faildStopDetection'), err.message || t('message.messagetext.faildStopDetection'), 'OK')
    }).finally(()=>{
        appStore.setLoading(false);
    })
}

const handleCloseDetection = async () => {
    appStore.setLoading(true);
    api.closeDetection().then((res)=>{
        const resData = res.data;
        if(!resData.status){
            modifyStreamAlert(false, resData.msg || t('message.messagetext.faildCloseDetection'));
            MesAlertWTitle('error', t('message.error'), t('message.messagetext.faildCloseDetection'), resData.msg || t('message.messagetext.faildCloseDetection'), 'OK')
            return;
        };
        applyRuntimeStatus(resData.data);
        resetProcessSteps();
        stopClientStreams(t('message.messagetext.closedDetection'));
    }).catch((err)=>{
        modifyStreamAlert(false, err.message || t('message.messagetext.faildCloseDetection'));
        MesAlertWTitle('error', t('message.error'), t('message.messagetext.faildCloseDetection'), err.message || t('message.messagetext.faildCloseDetection'), 'OK')
    }).finally(()=>{
        appStore.setLoading(false);
    })
}
/**
 * *********************************************************
 * End 检测控制按钮接口逻辑
 * *********************************************************
 */


/**
 * *********************************************************
 * Start 生命周期与监听逻辑
 * 这里统一放页面初始化、离开页面清理、hint 内容变化监听。
 * *********************************************************
 */
onMounted(async() => {
    await getSopConfigration();
    updateFooterHintOverflow()
    window.addEventListener('resize', updateFooterHintOverflow)
    // manuallyStopped = false
    timeoutTicker = window.setInterval(() => {
        timeoutNow.value = Date.now()
    }, 1000)
    await refreshDetectionStatus();
    
})

onBeforeUnmount(() => {
    window.removeEventListener('resize', updateFooterHintOverflow);
    if (criticalAlertTimer) {
        clearTimeout(criticalAlertTimer)
        criticalAlertTimer = null
    }
    stopStream()
    closeResultSocket();
    if (timeoutTicker) {
        clearInterval(timeoutTicker)
        timeoutTicker = null
    }
})
watch(() => currentStep.value?.hint, updateFooterHintOverflow)
watch(() => currentStep.value?.name, updateFooterHintOverflow)
const modifyStreamAlert = (_streamConnected=false, _streamErrorMessage='',_onlyMessage=false) => {
    if(!_onlyMessage){
        streamConnected.value = _streamConnected;
    }
    streamErrorMessage.value = _streamErrorMessage;
}
/**
 * *********************************************************
 * End 生命周期与监听逻辑
 * *********************************************************
 */
const test = ()=>{
    alerts.value.unshift({
        id: `sop-${Date.now()}`,
        level: 'error',
        code: 'SOP_NG',
        message: '异常: 当前工序应安装 A，检测到 B 进入 C',
        confirmed: false,
    })
    const isSopAlert = (item) => String(item.code || '').startsWith('SOP_');
    console.log("isSOPAlert",isSopAlert(alerts.value[0]));
    console.log("alerts.value",alerts.value)
    alerts.value = alerts.value.filter((item) => !isSopAlert(item));
    console.log("alerts.value",alerts.value)
}
</script>
<style scoped lang="scss">
.layout-container {
    height: 100%;
    width: 100%;
    
    .layout-container {
        height: 100%;
        padding: 10px;
    }
}

.main-pane {
    padding: 0;
    background: var(--bs-bgcolor);
}

.camera-layout {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;

    .camera-item-top {
        height: 1%;
    }

    .camera-item-header {
        height: 9%;
        border-bottom: 1px solid #d8dce5;
        padding: 0 10px;

        .header-left {
            max-width: 85%;
            gap: 10px;
            overflow: hidden;
        }
        .header-timeout {
            flex: 0 0 auto;
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 5px;
            width: 170px;
            min-width: 170px;
            height: 46px;

            .header-timeout-text {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                line-height: 1;
                white-space: nowrap;

                span {
                    font-size: 11px;
                    color: var(--el-text-color-secondary);
                }

                strong {
                    font-size: 12px;
                    font-weight: 600;
                    color: var(--el-text-color-primary);
                }
            }

            .header-timeout-progress {
                width: 100%;

                :deep(.el-progress-bar__outer) {
                    background-color: var(--el-fill-color);
                }
            }
        }
        .header-right {
            border-left: 1px solid #000;
            // flex: 1;
            // min-width: 50px;
            min-width: 180px;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 8px;
            padding-left: 10px;

        }
    }

    .camera-item-body {
        height: 90%;
        width: 100%;
        position: relative;
        overflow: hidden;

        &::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-image: url(@/assets/img/FAIVS.jpg);
            background-size: 100% 100%;
            background-repeat: no-repeat;
            opacity:0.1;
            z-index: 0;
        }

        * {
            // position: relative;
            z-index: 1;
        }

        .video-stream {
            z-index:0;
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 100%;
            height: 100%;
            object-fit: contain;
        }

        .reconnecting-message {
            position: absolute;
            top: 50%;
            left: 50%;
            width: 300px;
            max-width: 70%;
            min-height: 80px;
            background: var(--bs-alert-error-bgcolor);
            // color: #fff;
            // border-radius: 8px;
            transform: translate(-50%, -50%);
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 12px;
            z-index:1;
        }

        

        .current-step-overlay {
            position: absolute;
            left: 12px;
            bottom: 12px;
            width: 360px;
            max-width: calc(100% - 24px);
            padding: 10px 12px;
            border-radius: 8px;
            background: rgba(20, 25, 32, 0.72);
            color: #fff;

            .overlay-title {
                font-size: 12px;
                color: #d1d8e0;
                margin-bottom: 4px;
            }

            .overlay-name {
                font-size: 22px;
                font-weight: 700;
                line-height: 1.2;
            }

            .overlay-meta {
                margin-top: 6px;
                font-size: 13px;
                color: #d1d8e0;
            }

        }
    }
}
.process-steps.el-steps--vertical{
    :deep(.el-step__icon){
        height: 24px !important;
        width: 24px !important;
    }
    :deep(.el-step__line){
        left: 12px !important;
    }
    :deep(.el-step__main){
        padding-left: 8px !important;
    }
}
.right-side {
    padding-left: 10px;
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    gap: 10px;
    box-sizing: border-box;

    .side-card {
        background: var(--bs-bgcolor);
        min-height: 0;
        margin-bottom: 0;
        border-radius: 0;
        display: flex;
        flex-direction: column;
    }

    .side-card-current {
        flex: 0 0 18%;
        :deep(.el-card__body) {
            overflow: hidden;
        }
    }

    .side-card-steps {
        flex: 1 1 38%;
        
    }
    
    .side-card-alerts,
    .side-card-events {
        flex: 0 1 20%;
    }

    :deep(.el-card__header) {
        flex: 0 0 auto;
        padding: 2px 10px;
        color: #000;
    }

    :deep(.el-card__body) {
        flex: 1;
        min-height: 0;
        padding: 10px;
        overflow-y: auto;
        overflow-x: hidden;
    }
}

.current-section {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;

    .current-name {
        font-size: 22px;
        font-weight: 700;
        line-height: 1.1;
        margin-bottom: 6px;
        color: #1d2d3d;
        display: -webkit-box;
        line-clamp: 2;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }

    .current-desc {
        font-size: 13px;
        color: #606266;
        margin-bottom: 8px;
        line-height: 1.4;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .current-error-alert {
        margin-bottom: 8px;
    }

    .current-progress-row {
        display: flex;
        align-items: center;
        gap: 6px;
        min-height: 28px;
        color: #fff;

        .current-metrics {
            flex: 0 0 auto;
            display: flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
        }

        .current-metric {
            min-width: 50px;
            height: 26px;
            // border-radius: 4px;
            padding: 0 6px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 4px;
            

            span {
                font-size: 12px;
                // color: #606266;
            }

            strong {
                font-size: 18px;
                line-height: 1;
                // color: #1d2d3d;
            }
        }

        .current-metric-target {
            background: var(--bs-primary-color);
        }

        .current-metric-current {
            background: var(--bs-turquoise-color);
        }

        .current-progress-meter {
            flex: 1;
            min-width: 0;
            height: 26px;
            border: 1px solid #e4e7ed;
            padding: 0 6px;
            display: flex;
            align-items: center;
            gap: 6px;

            .current-progress-label {
                flex: 0 0 auto;
                font-size: 12px;
                color: #606266;
            }

            :deep(.el-progress) {
                flex: 1;
                min-width: 0;
            }

            strong {
                flex: 0 0 42px;
                text-align: right;
                font-size: 13px;
                color: #1d2d3d;
            }
        }
    }
}

.alert-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.alert-item {
    // border-radius: 6px;
    border: 1px solid #e6e8eb;
    // padding: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;

    .alert-line {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
    }

    .alert-message {
        font-size: 13px;
        color: #2f3540;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
}

.alert-warning {
    background: var(--bs-alert-warning-bgcolor);
}

.alert-error {
    background: var(--bs-alert-error-bgcolor);
}

.events-section {
    height: 100%;
    min-height: 0;

    .event-list {
        height: 100%;
        min-height: 0;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .event-item {
        padding: 6px 8px;
        display: grid;
        grid-template-columns: 62px 82px 1fr;
        align-items: center;
        gap: 8px;
        font-size: 12px;

        .event-time {
            color: #606266;
        }

        .event-step {
            color: #3f4a56;
        }

        .event-text {
            color: #2f3540;
        }
    }

    .event-info {
        background: var(--bs-alert-info-bgcolor);
    }

    .event-warning {
        background: var(--bs-alert-warning-bgcolor);
    }

    .event-error {
        background: var(--bs-alert-error-bgcolor);
    }
}

.empty-state {
    font-size: 13px;
    color: #909399;
}

.action-footer {
    min-height: 80px;
    border-top: 1px solid #d8dce5;
    
    background: var(--bs-bgcolor);
    padding: 8px 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    overflow: hidden;

    .footer-progress {
        flex: 0 0 76px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 2px;

        .footer-title {
            display: block;
            font-size: 13px;
            color: #3a4a5a;
            line-height: 1;
        }
    }

    .footer-current {
        flex: 1;
        min-width: 0;
        align-self: stretch;
        display: flex;
        flex-direction: column;
        justify-content: center;
        border-left: 1px solid #e6e8eb;
        padding-left: 14px;

        .footer-current-title {
            font-size: 14px;
            color: #606266;
            line-height: 1.2;
            margin-bottom: 4px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .footer-current-hint {
            color: #1d2d3d;
            font-size: 22px;
            font-weight: 700;
            line-height: 1.25;
            height: 55px;
            overflow: hidden;

            .footer-current-hint-track {
                display: flex;
                flex-direction: column;
                width: 100%;

                .footer-current-hint-text {
                    flex: 0 0 auto;
                    width: 100%;
                    white-space: normal;
                    word-break: break-all;
                }

                .footer-current-hint-end {
                    color: #909399;
                    font-size: 16px;
                    font-weight: 500;
                    line-height: 1.6;
                    text-align: center;
                }

                &.is-scrolling {
                    animation: footer-hint-marquee 16s linear infinite;

                    .footer-current-hint-text {
                        padding-bottom: 24px;
                    }
                }
            }
        }
    }

    .footer-actions {
        flex: 0 0 auto;
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
    }
}

@keyframes footer-hint-marquee {
    0% {
        transform: translateY(0);
    }

    14% {
        transform: translateY(0);
    }

    82% {
        transform: translateY(-50%);
    }

    100% {
        transform: translateY(-50%);
    }
}

@media (max-width: 1280px) {
    .right-side {
        width: 300px !important;
    }

    .camera-layout .camera-item-header .header-left {
        max-width: 64%;
    }

    .camera-layout .camera-item-header .header-right {
        max-width: 36%;
    }
}
</style>
