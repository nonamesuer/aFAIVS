<template>
    <div class="layout-container">
        <el-container class="layout-container">
            <el-container>
                <el-main class="main-pane">
                    <div class="camera-layout">
                        <div class="camera-item-top" :class="{ 'is-connected': stream.connected }"/>

                        <div class="camera-item-header flex-center">
                            <div class="header-left flex-center">
                                <div class="text-auto-hidden">{{ cameraName }}</div>
                                <el-divider direction="vertical" />

                                <div class="text-auto-hidden">
                                    {{ sopConfiguration.model || '' }}
                                </div>
                                <el-divider direction="vertical" />

                                <div class="text-auto-hidden">
                                    {{ sopConfiguration.confidence || 0 }}
                                </div>
                                <el-divider direction="vertical" />

                                <el-tag
                                    effect="dark"
                                    size="small"
                                    :type="runtimeStatus.tagType"
                                >
                                    {{ runtimeStatus.label }}
                                </el-tag>

                                <el-divider direction="vertical" />

                                <el-tag
                                    effect="dark"
                                    :type="stream.transport === 'webrtc' ? 'success' : 'warning'"
                                >
                                    {{ stream.transport === 'webrtc' ? 'WebRTC' : 'MJPEG' }}
                                </el-tag>

                                <template v-if="timeoutInfo.visible">
                                    <el-divider direction="vertical" />
                                    <div class="header-timeout">
                                        <el-progress
                                            class="header-timeout-progress"
                                            :percentage="timeoutInfo.percentage"
                                            :stroke-width="7"
                                            :format="formatTimeoutProgress"
                                        />
                                    </div>
                                </template>
                            </div>

                            <div class="header-right">{{ $t('interacting.result') }}</div>
                        </div>

                        <div class="camera-item-body">
                            <div v-if="!stream.connected" class="reconnecting-message">
                                {{
                                    stream.errorMessage ||
                                    t('message.messagetext.webrtcStreamError')
                                }}
                            </div>

                            <el-alert
                                v-if="criticalAlerts.length"
                                :closable="true"
                                show-icon
                                type="error"
                                effect="dark"
                                :title="`${criticalAlerts[0].code} ${criticalAlerts[0].message}`"
                                @close="clearCriticalAlert"
                            />

                            <video
                                v-if="runtime.active && stream.transport === 'webrtc'"
                                ref="streamVideoRef"
                                class="video-stream"
                                autoplay
                                playsinline
                                muted
                            />

                            <img
                                v-else-if="runtime.active"
                                ref="streamImageRef"
                                class="video-stream"
                                :src="mjpegUrl"
                                alt="server-stream"
                                @load="setStreamState(true)"
                                @error="setStreamState(false, t('message.messagetext.mjpegStreamError'))"
                            />

                            <div v-if="currentStep" class="current-step-overlay">
                                <div class="overlay-title">{{ $t('displaytext.currentprocess') }}</div>
                                <div class="overlay-name text-auto-hidden">
                                    {{ currentStep.name }}
                                </div>
                                <div class="overlay-meta">
                                    {{ $t('displaytext.target') }} {{ currentStep.target }}
                                    |
                                    {{ $t('displaytext.current') }} {{ currentStep.current }}
                                    |
                                    {{ getStepStatusLabel(currentStep.status) }}
                                </div>
                                <div
                                    v-if="currentStep.reason"
                                    class="overlay-reason text-auto-hidden"
                                >
                                    {{ currentStep.reason }}
                                </div>
                            </div>
                        </div>
                    </div>
                </el-main>

                <el-footer class="action-footer">
                    <div class="footer-progress" :title="t('displaytext.overallprogress')">
                        <el-progress
                            type="circle"
                            color="var(--bs-primary-color)"
                            :percentage="overallProgress"
                            :width="58"
                            :stroke-width="6"
                        />
                        <span class="footer-title" >{{ $t('displaytext.oap') }}</span>
                    </div>

                    <div v-if="currentStep" class="footer-current">
                        <div class="footer-current-title">
                            {{ currentStep.name }}
                        </div>

                        <div
                            ref="footerHintRef"
                            class="footer-current-hint"
                            :title="currentStep.hint || $t('displaytext.waitingforprocesshint')"
                        >
                            <div
                                ref="footerHintTextRef"
                                class="footer-current-hint-track"
                                :class="{ 'is-scrolling': footerHintOverflow }"
                            >
                                <div class="footer-current-hint-text">
                                    {{ currentStep.hint || $t('displaytext.waitingforprocesshint') }}
                                    <div
                                        v-if="footerHintOverflow"
                                        class="footer-current-hint-end"
                                    >
                                        -- {{ $t('displaytext.endhint') }} --
                                    </div>
                                </div>

                                <div
                                    v-if="footerHintOverflow"
                                    class="footer-current-hint-text"
                                    aria-hidden="true"
                                >
                                    {{ currentStep.hint || $t('displaytext.waitingforprocesshint') }}
                                    <div class="footer-current-hint-end">
                                        -- {{ $t('displaytext.endhint') }} --
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="footer-actions">
                        <el-button v-if="!runtime.active" type="primary" :icon="VideoPlay" @click="handleStartDetection">{{ $t('button.start') }}</el-button>

                        <el-button v-if="runtime.running" type="primary"  plain :icon="VideoPause" @click="handlePauseDetection">
                            {{ $t('button.pause') }}
                        </el-button>

                        <el-button v-if="runtime.paused" type="primary" :icon="VideoPlay" @click="handleResumeDetection">
                            {{ $t('button.resume') }}
                        </el-button>

                        <el-button v-if="runtime.active" type="warning" :icon="RefreshLeft" @click="handleResetDetection">
                            {{ $t('button._reset') }}
                        </el-button>

                        <el-button type="danger" :icon="Stopwatch" @click="handleStopDetection">{{ $t('button.stop') }}</el-button>
                    </div>
                </el-footer>
            </el-container>

            <el-aside width="340px" class="right-side">
                <el-card class="side-card side-card-current" shadow="never">
                    <template #header>
                        <div>{{ $t('displaytext.currentprocess') }}</div>
                    </template>

                    <div v-if="currentStep" class="current-section">
                        <div class="current-name">{{ currentStep.name }}</div>
                        <div class="current-desc">{{ currentStep.hint }}</div>

                        <div class="current-progress-row">
                            <div class="current-metrics">
                                <div class="current-metric current-metric-target">
                                    <span>{{ $t('displaytext.target') }}</span>
                                    <strong>{{ currentStep.target }}</strong>
                                </div>

                                <div class="current-metric current-metric-current">
                                    <span>{{ $t('displaytext.current') }}</span>
                                    <strong>{{ currentStep.current }}</strong>
                                </div>
                            </div>

                            <div class="current-progress-meter">
                                <span class="current-progress-label">{{ $t('displaytext.progress') }}</span>
                                <el-progress
                                    :percentage="currentStepProgress"
                                    :stroke-width="9"
                                    :show-text="false"
                                />
                                <strong>{{ currentStepProgress }}%</strong>
                            </div>
                        </div>
                    </div>
                </el-card>

                <el-card class="side-card side-card-steps" shadow="never">
                    <template #header>
                        <div>
                            {{ $t('displaytext.processstep') }}：
                            <span>{{ okCount }}/{{ processSteps.length }}</span>
                        </div>
                    </template>

                    <div v-if="processSteps.length">
                        <el-steps
                            direction="vertical"
                            class="bs-step-normal process-steps"
                            :active="currentStepIndex"
                            finish-status="success"
                        >
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
                        <div style="color: red">
                            {{ $t('displaytext.errorsandalerts') }}：<span>{{ ngCount }}</span>
                        </div>
                    </template>

                    <div>
                        <div v-if="!unconfirmedAlerts.length" class="empty-state">
                            {{ $t('displaytext.noalert') }}
                        </div>

                        <div v-else class="alert-list">
                            <div
                                v-for="alert in unconfirmedAlerts"
                                :key="alert.id"
                                :title="`${alert.code} | ${alert.message}`"
                                class="alert-item"
                                :class="`alert-${alert.level}`"
                            >
                                <div class="alert-line">
                                    <el-tag size="small" :type="getTagType(alert.level)">
                                        {{ alert.code }}
                                    </el-tag>
                                    <span class="alert-message">
                                        {{ alert.message }}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </el-card>

                <el-card class="side-card side-card-events" shadow="never">
                    <template #header>
                        <div>{{ $t('displaytext.realtimeevent') }}</div>
                    </template>

                    <div class="events-section">
                        <div class="event-list">
                            <div
                                v-for="event in events"
                                :key="event.id"
                                :title="`${event.time} | ${event.step} | ${event.text}`"
                                class="event-item"
                                :class="`event-${event.level}`"
                            >
                                <span class="event-time">{{ event.time }}</span>
                                <span class="event-step text-auto-hidden">
                                    {{ event.step }}
                                </span>
                                <span class="event-text text-auto-hidden">
                                    {{ event.text }}
                                </span>
                            </div>
                        </div>
                    </div>
                </el-card>
            </el-aside>
        </el-container>
    </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount,onMounted,reactive,ref, watch} from 'vue'
import { VideoPause, VideoPlay,RefreshLeft,Stopwatch } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import api from '@/api/index'
import { MesAlertWTitle,MesConfirmWTitle } from '@/assets/js/secondpk'
import { useAppStore } from '@/stores/store'

const appStore = useAppStore()
const { t } = useI18n()

const MAX_EVENT_COUNT = 50
const MAX_ALERT_COUNT = 30
const RECONNECT_DELAY_MS = 3000
const TIMEOUT_TICK_MS = 1000

const createEmptyDetectionResult = () => ({
    step: null,
    gesture: 'idle',
    bbox: [],
    detections: [],
    score: 0,
    ok_count: 0,
    ng_count: 0,
    updated_at: 0,
    sop: null,
})

const runtime = reactive({
    initialized: false,
    running: false,
    paused: false,
    active: false,
})

const stream = reactive({
    connected: false,
    transport: 'webrtc',
    errorMessage: t('message.messagetext.closedDetection'),
})

const cameraName = ref(t('displaytext.noconfigcamera'))
const sopConfiguration = ref({})
const detectionResult = ref(createEmptyDetectionResult())
const processSteps = ref([])
const alerts = ref([])
const events = ref([])
const criticalAlerts = ref([])

const streamVideoRef = ref(null)
const streamImageRef = ref(null)
const footerHintRef = ref(null)
const footerHintTextRef = ref(null)
const footerHintOverflow = ref(false)
const timeoutNow = ref(Date.now())

const mjpegUrl = ref(`${api.mjpegBaseUrl}?ts=${Date.now()}`)

let peerConnection = null
let resultSocket = null
let reconnectTimer = null
let resultReconnectTimer = null
let criticalAlertTimer = null
let timeoutTicker = null
let manuallyStopped = false
let webRtcStarting = false
let webRtcStartToken = 0
let lastSopEventKey = ''
let lastCriticalAlertKey = ''

const okCount = computed(() => Number(detectionResult.value.ok_count || 0))
const ngCount = computed(() => Number(detectionResult.value.ng_count || 0))
const currentSop = computed(() => detectionResult.value.sop || null)
const currentRuntimeStep = computed(() => currentSop.value?.current_step || null)
const unconfirmedAlerts = computed(() =>
    alerts.value.filter((alert) => !alert.confirmed),
)

const runtimeStatus = computed(() => {
    if (runtime.paused) return { label: t('displaytext.paused'), tagType: 'warning' };
    if (runtime.running) return { label: t('displaytext.running'), tagType: 'success' };
    return { label: t('displaytext.nostarted'), tagType: 'info' };
})

const currentStepIndex = computed(() => {
    if (!runtime.active || !processSteps.value.length) {
        return -1
    }

    const indexFromSop = Number(currentSop.value?.progress?.current_index)
    if (Number.isFinite(indexFromSop)) {
        return clamp(indexFromSop, 0, processSteps.value.length - 1)
    }

    return processSteps.value.findIndex((step) => step.status === 'process')
})

const currentStep = computed(() => {
    if (currentStepIndex.value < 0) {
        return null
    }
    return processSteps.value[currentStepIndex.value] || null
})

const currentStepProgress = computed(() =>
    calculatePercentage(currentStep.value?.current, currentStep.value?.target),
)

const overallProgress = computed(() => {
    const progress = currentSop.value?.progress
    if (Number(progress?.total) > 0) {
        return calculatePercentage(progress.done, progress.total)
    }

    const total = processSteps.value.length
    if (!total) {
        return 0
    }

    const completedCount = processSteps.value.filter(
        (step) => step.status === 'success',
    ).length

    const activeRatio = currentStep.value
        ? clamp(
              Number(currentStep.value.current || 0) /
                  Math.max(1, Number(currentStep.value.target || 1)),
              0,
              1,
          )
        : 0

    return roundPercentage(((completedCount + activeRatio) / total) * 100)
})

const timeoutInfo = computed(() => {
    const sop = currentSop.value
    const step = currentRuntimeStep.value
    const total = normalizePositiveNumber(step?.timeout)

    if (
        !runtime.active ||
        !sop ||
        !step ||
        !total ||
        sop.state === 'completed' ||
        !['active', 'failed'].includes(step.state)
    ) {
        return {
            visible: false,
            total: 0,
            elapsed: 0,
            remaining: 0,
            percentage: 0,
        }
    }

    const serverElapsed = Math.max(0, Number(step.elapsed || 0))
    const shouldAdvance =
        sop.state === 'running' &&
        runtime.running &&
        !runtime.paused &&
        step.state === 'active'

    let elapsed = serverElapsed
    if (shouldAdvance) {
        const updatedAtMs = Number(sop.updated_at || 0) * 1000
        if (updatedAtMs > 0) {
            elapsed += Math.max(0, (timeoutNow.value - updatedAtMs) / 1000)
        }
    }

    elapsed = clamp(elapsed, 0, total)

    return {
        visible: true,
        total,
        elapsed,
        remaining: Math.max(0, total - elapsed),
        percentage: calculatePercentage(elapsed, total),
    }
})

function clamp(value, min, max) {
    return Math.min(max, Math.max(min, Number(value) || 0))
}

function roundPercentage(value) {
    return Number(clamp(value, 0, 100).toFixed(1))
}

function calculatePercentage(current, total) {
    const safeTotal = Number(total || 0)
    if (safeTotal <= 0) {
        return 0
    }
    return roundPercentage((Number(current || 0) / safeTotal) * 100)
}

function normalizePositiveNumber(value) {
    const number = Number(value || 0)
    return Number.isFinite(number) && number > 0 ? number : 0
}

function formatTimeoutDuration(seconds) {
    const safeSeconds = Math.max(0, Math.ceil(Number(seconds || 0)))
    if (safeSeconds < 60) {
        return `${safeSeconds}秒`
    }

    const minutes = Math.floor(safeSeconds / 60)
    const remainingSeconds = safeSeconds % 60
    return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`
}

function formatTimeoutProgress() {
    return `${formatTimeoutDuration(timeoutInfo.value.remaining)} / ${formatTimeoutDuration(timeoutInfo.value.total)}`
}

function setStreamState(connected, errorMessage = '', onlyMessage = false) {
    if (!onlyMessage) {
        stream.connected = Boolean(connected)
    }
    stream.errorMessage = errorMessage
}

function applyRuntimeStatus(payload = {}) {
    runtime.initialized = Boolean(payload.initialized)
    runtime.running = Boolean(payload.running)
    runtime.paused = Boolean(payload.paused)
    runtime.active = Boolean(payload.active)
}

function getTagType(level) {
    return {
        error: 'danger',
        warning: 'warning',
        info: 'info',
        success: 'success',
    }[level] || 'info'
}

function getStepStatusLabel(status) {
    return {
        success: '已完成',
        process: '进行中',
        error: '阻塞',
        wait: '未开始',
    }[status] || '未开始'
}

function getStepDescription(step = {}) {
    const base = `状态: ${getStepStatusLabel(step.status)} | 目标: ${step.target}`
    return step.reason ? `${base} | ${step.reason}` : base
}

function getNowTime() {
    return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

function getSopReasonText(reason = '') {
    if (!reason) {
        return '等待检测结果'
    }

    const wrongObjectMatch = reason.match(
        /^NG: Expected (.+), but (.+) entered (.+)$/,
    )
    if (wrongObjectMatch) {
        return `异常: 当前工序应安装 ${wrongObjectMatch[1]}，检测到 ${wrongObjectMatch[2]} 进入 ${wrongObjectMatch[3]}`
    }

    const replacements = [
        ['NG: ', '异常: '],
        ['Step timeout: ', '工序超时: '],
        ['Waiting for region ', '等待区域 '],
        ['Waiting for ', '等待目标 '],
    ]

    for (const [prefix, replacement] of replacements) {
        if (reason.startsWith(prefix)) {
            return reason.replace(prefix, replacement)
        }
    }

    if (reason.startsWith('Move ') && reason.includes(' into ')) {
        const [objectName, regionName] = reason
            .replace('Move ', '')
            .split(' into ')
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

function getSopAlertCode(reason = '') {
    if (reason.startsWith('Step timeout: ')) {
        return 'SOP_TIMEOUT'
    }
    if (reason.startsWith('NG: ')) {
        return 'SOP_NG'
    }
    return 'SOP_ERROR'
}

function normalizeStep(step = {}, index = 0, runtimeStep = false) {
    return {
        ...step,
        id: step.id ?? index + 1,
        name: step.name || `工序${index + 1}`,
        target: Number(step.target ?? 1),
        current: runtimeStep ? Number(step.matched_count ?? 0) : 0,
        status: runtimeStep ? mapSopStepStatus(step.state) : 'wait',
        hint: step.hint || '',
        reason: runtimeStep ? getSopReasonText(step.last_reason || '') : '',
    }
}

function mapSopStepStatus(state) {
    return {
        done: 'success',
        active: 'process',
        failed: 'error',
    }[state] || 'wait'
}

function resolveSopConfig(data = {}) {
    if (Array.isArray(data.steps)) {
        return data
    }

    return (
        Object.values(data).find(
            (item) => item && Array.isArray(item.steps),
        ) || {}
    )
}

function buildProcessSteps(steps = [], runtimeStep = false) {
    return steps.map((step, index) =>
        normalizeStep(step, index, runtimeStep),
    )
}

function resetProcessSteps() {
    detectionResult.value = createEmptyDetectionResult()
    processSteps.value = buildProcessSteps(sopConfiguration.value.steps || [])
    lastSopEventKey = ''
    lastCriticalAlertKey = ''
}

function syncProcessStepsFromSop(sop = {}) {
    const steps = Array.isArray(sop.steps) ? sop.steps : []
    if (!steps.length) {
        return
    }

    const failedReason =
        sop.state === 'failed' ? getSopReasonText(sop.reason || '') : ''

    processSteps.value = buildProcessSteps(steps, true).map((step, index) => {
        const source = steps[index]
        return {
            ...step,
            reason:
                source.state === 'failed'
                    ? failedReason
                    : getSopReasonText(source.last_reason || ''),
        }
    })
}

function buildEventKey(sop, step, rawReason) {
    return [
        sop.state,
        step?.state || '',
        step?.id || 'done',
        step?.pick_state || '',
        step?.matched_count || 0,
        step?.awaiting_cycle_reset || false,
        rawReason,
        sop.progress?.done || 0,
    ].join('|')
}

function appendSopEvent(sop = {}) {
    const step = sop.current_step
    const isFailed = sop.state === 'failed' || step?.state === 'failed'
    const rawReason = isFailed
        ? sop.reason || step?.last_reason || ''
        : step?.last_reason || sop.reason || ''

    if (!rawReason) return

    const eventKey = buildEventKey(sop, step, rawReason)
    if (eventKey === lastSopEventKey) return
    lastSopEventKey = eventKey
    events.value = [
        {
            id: `${Date.now()}-${Math.random()}`,
            time: getNowTime(),
            level: isFailed
                ? 'error'
                : sop.state === 'completed' || step?.state === 'done'
                  ? 'success'
                  : 'info',
            step: step?.name || 'SOP',
            text: getSopReasonText(rawReason),
        },
        ...events.value,
    ].slice(0, MAX_EVENT_COUNT)
}

function clearCriticalAlert() {
    criticalAlerts.value = []
    clearTimer('critical')
}

function showCriticalAlert(alert, duration = 5000) {
    criticalAlerts.value = [alert]
    clearTimer('critical')

    criticalAlertTimer = window.setTimeout(() => {
        criticalAlerts.value = []
        criticalAlertTimer = null
    }, duration)
}

function syncSopAlert(sop = {}) {
    const step = sop.current_step
    const isFailed = sop.state === 'failed' || step?.state === 'failed'

    if (!isFailed) {
        lastCriticalAlertKey = ''
        return
    }

    const rawReason =
        sop.reason || step?.last_reason || 'SOP 状态异常'
    const code = getSopAlertCode(rawReason)
    const alertKey = `${step?.id || 'sop'}|${code}|${rawReason}`

    if (alertKey === lastCriticalAlertKey) {
        return
    }

    lastCriticalAlertKey = alertKey

    const alert = {
        id: `sop-${Date.now()}-${Math.random()}`,
        level: 'error',
        code,
        message: getSopReasonText(rawReason),
        confirmed: false,
    }

    alerts.value = [alert, ...alerts.value].slice(0, MAX_ALERT_COUNT)
    showCriticalAlert(alert)
}

function applySopState(sop) {
    if (!sop || typeof sop !== 'object') {
        return
    }

    syncProcessStepsFromSop(sop)
    appendSopEvent(sop)
    syncSopAlert(sop)
}

function applyDetectionResult(payload = {}) {
    const previous = detectionResult.value

    detectionResult.value = {
        step: payload.step ?? previous.step,
        gesture: payload.gesture ?? previous.gesture,
        bbox: Array.isArray(payload.bbox) ? payload.bbox : [],
        detections: Array.isArray(payload.detections)
            ? payload.detections
            : [],
        score: Number(payload.score ?? previous.score),
        ok_count: Number(payload.ok_count ?? previous.ok_count),
        ng_count: Number(payload.ng_count ?? previous.ng_count),
        updated_at: Number(payload.updated_at ?? Date.now() / 1000),
        sop: payload.sop ?? previous.sop,
    }

    applySopState(detectionResult.value.sop)
}

async function updateFooterHintOverflow() {
    footerHintOverflow.value = false
    await nextTick()

    const container = footerHintRef.value
    const firstText = footerHintTextRef.value?.firstElementChild

    footerHintOverflow.value = Boolean(
        container &&
            firstText &&
            firstText.scrollHeight > container.clientHeight + 1,
    )
}

async function getSopConfiguration() {
    appStore.setLoading(true)

    try {
        const { data: response } = await api.getSopConfigration()
        if (!response.status) {
            MesAlertWTitle(
                'error',
                t('message.error'),
                t('message.messagetext.failed_get_config'),
                response.msg,
                'OK',
            )
            return
        }

        sopConfiguration.value = resolveSopConfig(response.data || {})
        cameraName.value =
            response.enableCamera || t('displaytext.noconfigcamera')
        processSteps.value = buildProcessSteps(
            sopConfiguration.value.steps || [],
        )
    } catch (error) {
        showApiError(
            t('message.messagetext.failed_get_config'),
            error,
        )
    } finally {
        appStore.setLoading(false)
    }
}

function buildIceServers() {
    const urls = String(
        import.meta.env.VITE_WEBRTC_ICE_URLS || '',
    )
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)

    if (!urls.length) {
        return [{ urls: ['stun:stun.l.google.com:19302'] }]
    }

    const username = String(
        import.meta.env.VITE_WEBRTC_ICE_USERNAME || '',
    ).trim()
    const credential = String(
        import.meta.env.VITE_WEBRTC_ICE_CREDENTIAL || '',
    ).trim()

    return username && credential
        ? [{ urls, username, credential }]
        : [{ urls }]
}

function clearTimer(type) {
    const timerMap = {
        reconnect: [reconnectTimer, (value) => (reconnectTimer = value)],
        result: [
            resultReconnectTimer,
            (value) => (resultReconnectTimer = value),
        ],
        critical: [
            criticalAlertTimer,
            (value) => (criticalAlertTimer = value),
        ],
    }

    const [timer, setter] = timerMap[type] || []
    if (timer) {
        clearTimeout(timer)
        setter(null)
    }
}

function closePeerConnection() {
    if (!peerConnection) {
        return
    }

    try {
        peerConnection.ontrack = null
        peerConnection.onconnectionstatechange = null
        peerConnection.oniceconnectionstatechange = null
        peerConnection.close()
    } catch (error) {
        console.warn('关闭 WebRTC 连接失败:', error)
    } finally {
        peerConnection = null
    }
}

function stopServerStream() {
    if (streamVideoRef.value) {
        streamVideoRef.value.srcObject = null
    }
    if (streamImageRef.value) {
        streamImageRef.value.src = ''
    }
}

function closeResultSocket() {
    clearTimer('result')

    if (!resultSocket) {
        return
    }

    try {
        resultSocket.onmessage = null
        resultSocket.onclose = null
        resultSocket.onerror = null
        resultSocket.close()
    } catch (error) {
        console.warn('关闭结果 WebSocket 失败:', error)
    } finally {
        resultSocket = null
    }
}

function scheduleResultSocketReconnect() {
    if (
        manuallyStopped ||
        !runtime.active ||
        resultReconnectTimer
    ) {
        return
    }

    resultReconnectTimer = window.setTimeout(() => {
        resultReconnectTimer = null
        connectResultSocket()
    }, RECONNECT_DELAY_MS)
}

function handleCameraStatus(payload = {}) {
    const status = payload.status

    if (status === 'reconnecting') {
        if (stream.transport === 'mjpeg') {
            mjpegUrl.value = ''
        }
        setStreamState(false, payload.message)
        return
    }

    if (status === 'reconnected') {
        if (stream.transport === 'mjpeg') {
            mjpegUrl.value = `${api.mjpegBaseUrl}?ts=${Date.now()}`
        }
        setStreamState(true)
        return
    }

    if (status === 'disconnected') {
        stopClientStreams(payload.message)
    }
}

function connectResultSocket() {
    closeResultSocket()

    if (!runtime.active) {
        return
    }

    try {
        resultSocket = new WebSocket(api.resultWsUrl)

        resultSocket.onmessage = ({ data }) => {
            try {
                const payload = JSON.parse(data)
                if (payload.ws_result) {
                    console.log('接收到检测结果:', payload.ws_result)
                    applyDetectionResult(payload.ws_result)
                } else if (payload.camera_status) {
                    handleCameraStatus(payload.camera_status)
                }
            } catch (error) {
                console.warn('解析检测结果失败:', error)
            }
        }

        resultSocket.onclose = (event) => {
            resultSocket = null

            if (event.code === 1000) {
                stopStream()
                setStreamState(
                    null,
                    t('message.messagetext.closedDetection'),
                    true,
                )
                return
            }

            if (!manuallyStopped && runtime.running) {
                scheduleResultSocketReconnect()
            }
        }

        resultSocket.onerror = scheduleResultSocketReconnect
    } catch (error) {
        console.warn('连接结果 WebSocket 失败:', error)
        scheduleResultSocketReconnect()
    }
}

function startMjpegStream() {
    closePeerConnection()
    clearTimer('reconnect')
    stream.transport = 'mjpeg'
    setStreamState(
        false,
        t('message.messagetext.mipegconnnecting'),
    )
    mjpegUrl.value = `${api.mjpegBaseUrl}?ts=${Date.now()}`
}

function scheduleWebRtcReconnect() {
    if (
        manuallyStopped ||
        !runtime.running ||
        reconnectTimer
    ) {
        return
    }

    const token = webRtcStartToken
    reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null

        if (
            manuallyStopped ||
            !runtime.running ||
            token !== webRtcStartToken
        ) {
            return
        }

        startWebRtcStream()
    }, RECONNECT_DELAY_MS)
}

function handleWebRtcError() {
    setStreamState(
        false,
        t('message.messagetext.webrtcStreamError'),
    )
    stopServerStream()
    scheduleWebRtcReconnect()
}

function waitForIceGatheringComplete(connection) {
    if (connection.iceGatheringState === 'complete') {
        return Promise.resolve()
    }

    return new Promise((resolve) => {
        const handler = () => {
            if (connection.iceGatheringState === 'complete') {
                connection.removeEventListener(
                    'icegatheringstatechange',
                    handler,
                )
                resolve()
            }
        }

        connection.addEventListener(
            'icegatheringstatechange',
            handler,
        )
    })
}

function isCurrentWebRtcAttempt(token) {
    return (
        !manuallyStopped &&
        runtime.active &&
        token === webRtcStartToken &&
        peerConnection
    )
}

async function startWebRtcStream() {
    if (webRtcStarting || !runtime.running) {
        return
    }

    webRtcStarting = true
    const token = ++webRtcStartToken

    clearTimer('reconnect')
    stream.transport = 'webrtc'
    setStreamState(
        false,
        t('message.messagetext.webrtcconnnecting'),
    )

    try {
        closePeerConnection()
        peerConnection = new RTCPeerConnection({
            iceServers: buildIceServers(),
        })

        peerConnection.addTransceiver('video', {
            direction: 'recvonly',
        })

        peerConnection.ontrack = ({ streams }) => {
            const [remoteStream] = streams
            if (streamVideoRef.value && remoteStream) {
                streamVideoRef.value.srcObject = remoteStream
                streamVideoRef.value.onloadedmetadata = () => {
                    setStreamState(true)
                    clearTimer('reconnect')
                }
            }
        }

        peerConnection.onconnectionstatechange = () => {
            const state = peerConnection?.connectionState
            if (state === 'connected') {
                setStreamState(true)
                clearTimer('reconnect')
            } else if (
                ['failed', 'closed', 'disconnected'].includes(state)
            ) {
                handleWebRtcError()
            }
        }

        peerConnection.oniceconnectionstatechange = () => {
            if (peerConnection?.iceConnectionState === 'failed') {
                setStreamState(
                    null,
                    t('message.messagetext.webrtcStreamError'),
                    true,
                )
            }
        }

        const offer = await peerConnection.createOffer()
        if (!isCurrentWebRtcAttempt(token)) return

        await peerConnection.setLocalDescription(offer)
        await waitForIceGatheringComplete(peerConnection)
        if (!isCurrentWebRtcAttempt(token)) return

        const response = await fetch(api.webRTcOfferUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sdp: peerConnection.localDescription?.sdp,
                type: peerConnection.localDescription?.type,
            }),
        })

        if (!response.ok) {
            throw new Error(
                `WebRTC 信令失败: HTTP ${response.status}`,
            )
        }

        if (!isCurrentWebRtcAttempt(token)) return

        const answer = await response.json()
        if (!isCurrentWebRtcAttempt(token)) return

        await peerConnection.setRemoteDescription(
            new RTCSessionDescription(answer),
        )
    } catch (error) {
        if (isCurrentWebRtcAttempt(token)) {
            console.warn('启动 WebRTC 视频流失败:', error)
            handleWebRtcError()
        }
    } finally {
        if (token === webRtcStartToken) {
            webRtcStarting = false
        }
    }
}

function startClientStreams() {
    manuallyStopped = false
    clearTimer('reconnect')
    clearTimer('result')

    const isFirefox = /firefox/i.test(
        window.navigator.userAgent,
    )
    const preferMjpeg =
        String(
            import.meta.env.VITE_WEBRTC_PREFER_MJPEG_FIREFOX ||
                'true',
        ).toLowerCase() === 'true'

    if (isFirefox && preferMjpeg) {
        startMjpegStream()
    } else {
        startWebRtcStream()
    }

    connectResultSocket()
}

function stopStream() {
    manuallyStopped = true
    webRtcStartToken += 1
    webRtcStarting = false
    clearTimer('reconnect')
    closePeerConnection()
    stopServerStream()
    setStreamState(false)
}

function stopClientStreams(
    message = t('message.messagetext.stopedDetection'),
) {
    stopStream()
    closeResultSocket()
    setStreamState(null, message, true)
}

function showApiError(title, error) {
    const message =
        error?.message ||
        t('message.messagetext.backendServerIssue')

    setStreamState(false, message)
    MesAlertWTitle(
        'error',
        t('message.error'),
        title,
        message,
        'OK',
    )
}

async function runDetectionAction({
    request,
    title,
    fallbackMessage,
    onSuccess,
}) {
    appStore.setLoading(true)

    try {
        const { data: response } = await request()
        if (!response.status) {
            const message = response.msg || fallbackMessage
            setStreamState(false, message)
            MesAlertWTitle('error',t('message.error'),title,message,'OK',)
            return false
        }

        applyRuntimeStatus(response.data || {})
        await onSuccess?.(response)
        return true
    } catch (error) {
        showApiError(title, error)
        return false
    } finally {
        appStore.setLoading(false)
    }
}

async function refreshDetectionStatus() {
    appStore.setLoading(true)
    try {
        const { data: response } = await api.statusDetection()
        applyRuntimeStatus(response)
        if (runtime.running || runtime.active) {
            startClientStreams()
        } else {
            setStreamState(false,t('message.messagetext.closedDetection'))
        }
    } catch (error) {
        showApiError(
            t('message.messagetext.backendServerIssue'),
            error,
        )
    } finally {
        appStore.setLoading(false)
    }
}
function clearDetectionHistory() {
    events.value = []
    alerts.value = []
    clearCriticalAlert()
    lastSopEventKey = ''
    lastCriticalAlertKey = ''
}
function resetStoppedUiState() {
    detectionResult.value = createEmptyDetectionResult()

    processSteps.value = buildProcessSteps(
        sopConfiguration.value.steps || [],
    )

    clearDetectionHistory()

    timeoutNow.value = Date.now()
    footerHintOverflow.value = false

    stream.transport = 'webrtc'
    mjpegUrl.value = `${api.mjpegBaseUrl}?ts=${Date.now()}`

    setStreamState(
        false,
        t('message.messagetext.stopedDetection'),
    )
}
async function handleStartDetection() {
    if (
        !cameraName.value ||
        cameraName.value === t('displaytext.noconfigcamera')
    ) {
        MesAlertWTitle(
            'warning',
            t('message.warning'),
            t('message.messagetext.failedstart'),
            t('message.messagetext.pleaseConfigureCamera'),
            'OK',
        )
        return
    }

    await runDetectionAction({
        request: () =>
            api.startDetection({
                camera_name: cameraName.value,
                project_name: sopConfiguration.value.model,
            }),
        title: t('message.messagetext.failedstart'),
        fallbackMessage: t(
            'message.messagetext.faildStartDetection',
        ),
        onSuccess: () => {
            detectionResult.value.step = 1
            processSteps.value = processSteps.value.map(
                (step, index) => ({
                    ...step,
                    current: 0,
                    reason: '',
                    status: index === 0 ? 'process' : 'wait',
                }),
            )
            startClientStreams()
        },
    })
}

async function handlePauseDetection() {
    await runDetectionAction({
        request: api.pauseDetection,
        title: t(
            'message.messagetext.faildPauseDetection',
        ),
        fallbackMessage: t(
            'message.messagetext.faildPauseDetection',
        ),
        onSuccess: () => {
            setStreamState(
                null,
                t(
                    'message.messagetext.successPauseDetection',
                ),
                true,
            )
        },
    })
}

async function handleResumeDetection() {
    await runDetectionAction({
        request: api.resumeDetection,
        title: t(
            'message.messagetext.faildResumeDetection',
        ),
        fallbackMessage: t(
            'message.messagetext.faildResumeDetection',
        ),
        onSuccess: () => {
            if (!stream.connected) {
                startClientStreams()
            }
            setStreamState(true)
        },
    })
}

async function handleResetDetection() {
    let clearHistory = false
    const result = await MesConfirmWTitle("warning",t('message.warning'), t('message.messagetext.confirmResetDetection'), t('message.messagetext.confirmResetDetectionDesc'), t('button.resetandclear'), t('button.onlyreset')).then(()=>{
        clearHistory = true
    }).catch(()=>{
        clearHistory = false
    }).finally(async () => {
        await runDetectionAction({
            request: api.resetDetection,
            title: t('message.messagetext.failedResetDetection'),
            fallbackMessage: t('message.messagetext.failedResetDetection'),
            onSuccess: (res) => {
                resetProcessSteps();
                if (clearHistory) {
                    clearDetectionHistory()
                }
                const result = res.data?.result;
                if(result){
                    applyDetectionResult(result)
                }else{
                    detectionResult.value = {
                        ...createEmptyDetectionResult(),
                        step: 1,
                    }

                    processSteps.value = buildProcessSteps(
                        sopConfiguration.value.steps || [],
                    ).map((step, index) => ({
                        ...step,
                        current: 0,
                        reason: '',
                        status: index === 0
                            ? 'process'
                            : 'wait',
                    }))
                }
                timeoutNow.value = Date.now();
                if (runtime.running && !stream.connected) {
                    startClientStreams()
                }
                if (runtime.paused) {
                    setStreamState(null,'检测已暂停，工序已复位到第一步',true,)
                }
            },
        })
    })
}
    
async function handleStopDetection() {
        await runDetectionAction({
        request: api.stopDetection,

        title: '停止失败',
        fallbackMessage: '无法停止检测运行时',

        onSuccess: () => {
            /*
             * 后端已经停止：
             * - 检测线程
             * - 手部检测线程
             * - 摄像头
             * - WebRTC
             */

            /*
             * 前端停止：
             * - WebRTC PeerConnection
             * - MJPEG
             * - 结果 WebSocket
             * - 自动重连定时器
             */
            stopClientStreams(
                t('message.messagetext.stopedDetection'),
            )

            /*
             * 即使后端返回状态异常，也强制把前端恢复到
             * “未开始”状态。
             */
            applyRuntimeStatus({
                initialized: false,
                running: false,
                paused: false,
                active: false,
            })

            /*
             * 清空工序、事件、告警、OK/NG 和当前结果。
             */
            resetStoppedUiState()
        },
    })
}

onMounted(async () => {
    await getSopConfiguration()
    await updateFooterHintOverflow()

    window.addEventListener(
        'resize',
        updateFooterHintOverflow,
    )

    timeoutTicker = window.setInterval(() => {
        timeoutNow.value = Date.now()
    }, TIMEOUT_TICK_MS)

    await refreshDetectionStatus()
})

onBeforeUnmount(() => {
    window.removeEventListener(
        'resize',
        updateFooterHintOverflow,
    )

    clearCriticalAlert()
    clearTimer('reconnect')
    clearTimer('result')

    if (timeoutTicker) {
        clearInterval(timeoutTicker)
        timeoutTicker = null
    }

    stopStream()
    closeResultSocket()
})

watch(
    () => [currentStep.value?.name, currentStep.value?.hint],
    updateFooterHintOverflow,
)
</script>

<style scoped lang="scss">
.layout-container {
    width: 100%;
    height: 100%;

    > .layout-container {
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
        background: red;

        &.is-connected {
            background: green;
        }
    }

    .camera-item-header {
        height: 9%;
        padding: 0 10px;
        border-bottom: 1px solid #d8dce5;

        .header-left {
            max-width: 85%;
            gap: 10px;
            overflow: hidden;
        }

        .header-timeout {
            flex: 0 0 auto;
            width: 170px;
            min-width: 170px;

            .header-timeout-progress {
                width: 100%;

                :deep(.el-progress__text) {
                    min-width: 88px;
                    font-size: 12px;
                }

                :deep(.el-progress-bar__outer) {
                    background: var(--el-fill-color);
                }
            }
        }

        .header-right {
            min-width: 180px;
            height: 100%;
            padding-left: 10px;
            border-left: 1px solid #000;
            display: flex;
            align-items: center;
            justify-content: flex-end;
        }
    }

    .camera-item-body {
        position: relative;
        width: 100%;
        height: 90%;
        overflow: hidden;

        &::before {
            position: absolute;
            z-index: 0;
            inset: 0;
            content: '';
            background: url(@/assets/img/FAIVS.jpg) center / 100% 100% no-repeat;
            opacity: 0.1;
        }
        .el-alert {
            // position: relative;
            z-index: 1;
        }
        .video-stream {
            position: absolute;
            z-index: 0;
            top: 50%;
            left: 50%;
            width: 100%;
            height: 100%;
            object-fit: contain;
            transform: translate(-50%, -50%);
        }

        .reconnecting-message {
            position: absolute;
            z-index: 1;
            top: 50%;
            left: 50%;
            width: 300px;
            max-width: 70%;
            min-height: 80px;
            padding: 12px;
            background: var(--bs-alert-error-bgcolor);
            transform: translate(-50%, -50%);
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
        }

        .current-step-overlay {
            position: absolute;
            z-index: 2;
            left: 12px;
            bottom: 12px;
            width: 360px;
            max-width: calc(100% - 24px);
            padding: 10px 12px;
            border-radius: 8px;
            background: rgb(20 25 32 / 72%);
            color: #fff;

            .overlay-title,
            .overlay-meta {
                font-size: 12px;
                color: #d1d8e0;
            }

            .overlay-name {
                margin-top: 4px;
                font-size: 22px;
                font-weight: 700;
            }

            .overlay-meta {
                margin-top: 6px;
            }
        }
    }
}

.process-steps.el-steps--vertical {
    :deep(.el-step__icon) {
        width: 24px !important;
        height: 24px !important;
    }

    :deep(.el-step__line) {
        left: 12px !important;
    }

    :deep(.el-step__main) {
        padding-left: 8px !important;
    }
}

.right-side {
    height: 100%;
    padding-left: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    gap: 10px;
    box-sizing: border-box;

    .side-card {
        min-height: 0;
        margin: 0;
        border-radius: 0;
        background: var(--bs-bgcolor);
        display: flex;
        flex-direction: column;
    }

    .side-card-current {
        flex: 0 0 18%;
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
        overflow: auto;
    }
}

.current-section {
    height: 100%;
    display: flex;
    flex-direction: column;

    .current-name {
        margin-bottom: 6px;
        overflow: hidden;
        font-size: 22px;
        font-weight: 700;
        line-height: 1.1;
        color: #1d2d3d;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }

    .current-desc {
        margin-bottom: 8px;
        overflow: hidden;
        font-size: 13px;
        line-height: 1.4;
        color: #606266;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .current-progress-row {
        min-height: 28px;
        display: flex;
        align-items: center;
        gap: 6px;

        .current-metrics {
            flex: 0 0 auto;
            display: flex;
            gap: 6px;
        }

        .current-metric {
            min-width: 50px;
            height: 26px;
            padding: 0 6px;
            color: #fff;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 4px;

            span {
                font-size: 12px;
            }

            strong {
                font-size: 18px;
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
            padding: 0 6px;
            border: 1px solid #e4e7ed;
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
    border: 1px solid #e6e8eb;

    .alert-line {
        min-width: 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .alert-message {
        overflow: hidden;
        font-size: 13px;
        color: #2f3540;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
}

.alert-warning,
.event-warning {
    background: var(--bs-alert-warning-bgcolor);
}

.alert-error,
.event-error {
    background: var(--bs-alert-error-bgcolor);
}

.event-info {
    background: var(--bs-alert-info-bgcolor);
}

.event-success {
    background: var(--bs-alert-success-bgcolor, var(--bs-alert-info-bgcolor));
}

.events-section,
.event-list {
    height: 100%;
    min-height: 0;
}

.event-list {
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.event-item {
    padding: 6px 8px;
    font-size: 12px;
    display: grid;
    grid-template-columns: 62px 82px 1fr;
    align-items: center;
    gap: 8px;

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

.empty-state {
    font-size: 13px;
    color: #909399;
}

.action-footer {
    min-height: 80px;
    padding: 8px 10px;
    border-top: 1px solid #d8dce5;
    background: var(--bs-bgcolor);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;

    .footer-progress {
        flex: 0 0 76px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;

        .footer-title {
            font-size: 13px;
            color: #3a4a5a;
        }
    }

    .footer-current {
        flex: 1;
        min-width: 0;
        align-self: stretch;
        padding-left: 14px;
        border-left: 1px solid #e6e8eb;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    .footer-current-title {
        overflow: hidden;
        font-size: 18px;
        font-weight: 700;
        color: #1d2d3d;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .footer-current-hint {
        position: relative;
        height: 40px;
        overflow: hidden;
        font-size: 14px;
        line-height: 20px;
        color: #606266;
    }

    .footer-current-hint-track.is-scrolling {
        animation: footer-hint-scroll 8s linear infinite;
    }

    .footer-current-hint-text {
        min-height: 40px;
    }

    .footer-current-hint-end {
        color: #909399;
        text-align: center;
    }

    .footer-actions {
        flex: 0 0 auto;
        display: flex;
        align-items: center;
        gap: 8px;
    }
}

@keyframes footer-hint-scroll {
    0%,
    35% {
        transform: translateY(0);
    }

    65%,
    100% {
        transform: translateY(-50%);
    }
}
</style>
