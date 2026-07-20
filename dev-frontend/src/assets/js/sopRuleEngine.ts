import { i18n } from '@/lang'

export type ObjectDetectionPhase = 'source' | 'transit' | 'target'

export interface ObjectDetectionConfig {
  source: boolean
  transit: boolean
  target: boolean
}

export interface SopValidationResult {
  valid: boolean
  code: string
  message: string
  plan: string[]
}

const HAND_SIDES = ['l', 'r'] as const

const tr = (key: string, fallback: string, params?: Record<string, unknown>): string => {
  const translated = i18n.global.t(key, params || {})
  return translated === key ? fallback : String(translated)
}

export const normalizeObjectDetection = (context: Record<string, any> = {}): ObjectDetectionConfig => {
  const raw = context.objectDetection
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return {
      source: Boolean(raw.source),
      transit: Boolean(raw.transit),
      target: Boolean(raw.target),
    }
  }

  const legacy = context.expectedObjectRequire
  if (legacy && typeof legacy === 'object' && !Array.isArray(legacy)) {
    return {
      source: Boolean(legacy.source),
      transit: Boolean(legacy.transit),
      target: Boolean(legacy.target),
    }
  }

  const required = legacy !== false
  return { source: required, transit: required, target: required }
}

export const hasConfiguredHands = (context: Record<string, any> = {}): boolean => {
  const points = context.handPoints
  if (!points || typeof points !== 'object' || Array.isArray(points)) return false
  return HAND_SIDES.some(side => Array.isArray(points[side]) && points[side].length > 0)
}

export const buildExecutionPlan = (step: any): string[] => {
  const context = step?.context || {}
  const expected = String(context.expectedObject || '').trim()
  const source = String(context.fromRegion || '').trim()
  const target = String(context.toRegion || '').trim()
  const phases = normalizeObjectDetection(context)
  const hand = hasConfiguredHands(context)
  const plan: string[] = []

  if (source) {
    if (phases.source && expected) {
      plan.push(
        tr('sopRuleEngine.plan.detectInSource', '在 {source} 检测到 {expected}', { source, expected })
      )
    }
    if (hand) {
      plan.push(
        phases.source && expected
          ? tr('sopRuleEngine.plan.handEnterAndApproach', '手部进入 {source} 并接近 {expected}', { source, expected })
          : tr('sopRuleEngine.plan.handEnterSource', '手部进入 {source}', { source })
      )
    }
    if (!hand && expected) {
      plan.push(
        tr(
          'sopRuleEngine.plan.sourceCountDecreaseEvidence',
          '以 {source} 中 {expected} 数量减少 1 作为拿取证据',
          { source, expected }
        )
      )
    }
  } else {
    if (phases.source && expected) {
      plan.push(tr('sopRuleEngine.plan.detectInView', '在可视范围检测到 {expected}', { expected }))
    }
    if (hand) plan.push(tr('sopRuleEngine.plan.handActionOutsideTarget', '检测到目标区域外的新手部动作'))
  }

  if (phases.transit && expected) {
    plan.push(
      hand
        ? tr('sopRuleEngine.plan.transitDetectWithHand', '移动过程中持续检测 {expected} 与手部接近', { expected })
        : tr('sopRuleEngine.plan.transitDetect', '移动过程中持续检测 {expected}', { expected })
    )
  } else if (hand) {
    plan.push(tr('sopRuleEngine.plan.trackHandInTransit', '移动过程中跟踪手部关键点'))
  }

  if (phases.target && expected) {
    plan.push(
      tr('sopRuleEngine.plan.targetCountIncrease', '{target} 中 {expected} 数量相对本轮基线增加 1', { target, expected })
    )
    if (hand) plan.push(tr('sopRuleEngine.plan.completeAfterHandLeave', '手部离开物料或目标区域后完成'))
  } else if (hand) {
    plan.push(tr('sopRuleEngine.plan.completeWhenHandOrTrackedObjectEnterTarget', '手部或被跟踪物进入 {target} 后完成', { target }))
  } else if (expected) {
    plan.push(tr('sopRuleEngine.plan.completeWhenTrackedObjectEnterTarget', '被跟踪的 {expected} 进入 {target} 后完成', { expected, target }))
  }

  return plan
}

export const validateVisionStep = (step: any): SopValidationResult => {
  const id = step?.id ?? '?'
  const context = step?.context || {}
  const expected = String(context.expectedObject || '').trim()
  const source = String(context.fromRegion || '').trim()
  const target = String(context.toRegion || '').trim()
  const phases = normalizeObjectDetection(context)
  const hand = hasConfiguredHands(context)
  const anyObjectPhase = phases.source || phases.transit || phases.target
  const plan = buildExecutionPlan(step)

  const invalid = (code: string, message: string): SopValidationResult => ({
    valid: false,
    code,
    message: tr('sopRuleEngine.validate.stepMessage', '步骤 {id}：{message}', { id, message }),
    plan,
  })

  if (!target) return invalid('target_region_required', tr('sopRuleEngine.validate.targetRegionRequired', '必须配置目标区域'))
  if (!expected && anyObjectPhase) {
    return invalid(
      'object_phase_without_expected_object',
      tr('sopRuleEngine.validate.objectPhaseWithoutExpectedObject', '未配置期望目标时，不能启用任何物料检测阶段')
    )
  }
  if (!expected && !hand) {
    return invalid(
      'no_observation_method',
      tr('sopRuleEngine.validate.noObservationMethod', '必须配置期望目标或有效手部关键点')
    )
  }

  if (source) {
    if (expected && !hand && (!phases.source || !phases.transit)) {
      return invalid(
        'fixed_source_object_only_requires_source_and_transit',
        tr(
          'sopRuleEngine.validate.fixedSourceObjectOnlyRequiresSourceAndTransit',
          '配置了开始区域但未配置手部时，必须同时启用开始区域和移动过程物料检测'
        )
      )
    }
    if (!expected && anyObjectPhase) {
      return invalid(
        'hand_only_object_phase_conflict',
        tr('sopRuleEngine.validate.handOnlyObjectPhaseConflict', '手部-only 配置必须关闭全部物料检测阶段')
      )
    }
    return { valid: true, code: '', message: '', plan }
  }

  if (expected && !hand && !phases.target) {
    return invalid(
      'free_source_object_only_requires_target',
      tr('sopRuleEngine.validate.freeSourceObjectOnlyRequiresTarget', '未配置开始区域且未配置手部时，必须启用目标区域物料检测')
    )
  }
  if (!expected && anyObjectPhase) {
    return invalid(
      'hand_only_object_phase_conflict',
      tr('sopRuleEngine.validate.handOnlyObjectPhaseConflict', '手部-only 配置必须关闭全部物料检测阶段')
    )
  }

  return { valid: true, code: '', message: '', plan }
}

export const normalizeVisionStepForSave = (step: any): any => {
  const cloned = JSON.parse(JSON.stringify(step))
  cloned.target = Math.max(1, Number(cloned.target || 1))
  cloned.timeout = Math.max(0, Number(cloned.timeout || 0))
  cloned.context = cloned.context || {}
  cloned.context.objectDetection = normalizeObjectDetection(cloned.context)
  cloned.context.missTolerance = Math.max(0, Number(cloned.context.missTolerance ?? 5))
  cloned.context.handMargin = Math.max(0, Number(cloned.context.handMargin ?? 30))
  delete cloned.context.expectedObjectRequire
  return cloned
}
