type I18nContext = {t:(key:string,params?:Record<string,unknown>)=>string;te:(key:string)=>boolean;locale?:string | {value?:string}};

type ReasonSource = string | Record<string,any> | null | undefined;

function readReason(source: ReasonSource) {
    if (typeof source === 'string')return {code:'',params:{},text:source};
    const value = source && typeof source === 'object' ? source : {};
    return {code:String(value.reasonCode || value.reason_code || value.lastReasonCode || value.last_reason_code || ''),params:value.reasonParams || value.reason_params || value.lastReasonParams || value.last_reason_params || {},text:String(value.reason || value.lastReason || value.last_reason || '')};
};

function localeName(locale: I18nContext['locale']) {return typeof locale === 'string' ? locale : String(locale?.value || 'zh')};

function listText(value: unknown,locale: I18nContext['locale']) {
    if (!Array.isArray(value))return String(value || '');
    try {return new Intl.ListFormat(localeName(locale),{style:'short',type:'conjunction'}).format(value.map(item => String(item)))} catch {return value.join(', ')};
};

function legacyReason(text: string,{t}:I18nContext) {
    if (!text)return '';
    let matched = text.match(/^NG: Expected (.+), but (.+) entered (.+)$/);if (matched)return t('sopReason.WRONG_OBJECT_ENTERED',{expected:matched[1],actual:matched[2],target:matched[3]});
    matched = text.match(/^Step timeout: (.+) exceeded ([\d.]+)s$/);if (matched)return t('sopReason.STEP_TIMEOUT',{step:matched[1],seconds:matched[2]});
    matched = text.match(/^Waiting for: (.+)$/);if (matched)return t('sopReason.WAITING_REQUIRED_ITEMS',{items:matched[1]});
    matched = text.match(/^Waiting for (.+) in (.+)$/);if (matched)return t('sopReason.WAITING_OBJECT_IN_REGION',{object:matched[1],region:matched[2]});
    matched = text.match(/^Waiting for (.+) to enter (.+)$/);if (matched)return t('sopReason.WAITING_OBJECT_ENTER_TARGET',{object:matched[1],target:matched[2]});
    if (text === 'All steps completed')return t('sopReason.ALL_STEPS_COMPLETED');
    if (text === 'SOP paused')return t('sopReason.SOP_PAUSED');
    if (text === 'SOP resumed')return t('sopReason.SOP_RESUMED');
    return text;
};

export function translateSopReason(source: ReasonSource,context:I18nContext) {
    const {code,params,text} = readReason(source);const key = `sopReason.${code}`;
    if (!code || !context.te(key))return legacyReason(text,context);
    const translatedParams:Record<string,unknown> = {...params};
    if (Array.isArray(translatedParams.items))translatedParams.items = listText(translatedParams.items,context.locale);
    if (translatedParams.object === 'item')translatedParams.object = context.t('sopReasonValue.item');
    if (typeof translatedParams.phase === 'string' && context.te(`sopReasonPhase.${translatedParams.phase}`))translatedParams.phase = context.t(`sopReasonPhase.${translatedParams.phase}`);
    if (translatedParams.detailCode)translatedParams.detail = translateSopReason({reasonCode:translatedParams.detailCode,reasonParams:translatedParams.detailParams,reason:translatedParams.detail},context);
    return context.t(key,translatedParams);
};

export function sopReasonKey(source: ReasonSource) {const value = readReason(source);return `${value.code}|${JSON.stringify(value.params)}|${value.text}`};
