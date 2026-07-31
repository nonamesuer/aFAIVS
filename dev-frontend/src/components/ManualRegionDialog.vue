<template>
  <el-dialog
    :model-value="visible"
    class="manual-region-dialog"
    modal-class="bs-shade"
    fullscreen
    destroy-on-close
    @closed="handleClosed"
    @update:model-value="emit('update:visible', $event)"
  >
    <template #header>
      <div class="dialog-header">
        <div>
          <h2>{{ $t('config.manual_region.title') }}</h2>
          <p>{{ $t('config.manual_region.description') }}</p>
        </div>

        <div class="header-actions">
          <el-select
            v-model="cameraIndex"
            :placeholder="$t('config.manual_region.select_camera')"
            style="width: 240px"
          >
            <el-option
              v-for="(camera, index) in cameraList"
              :key="camera"
              :label="camera"
              :value="index"
            />
          </el-select>

          <el-button
            :type="frozen ? 'warning' : 'primary'"
            plain
            :disabled="cameraIndex === null"
            @click="frozen = !frozen"
          >
            {{ frozen
              ? $t('config.manual_region.resume_preview')
              : $t('config.manual_region.freeze_preview') }}
          </el-button>

          <el-button
            type="primary"
            :disabled="cameraIndex === null || !frameWidth"
            @click="beginDrawing"
          >
            {{ $t('config.manual_region.draw_region') }}
          </el-button>
        </div>
      </div>
    </template>

    <div class="region-layout">
      <section class="canvas-panel">
        <div
          class="canvas-wrapper"
          :class="{ drawing: drawingMode }"
        >
          <canvas
            ref="canvasRef"
            @pointerdown="handlePointerDown"
            @pointermove="handlePointerMove"
            @pointerup="handlePointerUp"
            @pointercancel="handlePointerUp"
          />

          <el-empty
            v-if="cameraIndex === null"
            :description="$t('config.manual_region.select_camera')"
          />

          <div
            v-else-if="!frameWidth"
            class="preview-status"
          >
            <el-icon class="is-loading"><Loading /></el-icon>
            {{ $t('config.manual_region.waiting_preview') }}
          </div>

          <div
            v-if="drawingMode"
            class="drawing-tip"
          >
            {{ $t('config.manual_region.drawing_tip') }}
          </div>
        </div>

        <div class="canvas-footer">
          <span>
            {{ $t('config.manual_region.reference_resolution') }}:
            {{ frameWidth || '-' }} × {{ frameHeight || '-' }}
          </span>
          <span>
            {{ $t('config.manual_region.coordinate_hint') }}
          </span>
        </div>
      </section>

      <aside class="region-sidebar">
        <div class="sidebar-title">
          <strong>{{ $t('config.manual_region.region_list') }}</strong>
          <el-tag>{{ workingRegions.length }}</el-tag>
        </div>

        <div class="region-list">
          <button
            v-for="region in workingRegions"
            :key="region.id"
            type="button"
            :class="['region-list-item', { active: selectedId === region.id }]"
            @click="selectRegion(region.id)"
          >
            <span
              class="region-color"
              :style="{ backgroundColor: region.color }"
            />
            <span class="region-name">{{ region.name }}</span>
            <el-tag
              v-if="region.enabled === false"
              size="small"
              type="info"
            >
              {{ $t('config.manual_region.disabled') }}
            </el-tag>
          </button>

          <el-empty
            v-if="!workingRegions.length"
            :description="$t('config.manual_region.no_regions')"
            :image-size="90"
          />
        </div>

        <el-divider />

        <el-form
          v-if="selectedRegion"
          label-position="top"
        >
          <el-form-item :label="$t('config.manual_region.region_name')">
            <el-input
              v-model="selectedRegion.name"
              maxlength="64"
              show-word-limit
              @input="markDirty"
            />
          </el-form-item>

          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item :label="$t('config.manual_region.region_color')">
                <el-color-picker
                  v-model="selectedRegion.color"
                  color-format="hex"
                  @active-change="handleColorChange"
                  @change="handleColorChange"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('config.manual_region.enabled')">
                <el-switch
                  v-model="selectedRegion.enabled"
                  @change="markDirty"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <div class="coordinate-grid">
            <span>X1: {{ formatCoordinate(selectedRegion.x1) }}</span>
            <span>Y1: {{ formatCoordinate(selectedRegion.y1) }}</span>
            <span>X2: {{ formatCoordinate(selectedRegion.x2) }}</span>
            <span>Y2: {{ formatCoordinate(selectedRegion.y2) }}</span>
          </div>

          <el-alert
            :closable="false"
            type="info"
            show-icon
            :title="$t('config.manual_region.adjust_tip')"
          />

          <div class="region-actions">
            <el-button
              type="primary"
              plain
              @click="redrawSelectedRegion"
            >
              {{ $t('config.manual_region.redraw') }}
            </el-button>
            <el-button
              type="danger"
              plain
              @click="removeSelectedRegion"
            >
              {{ $t('button.delete') }}
            </el-button>
          </div>
        </el-form>

        <el-empty
          v-else
          :description="$t('config.manual_region.select_region')"
          :image-size="80"
        />
      </aside>
    </div>

    <template #footer>
      <el-button @click="reloadCurrentProfile">
        {{ $t('button.reset') }}
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="cameraIndex === null || !frameWidth"
        @click="saveRegions"
      >
        {{ $t('button.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
  watch,
} from 'vue'
import {
  ElMessage,
  ElMessageBox,
} from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

import api from '@/api/index'
import { useAppStore } from '@/stores/store'

interface ManualRegion {
  id: string
  name: string
  color: string
  shape: 'rectangle'
  x1: number
  y1: number
  x2: number
  y2: number
  enabled: boolean
}

interface ManualRegionProfile {
  referenceWidth: number
  referenceHeight: number
  regions: ManualRegion[]
}

interface ManualRegionsConfig {
  version: number
  cameras: Record<string, ManualRegionProfile>
}

type HandleName = 'nw' | 'ne' | 'sw' | 'se'
type Interaction =
  | {
      type: 'draw'
      startX: number
      startY: number
      original?: ManualRegion
    }
  | {
      type: 'move'
      regionId: string
      startX: number
      startY: number
      original: ManualRegion
    }
  | {
      type: 'resize'
      regionId: string
      handle: HandleName
      original: ManualRegion
    }

const props = defineProps<{
  visible: boolean
  cameraList: string[]
  manualRegions: ManualRegionsConfig
}>()

const emit = defineEmits<{
  (event: 'update:visible', value: boolean): void
  (event: 'update:manualRegions', value: ManualRegionsConfig): void
  (event: 'saved'): void
}>()

const { t } = useI18n()
const appStore = useAppStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const cameraIndex = ref<number | null>(null)
const workingRegions = ref<ManualRegion[]>([])
const selectedId = ref('')
const persistedIds = ref(new Set<string>())
const frozen = ref(false)
const drawingMode = ref(false)
const saving = ref(false)
const dirty = ref(false)
const frameWidth = ref(0)
const frameHeight = ref(0)

let socket: WebSocket | null = null
let latestBitmap: ImageBitmap | null = null
let frameDecoding = false
let interaction: Interaction | null = null

const selectedRegion = computed(() =>
  workingRegions.value.find(region => region.id === selectedId.value) || null
)

const currentCameraName = computed(() =>
  cameraIndex.value === null
    ? ''
    : String(props.cameraList[cameraIndex.value] || '')
)

const cloneRegion = (region: ManualRegion): ManualRegion => ({
  ...region,
})

const normalizeProfileRegions = (profile?: ManualRegionProfile): ManualRegion[] =>
  Array.isArray(profile?.regions)
    ? profile.regions.map(region => ({
        id: String(region.id || ''),
        name: String(region.name || ''),
        color: String(region.color || '#409EFF').toUpperCase(),
        shape: 'rectangle',
        x1: Number(region.x1 || 0),
        y1: Number(region.y1 || 0),
        x2: Number(region.x2 || 0),
        y2: Number(region.y2 || 0),
        enabled: region.enabled !== false,
      }))
    : []

const reloadCurrentProfile = () => {
  const profile = props.manualRegions?.cameras?.[currentCameraName.value]
  workingRegions.value = normalizeProfileRegions(profile)
  persistedIds.value = new Set(workingRegions.value.map(region => region.id))
  selectedId.value = workingRegions.value[0]?.id || ''
  drawingMode.value = false
  interaction = null
  dirty.value = false
  renderCanvas()
}

const createRegionId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `region_${crypto.randomUUID().replace(/-/g, '')}`
  }
  return `region_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

const formatCoordinate = (value: number) =>
  Number(value || 0).toFixed(4)

const clamp = (value: number, min = 0, max = 1) =>
  Math.min(max, Math.max(min, value))

const normalizeBounds = (
  x1: number,
  y1: number,
  x2: number,
  y2: number,
) => ({
  x1: clamp(Math.min(x1, x2)),
  y1: clamp(Math.min(y1, y2)),
  x2: clamp(Math.max(x1, x2)),
  y2: clamp(Math.max(y1, y2)),
})

const markDirty = () => {
  dirty.value = true
  renderCanvas()
}

const handleColorChange = (value: string | null) => {
  if (selectedRegion.value && value) {
    selectedRegion.value.color = value.toUpperCase()
  }
  markDirty()
}

const selectRegion = (regionId: string) => {
  selectedId.value = regionId
  drawingMode.value = false
  renderCanvas()
}

const beginDrawing = () => {
  if (!frameWidth.value) return
  frozen.value = true
  drawingMode.value = true
  selectedId.value = ''
  interaction = null
  renderCanvas()
}

const redrawSelectedRegion = () => {
  if (!selectedRegion.value) return
  frozen.value = true
  drawingMode.value = true
  interaction = {
    type: 'draw',
    startX: 0,
    startY: 0,
    original: cloneRegion(selectedRegion.value),
  }
  renderCanvas()
}

const canvasPoint = (event: PointerEvent) => {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const bounds = canvas.getBoundingClientRect()
  return {
    x: clamp((event.clientX - bounds.left) / Math.max(bounds.width, 1)),
    y: clamp((event.clientY - bounds.top) / Math.max(bounds.height, 1)),
  }
}

const handleTolerance = () => {
  const canvas = canvasRef.value
  if (!canvas) return 0.02
  const bounds = canvas.getBoundingClientRect()
  return Math.max(0.008, 10 / Math.max(bounds.width, bounds.height, 1))
}

const regionHandleAt = (
  region: ManualRegion,
  x: number,
  y: number,
): HandleName | null => {
  const tolerance = handleTolerance()
  const handles: Array<[HandleName, number, number]> = [
    ['nw', region.x1, region.y1],
    ['ne', region.x2, region.y1],
    ['sw', region.x1, region.y2],
    ['se', region.x2, region.y2],
  ]
  return handles.find(
    ([, handleX, handleY]) =>
      Math.abs(x - handleX) <= tolerance
      && Math.abs(y - handleY) <= tolerance
  )?.[0] || null
}

const regionAt = (x: number, y: number) =>
  [...workingRegions.value]
    .reverse()
    .find(region =>
      x >= region.x1
      && x <= region.x2
      && y >= region.y1
      && y <= region.y2
    ) || null

const handlePointerDown = (event: PointerEvent) => {
  if (!frameWidth.value) return
  const canvas = canvasRef.value
  canvas?.setPointerCapture(event.pointerId)
  const point = canvasPoint(event)

  if (drawingMode.value) {
    const original = interaction?.type === 'draw'
      ? interaction.original
      : undefined
    interaction = {
      type: 'draw',
      startX: point.x,
      startY: point.y,
      original,
    }
    return
  }

  const selected = selectedRegion.value
  const handle = selected
    ? regionHandleAt(selected, point.x, point.y)
    : null
  if (selected && handle) {
    interaction = {
      type: 'resize',
      regionId: selected.id,
      handle,
      original: cloneRegion(selected),
    }
    frozen.value = true
    return
  }

  const hit = regionAt(point.x, point.y)
  if (!hit) {
    selectedId.value = ''
    renderCanvas()
    return
  }

  selectedId.value = hit.id
  interaction = {
    type: 'move',
    regionId: hit.id,
    startX: point.x,
    startY: point.y,
    original: cloneRegion(hit),
  }
  frozen.value = true
  renderCanvas()
}

const handlePointerMove = (event: PointerEvent) => {
  if (!interaction) return
  const point = canvasPoint(event)

  if (interaction.type === 'draw') {
    renderCanvas({
      ...normalizeBounds(
        interaction.startX,
        interaction.startY,
        point.x,
        point.y,
      ),
      color: interaction.original?.color || '#409EFF',
    })
    return
  }

  const region = workingRegions.value.find(
    item => item.id === interaction?.regionId
  )
  if (!region) return

  if (interaction.type === 'move') {
    const width = interaction.original.x2 - interaction.original.x1
    const height = interaction.original.y2 - interaction.original.y1
    const dx = point.x - interaction.startX
    const dy = point.y - interaction.startY
    const x1 = clamp(interaction.original.x1 + dx, 0, 1 - width)
    const y1 = clamp(interaction.original.y1 + dy, 0, 1 - height)
    Object.assign(region, {
      x1,
      y1,
      x2: x1 + width,
      y2: y1 + height,
    })
  } else {
    const original = interaction.original
    const next = {
      x1: original.x1,
      y1: original.y1,
      x2: original.x2,
      y2: original.y2,
    }
    if (interaction.handle.includes('n')) next.y1 = point.y
    if (interaction.handle.includes('s')) next.y2 = point.y
    if (interaction.handle.includes('w')) next.x1 = point.x
    if (interaction.handle.includes('e')) next.x2 = point.x
    Object.assign(
      region,
      normalizeBounds(next.x1, next.y1, next.x2, next.y2),
    )
  }

  dirty.value = true
  renderCanvas()
}

const handlePointerUp = (event: PointerEvent) => {
  const canvas = canvasRef.value
  if (canvas?.hasPointerCapture(event.pointerId)) {
    canvas.releasePointerCapture(event.pointerId)
  }
  if (!interaction) return

  if (interaction.type === 'draw') {
    const point = canvasPoint(event)
    const bounds = normalizeBounds(
      interaction.startX,
      interaction.startY,
      point.x,
      point.y,
    )
    if (
      bounds.x2 - bounds.x1 >= 0.002
      && bounds.y2 - bounds.y1 >= 0.002
    ) {
      if (interaction.original) {
        const existing = workingRegions.value.find(
          region => region.id === interaction?.original?.id
        )
        if (existing) Object.assign(existing, bounds)
        selectedId.value = interaction.original.id
      } else {
        const region: ManualRegion = {
          id: createRegionId(),
          name: `${t('config.manual_region.default_region_name')} ${workingRegions.value.length + 1}`,
          color: '#409EFF',
          shape: 'rectangle',
          ...bounds,
          enabled: true,
        }
        workingRegions.value.push(region)
        selectedId.value = region.id
      }
      dirty.value = true
    }
    drawingMode.value = false
  }

  interaction = null
  renderCanvas()
}

const drawRegion = (
  context: CanvasRenderingContext2D,
  region: Pick<ManualRegion, 'x1' | 'y1' | 'x2' | 'y2' | 'color'> & {
    id?: string
    name?: string
    enabled?: boolean
  },
  selected = false,
) => {
  const canvas = canvasRef.value
  if (!canvas) return
  const x = region.x1 * canvas.width
  const y = region.y1 * canvas.height
  const width = (region.x2 - region.x1) * canvas.width
  const height = (region.y2 - region.y1) * canvas.height
  const color = region.color || '#409EFF'

  context.save()
  context.globalAlpha = region.enabled === false ? 0.35 : 1
  context.fillStyle = `${color}2E`
  context.fillRect(x, y, width, height)
  context.strokeStyle = color
  context.lineWidth = selected ? 4 : 2
  context.strokeRect(x, y, width, height)

  if (region.name) {
    context.font = `${Math.max(14, Math.round(canvas.width / 70))}px sans-serif`
    const padding = 5
    const textWidth = context.measureText(region.name).width
    const labelY = Math.max(0, y - 24)
    context.fillStyle = color
    context.fillRect(x, labelY, textWidth + padding * 2, 24)
    context.fillStyle = '#FFFFFF'
    context.fillText(region.name, x + padding, labelY + 18)
  }

  if (selected) {
    const handleSize = Math.max(7, canvas.width / 120)
    const points = [
      [x, y],
      [x + width, y],
      [x, y + height],
      [x + width, y + height],
    ]
    context.fillStyle = '#FFFFFF'
    context.strokeStyle = color
    context.lineWidth = 2
    for (const [handleX, handleY] of points) {
      context.fillRect(
        handleX - handleSize / 2,
        handleY - handleSize / 2,
        handleSize,
        handleSize,
      )
      context.strokeRect(
        handleX - handleSize / 2,
        handleY - handleSize / 2,
        handleSize,
        handleSize,
      )
    }
  }
  context.restore()
}

const renderCanvas = (
  draft?: {
    x1: number
    y1: number
    x2: number
    y2: number
    color: string
  },
) => {
  const canvas = canvasRef.value
  if (!canvas || !latestBitmap) return
  if (
    canvas.width !== latestBitmap.width
    || canvas.height !== latestBitmap.height
  ) {
    canvas.width = latestBitmap.width
    canvas.height = latestBitmap.height
  }
  const context = canvas.getContext('2d')
  if (!context) return
  context.clearRect(0, 0, canvas.width, canvas.height)
  context.drawImage(latestBitmap, 0, 0, canvas.width, canvas.height)
  for (const region of workingRegions.value) {
    drawRegion(context, region, selectedId.value === region.id)
  }
  if (draft) drawRegion(context, draft, true)
}

const stopPreview = () => {
  if (socket) {
    socket.onmessage = null
    socket.onerror = null
    socket.close()
    socket = null
  }
  latestBitmap?.close()
  latestBitmap = null
  frameDecoding = false
  frameWidth.value = 0
  frameHeight.value = 0
  const canvas = canvasRef.value
  canvas?.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height)
}

const startPreview = () => {
  stopPreview()
  if (cameraIndex.value === null) return
  socket = new WebSocket(
    `ws://localhost:${appStore.servicePort}/ws/video_streaming`
    + `?camera_id=${cameraIndex.value}&mode=manual-region`
  )
  socket.binaryType = 'arraybuffer'
  socket.onmessage = async event => {
    if (frozen.value || frameDecoding || !(event.data instanceof ArrayBuffer)) return
    const buffer = new Uint8Array(event.data)
    if (buffer.byteLength < 4) return
    const magic = new DataView(
      buffer.buffer,
      buffer.byteOffset,
      buffer.byteLength,
    ).getUint32(0)
    if (magic !== 0xffff0000) return

    frameDecoding = true
    try {
      const bitmap = await createImageBitmap(
        new Blob([buffer.slice(4)], { type: 'image/jpeg' })
      )
      latestBitmap?.close()
      latestBitmap = bitmap
      frameWidth.value = bitmap.width
      frameHeight.value = bitmap.height
      renderCanvas()
    } finally {
      frameDecoding = false
    }
  }
  socket.onerror = () => {
    ElMessage.error(t('config.manual_region.preview_failed'))
  }
}

const removeSelectedRegion = async () => {
  const region = selectedRegion.value
  if (!region) return
  try {
    await ElMessageBox.confirm(
      t('config.manual_region.delete_confirm', { name: region.name }),
      t('message.warning'),
      {
        confirmButtonText: t('button.delete'),
        cancelButtonText: t('button.cancel'),
        type: 'warning',
      },
    )
  } catch {
    return
  }

  if (persistedIds.value.has(region.id)) {
    saving.value = true
    try {
      const { data } = await api.deleteManualRegion({
        cameraName: currentCameraName.value,
        regionId: region.id,
      })
      if (!data.status) {
        ElMessage.error(data.msg)
        return
      }
      dirty.value = true
      emit('update:manualRegions', data.datas)
      persistedIds.value.delete(region.id)
    } catch (error: any) {
      ElMessage.error(error?.message || t('config.manual_region.delete_failed'))
      return
    } finally {
      saving.value = false
    }
  }

  workingRegions.value = workingRegions.value.filter(
    item => item.id !== region.id
  )
  selectedId.value = workingRegions.value[0]?.id || ''
  dirty.value = true
  renderCanvas()
  ElMessage.success(t('config.manual_region.delete_success'))
}

const validateRegions = () => {
  const names = new Set<string>()
  for (const region of workingRegions.value) {
    region.name = String(region.name || '').trim()
    if (!region.name) return t('config.manual_region.name_required')
    const normalizedName = region.name.toLocaleLowerCase()
    if (names.has(normalizedName)) {
      return t('config.manual_region.name_duplicate', { name: region.name })
    }
    names.add(normalizedName)
    if (
      region.x2 - region.x1 < 0.002
      || region.y2 - region.y1 < 0.002
    ) {
      return t('config.manual_region.region_too_small', { name: region.name })
    }
  }
  return ''
}

const saveRegions = async () => {
  const validationError = validateRegions()
  if (validationError) {
    ElMessage.error(validationError)
    return
  }
  saving.value = true
  try {
    const { data } = await api.saveManualRegions({
      cameraName: currentCameraName.value,
      referenceWidth: frameWidth.value,
      referenceHeight: frameHeight.value,
      regions: workingRegions.value,
    })
    if (!data.status) {
      ElMessage.error(data.msg)
      return
    }
    dirty.value = true
    emit('update:manualRegions', data.datas)
    persistedIds.value = new Set(workingRegions.value.map(region => region.id))
    dirty.value = false
    emit('saved')
    ElMessage.success(t('config.manual_region.save_success'))
  } catch (error: any) {
    ElMessage.error(error?.message || t('config.manual_region.save_failed'))
  } finally {
    saving.value = false
  }
}

const handleClosed = () => {
  stopPreview()
  cameraIndex.value = null
  workingRegions.value = []
  selectedId.value = ''
  drawingMode.value = false
  interaction = null
}

watch(
  () => props.visible,
  async visible => {
    if (!visible) {
      stopPreview()
      return
    }
    await nextTick()
    cameraIndex.value = props.cameraList.length ? 0 : null
    if (cameraIndex.value === null) {
      reloadCurrentProfile()
    }
  },
)

watch(cameraIndex, async (next, previous) => {
  if (!props.visible || next === previous) return
  frozen.value = false
  await nextTick()
  reloadCurrentProfile()
  startPreview()
})

watch(
  () => props.manualRegions,
  () => {
    if (props.visible && !dirty.value) reloadCurrentProfile()
  },
  { deep: true },
)

onBeforeUnmount(stopPreview)
</script>

<style scoped>
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;

  h2 {
    margin: 0 0 4px;
  }

  p {
    margin: 0;
    color: var(--el-text-color-secondary);
  }
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.region-layout {
  height: calc(100vh - 170px);
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
}

.canvas-panel,
.region-sidebar {
  min-height: 0;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.canvas-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.canvas-wrapper {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background:
    linear-gradient(45deg, #222 25%, transparent 25%),
    linear-gradient(-45deg, #222 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #222 75%),
    linear-gradient(-45deg, transparent 75%, #222 75%),
    #181818;
  background-size: 24px 24px;
  background-position: 0 0, 0 12px, 12px -12px, -12px 0;

  canvas {
    display: block;
    max-width: 100%;
    max-height: 100%;
    touch-action: none;
    cursor: default;
  }

  &.drawing canvas {
    cursor: crosshair;
  }
}

.preview-status,
.drawing-tip {
  position: absolute;
  z-index: 2;
  padding: 10px 16px;
  border-radius: 6px;
  color: #fff;
  background: rgba(0, 0, 0, 0.72);
}

.drawing-tip {
  left: 50%;
  top: 16px;
  transform: translateX(-50%);
}

.canvas-footer {
  min-height: 40px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color);
}

.region-sidebar {
  padding: 16px;
  overflow: auto;
}

.sidebar-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.region-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  overflow: auto;
}

.region-list-item {
  width: 100%;
  min-height: 44px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  color: var(--el-text-color-primary);
  background: var(--el-bg-color);
  cursor: pointer;

  &:hover,
  &.active {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }
}

.region-color {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  border-radius: 4px;
}

.region-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coordinate-grid {
  margin-bottom: 14px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  font-family: monospace;
  color: var(--el-text-color-secondary);
}

.region-actions {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1000px) {
  .dialog-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .region-layout {
    height: auto;
    grid-template-columns: 1fr;
  }

  .canvas-panel {
    min-height: 55vh;
  }
}
</style>
