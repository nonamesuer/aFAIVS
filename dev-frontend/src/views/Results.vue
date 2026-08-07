<template>
  <el-container >
    <el-header height="50px">
      <div class="header-left">
        <b>{{ $t("public.faivs") }}</b> > 
        <b>{{ $t("results.title") }}</b>
      </div>
      <div class="header-right">
        <img src="@/assets/img/bosch.26cf9c8e.svg" style="height: 28px; vertical-align: middle" alt=""/>
        <el-button :icon="Refresh" circle @click="loadAll" />
        <el-dropdown trigger="click" @command="langChange" style="cursor: pointer">
          <span  class="el-dropdown-link">{{ currentLanguage }}<el-icon class="el-icon--right"><ArrowDown /></el-icon></span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="en">English</el-dropdown-item>
              <el-dropdown-item command="zh">Chinese</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
      </div>
    </el-header>
    <el-main>
      <section class="hero-panel">
        <div>
          <div class="eyebrow">
            <span></span>{{ $t("results.intelligence") }}
          </div>
          <h1>{{ $t("results.hero_title") }}</h1>
          <p>{{ $t("results.hero_description") }}</p>
        </div>
        <div class="hero-meta">
          <div class="live-dot"><i></i>{{ $t("results.data_live") }}</div>
          <div>{{ formatTime(lastUpdated) }}</div>
        </div>
      </section>
      <el-alert v-if="overview.storage?.usingLocalData"
        class="storage-alert"
        type="warning"
        :closable="false"
        show-icon
        ><template #title>{{ $t("results.local_data_title") }}</template>
        <div>{{ $t("results.local_data_description") }}</div></el-alert
      >
      <el-alert
        v-if="overview.storage && !overview.storage.configuredAvailable"
        class="storage-alert"
        type="error"
        :closable="false"
        show-icon
        ><template #title>{{ $t("results.storage_unavailable") }}</template>
        <div>
          {{
            overview.storage.configuredError || overview.storage.configuredPath
          }}
        </div></el-alert
      >

      <section class="kpi-grid">
        <article class="kpi-card kpi-blue">
          <el-icon size="48" color="var(--accent)"><DataAnalysis /></el-icon>
          <div>
            <span>{{ $t("results.kpi.total") }}</span>
            <strong>{{ number(summary.total) }}</strong>
            <small>{{ $t("results.kpi.total_hint") }}</small>
          </div>
        </article>
        <article class="kpi-card kpi-green">
          <el-icon size="48" color="var(--accent)"><CircleCheckFilled /></el-icon>
          <div>
            <span>{{ $t("results.kpi.first_pass") }}</span
            ><strong>{{ percent(summary.firstPassRate) }}</strong
            ><small
              >{{ number(summary.ok) }} {{ $t("results.kpi.ok_runs") }}</small
            >
          </div>
        </article>
        <article class="kpi-card kpi-violet">
          <el-icon size="48" color="var(--accent)"><Finished /></el-icon>
          <div>
            <span>{{ $t("results.kpi.completion") }}</span
            ><strong>{{ percent(summary.completionRate) }}</strong
            ><small
              >{{ number(summary.completed) }} /
              {{ number(summary.total) }}</small
            >
          </div>
        </article>
        <article class="kpi-card kpi-orange">
          <el-icon size="48" color="var(--accent)"><WarningFilled /></el-icon>
          <div>
            <span>{{ $t("results.kpi.deviation") }}</span
            ><strong>{{ number(summary.deviation) }}</strong
            ><small
              >{{ number(summary.mediaCount) }}
              {{ $t("results.kpi.evidence") }}</small
            >
          </div>
        </article>
      </section>

      <section class="insight-grid">
        <article class="panel trend-panel">
          <div class="panel-heading">
            <div>
              <h3>{{ $t("results.trend_title") }}</h3>
            </div>
            <div class="legend">
              <span>
                <i class="ok"></i>
                {{ $t("results.quality.ok") }}
              </span>
              <span>
                <i class="ng"></i>
                {{ $t("results.quality.with_deviation") }}
              </span>
            </div>
          </div>
          <div v-if="trend.length" class="trend-chart">
            <div v-for="item in trend" :key="item.day" class="trend-column">
              <div class="trend-value">{{ item.total }}</div>
              <div class="trend-bar">
                <i class="bar-ng" :style="{ height: `${barHeight(item.deviation)}%` }"></i>
                <i class="bar-ok" :style="{ height: `${barHeight(item.ok)}%` }"></i>
              </div>
              <span>{{ shortDay(item.day) }}</span>
            </div>
          </div>
          <el-empty v-else :description="$t('results.no_data')" :image-size="72"/>
        </article>
        <article class="panel ranking-panel">
          <div class="panel-heading">
            <div>
              <h3>{{ $t("results.sop_ranking") }}</h3>
            </div>
          </div>
          <div v-if="ranking.length" class="ranking-list">
            <div v-for="(item, index) in ranking" :key="item.name" class="ranking-item">
              <span class="rank">{{ String(index + 1).padStart(2, "0") }}</span>
              <div class="rank-content">
                <div>
                  <b>{{ item.name }}</b
                  ><span>{{ item.total }}</span>
                </div>
                <el-progress
                  :percentage="rate(item.ok, item.total)"
                  :stroke-width="7"
                  :show-text="false"
                  color="var(--bs-turquoise-color)"
                />
              </div>
              <small>{{ percent(rate(item.ok, item.total)) }}</small>
            </div>
          </div>
          <el-empty v-else :description="$t('results.no_data')" :image-size="72"/>
        </article>
      </section>

      <section class="panel query-panel">
        <div class="panel-heading">
          <div>
            <h3>{{ $t("results.query_title") }}</h3>
          </div>
          <el-button type="primary" size="small" link :icon="Download" :loading="exporting" @click="exportData">{{ $t("results.export") }}</el-button>
        </div>
        <div class="filter-grid">
          <el-input size="small" v-model="filters.keyword" clearable :prefix-icon="Search"  :placeholder="$t('results.keyword_placeholder')"  @keyup.enter="search" />
          <el-date-picker style="box-sizing: border-box;" v-model="filters.dateRange" type="daterange"  value-format="x" :start-placeholder="$t('results.start_date')"  :end-placeholder="$t('results.end_date')" :range-separator="$t('results.to')"/>
          <el-select v-model="filters.sopName" clearable  filterable :placeholder="$t('results.sop')" >
            <el-option v-for="item in overview.options?.sopNames || []" :key="item" :label="item" :value="item"/>
          </el-select>
          <el-select v-model="filters.cameraName" clearable filterable :placeholder="$t('results.camera')">
            <el-option v-for="item in overview.options?.cameraNames || []" :key="item" :label="item" :value="item"/>
          </el-select>
          <el-select v-model="filters.executionStatus" clearable :placeholder="$t('results.execution_status')">
            <el-option v-for="item in executionOptions" :key="item" :label="$t(`results.execution.${item}`)" :value="item"/>
          </el-select>
          <el-select v-model="filters.qualityStatus"  clearable :placeholder="$t('results.quality_status')">
            <el-option v-for="item in qualityOptions" :key="item" :label="$t(`results.quality.${item}`)" :value="item"/>
          </el-select>
          <el-select v-model="filters.hasMedia" clearable :placeholder="$t('results.evidence_filter')">
            <el-option :label="$t('results.with_evidence')" value="true" />
            <el-option :label="$t('results.without_evidence')" value="false"/>
          </el-select>
          <div class="filter-actions">
            <el-button type="primary" size="small" :icon="Search" @click="search">{{ $t("button.search") }}</el-button>
            <el-button type="primary" :icon="RefreshLeft" plain size="small" @click="resetFilters">{{ $t("button.reset") }}</el-button>
          </div>
        </div>
      </section>

      <section class="panel table-panel">
        <div class="table-title">
          <div>
            <h3>{{ $t("results.list_title") }}</h3>
            <span>{{ $t("results.total_records", { count: number(resultData.total) }) }}</span>
          </div>
          <div class="table-legend">
            <span class="source configured">{{ $t("results.configured_storage") }}</span>
            <span class="source local">{{ $t("results.local_storage") }}</span>
          </div>
        </div>
        <el-table :data="resultData.items" row-key="runId" stripe class="result-table" empty-text="" @row-dblclick="openDetail">
          <template #empty>
            <el-empty :description="$t('results.no_results')"/>
          </template>
          <el-table-column width="20">
            <template #default="{ row }">
              <div class="source-line" :class="row.storageSource"></div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('results.result')" min-width="100">
            <template #default="{ row }">
              <div class="status-stack">
                <el-tag :type="executionType(row.executionStatus)" effect="dark">
                  {{ $t(`results.execution.${knownExecution(row.executionStatus)}`) }}
                </el-tag> 
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('displaytext.status')" min-width="100">
            <template #default="{ row }">
              <span :class="['quality-text', row.qualityStatus]">{{ $t(`results.quality.${knownQuality(row.qualityStatus)}`) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('results.sn')" min-width="150">
            <template #default="{ row }">
              <div class="primary-cell">
                <b>{{ row.externalReference || "-" }}</b>
                <small>{{ shortId(row.runId) }}</small>
              </div></template>
            </el-table-column>
          <el-table-column :label="$t('results.sop')" min-width="155">
            <template #default="{ row }">
              <div class="primary-cell">
                <b>{{ row.sopName || "-" }}</b>
                <small>{{ row.projectName || row.modelName || "-" }}</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('results.operator')" min-width="135">
            <template #default="{ row }"><div class="icon-cell">
                <el-icon><User /></el-icon>
                <span>{{ row.operatorName || "-" }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('results.progress')" min-width="165">
            <template #default="{ row }"><div class="progress-cell">
                <div>
                  <span>{{ row.completedSteps }}/{{ row.totalSteps }}</span
                  ><small>NG {{ row.ngCount }}</small>
                </div>
                <el-progress :percentage="rate(row.completedSteps, row.totalSteps)" :stroke-width="6" :show-text="false" :color="row.ngCount ? 'var(--bs-danger-color)' : 'var(--bs-success-color)'"
                /></div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('results.duration')" width="115">
            <template #default="{ row }">
              <b class="mono">{{ duration(row.totalDurationMs || (row.endedAtMs || Date.now()) - row.startedAtMs) }}</b>
            </template>
          </el-table-column>
          <el-table-column :label="$t('results.started_at')" width="170">
            <template #default="{ row }">
              <div class="primary-cell">
                <span>{{ formatDate(row.startedAtMs) }}</span>
                <small>{{ formatClock(row.startedAtMs) }}</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="$t('results.evidence')" width="92" align="center" class-name="evidence-col">
            <template #default="{ row }">
              <el-badge :value="row.mediaCount" :hidden="!row.mediaCount" badge-style="background:var(--bs-danger-color);border:none;">
                <el-icon :class="['media-icon', { active: row.mediaCount }]"><PictureFilled /></el-icon>
              </el-badge>
            </template>
          </el-table-column>
          <el-table-column fixed="right" width="105" align="center">
            <template #default="{ row }">
              <el-button type="primary" link :icon="View" @click="openDetail(row)">{{ $t("button.detail") }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination">
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            :total="resultData.total"
            @current-change="loadResults"
            @size-change="changePageSize"
          />
        </div>
      </section>
    </el-main>

    <el-drawer v-model="detailVisible" size="88%" class="result-drawer"  destroy-on-close @closed="clearMediaUrls">
      <template #header>
        <div class="drawer-header">
          <div>
            <span>{{ $t("results.detail_title") }}</span>
            <h2>
              {{ detail.run?.externalReference || shortId(detail.run?.runId) }}
            </h2>
          </div>
          <div class="drawer-status">
            <el-tag :type="executionType(detail.run?.executionStatus)" effect="dark" size="large">{{ $t(`results.execution.${knownExecution( detail.run?.executionStatus )}`) }}</el-tag>
            <span>{{ formatTime(detail.run?.startedAtMs) }}</span>
          </div>
        </div>
      </template>
      <div v-loading="detailLoading" class="drawer-body">
        <div class="detail-hero">
          <div class="detail-score">
            <el-progress type="dashboard" :percentage="detailPassRate" :width="118" :stroke-width="10" :color="detail.run?.ngCount ? '#e26b3a' : '#00a878'">
              <template #default>
                <strong>{{ detailPassRate }}%</strong>
                <span>{{ $t("results.step_completion") }}</span>
              </template>
            </el-progress>
          </div>
          <div class="detail-identity">
            <span>{{ $t("results.sop") }}</span>
            <h3>{{ detail.run?.sopName || "-" }}</h3>
            <p>
              {{ detail.run?.projectName }} · {{ detail.run?.modelName }} ·
              {{ detail.run?.cameraName }}
            </p>
          </div>
          <div class="detail-stat">
            <span>{{ $t("results.duration") }}</span
            ><strong>{{ duration(runDuration(detail.run)) }}</strong
            ><small
              >{{ $t("results.active") }}
              {{ duration(detail.run?.activeDurationMs) }}</small
            >
          </div>
          <div class="detail-stat danger">
            <span>{{ $t("results.ng_count") }}</span
            ><strong>{{ detail.run?.ngCount || 0 }}</strong
            ><small
              >{{ $t("results.reset_count") }}
              {{ detail.run?.resetCount || 0 }}</small
            >
          </div>
          <div class="detail-stat">
            <span>{{ $t("results.evidence") }}</span
            ><strong>{{ detail.media?.length || 0 }}</strong
            ><small>{{ formatBytes(mediaBytes) }}</small>
          </div>
        </div>

        <el-tabs
          v-model="detailTab"
          class="detail-tabs"
          @tab-change="handleDetailTab"
        >
          <el-tab-pane :label="$t('results.tabs.overview')" name="overview">
            <div class="overview-grid">
              <article class="detail-panel">
                <h3>{{ $t("results.basic_information") }}</h3>
                <el-descriptions :column="2" border
                  ><el-descriptions-item :label="$t('results.run_id')">{{
                    detail.run?.runId
                  }}</el-descriptions-item
                  ><el-descriptions-item :label="$t('results.sn')">{{
                    detail.run?.externalReference || "-"
                  }}</el-descriptions-item
                  ><el-descriptions-item :label="$t('results.operator')">{{
                    detail.run?.operatorName || "-"
                  }}</el-descriptions-item
                  ><el-descriptions-item :label="$t('results.station')">{{
                    detail.run?.stationName || "-"
                  }}</el-descriptions-item
                  ><el-descriptions-item :label="$t('results.trigger')">{{
                    triggerName(detail.run?.triggerSource)
                  }}</el-descriptions-item
                  ><el-descriptions-item :label="$t('results.attempt')">{{
                    detail.run?.attemptNo || 1
                  }}</el-descriptions-item
                  ><el-descriptions-item :label="$t('results.started_at')">{{
                    formatTime(detail.run?.startedAtMs)
                  }}</el-descriptions-item
                  ><el-descriptions-item :label="$t('results.ended_at')">{{
                    formatTime(detail.run?.endedAtMs)
                  }}</el-descriptions-item></el-descriptions
                >
              </article>
              <article class="detail-panel">
                <h3>{{ $t("results.time_breakdown") }}</h3>
                <div class="time-bars">
                  <div v-for="item in timeBreakdown" :key="item.key">
                    <div>
                      <span>{{ item.label }}</span
                      ><b>{{ duration(item.value) }}</b>
                    </div>
                    <el-progress
                      :percentage="
                        rate(item.value, detail.run?.totalDurationMs)
                      "
                      :stroke-width="9"
                      :show-text="false"
                      :color="item.color"
                    />
                  </div>
                </div>
              </article>
              <article class="detail-panel full">
                <h3>{{ $t("results.final_reason") }}</h3>
                <div
                  class="reason-box"
                  :class="{ danger: detail.run?.ngCount }"
                >
                  <el-icon><InfoFilled /></el-icon
                  ><span>{{
                    localizedReason(detail.run) || $t("results.no_reason")
                  }}</span>
                </div>
              </article>
            </div>
          </el-tab-pane>
          <el-tab-pane
            :label="`${$t('results.tabs.steps')} (${
              detail.steps?.length || 0
            })`"
            name="steps"
          >
            <div v-if="detail.steps?.length" class="step-timeline">
              <el-timeline
                ><el-timeline-item
                  v-for="step in detail.steps"
                  :key="step.stepRunId"
                  :timestamp="`${formatClock(step.startedAtMs)} → ${formatClock(
                    step.completedAtMs
                  )}`"
                  :type="stepType(step)"
                  placement="top"
                  hollow
                  ><article class="step-card">
                    <div class="step-heading">
                      <div class="step-order">{{ step.stepOrder }}</div>
                      <div>
                        <h3>
                          {{
                            step.stepName ||
                            `${$t("results.step")} ${step.stepId}`
                          }}
                        </h3>
                        <p>
                          {{ step.expectedObject || "-" }} ·
                          {{ step.expectedSource || "-" }} →
                          {{ step.expectedTarget || "-" }}
                        </p>
                      </div>
                      <el-tag :type="stepType(step)">{{
                        stepResult(step.result)
                      }}</el-tag>
                    </div>
                    <div class="step-metrics">
                      <span
                        ><b
                          >{{ step.completedCount || 0 }}/{{
                            step.targetCount || 1
                          }}</b
                        >{{ $t("results.completed_count") }}</span
                      ><span
                        ><b>{{ duration(step.totalDurationMs) }}</b
                        >{{ $t("results.duration") }}</span
                      ><span
                        ><b>{{ step.retryCount || 0 }}</b
                        >{{ $t("results.retry_count") }}</span
                      ><span :class="{ danger: step.ngCount }"
                        ><b>{{ step.ngCount || 0 }}</b
                        >NG</span
                      >
                    </div>
                    <el-collapse v-if="step.cycles?.length"
                      ><el-collapse-item
                        :title="`${$t('results.cycle_details')} (${
                          step.cycles.length
                        })`"
                        ><el-table :data="step.cycles" size="small"
                          ><el-table-column
                            prop="cycleNo"
                            :label="$t('results.cycle')"
                            width="70"
                          /><el-table-column
                            :label="$t('results.expected_actual')"
                            min-width="190"
                            ><template #default="{ row }"
                              ><span
                                >{{ row.expectedObject || "-" }} /
                                <b
                                  :class="{
                                    textDanger:
                                      row.actualObject &&
                                      row.actualObject !== row.expectedObject,
                                  }"
                                  >{{ row.actualObject || "-" }}</b
                                ></span
                              ></template
                            ></el-table-column
                          ><el-table-column :label="$t('results.pickup')"
                            ><template #default="{ row }">{{
                              duration(row.pickupDurationMs)
                            }}</template></el-table-column
                          ><el-table-column :label="$t('results.transit')"
                            ><template #default="{ row }">{{
                              duration(row.transitDurationMs)
                            }}</template></el-table-column
                          ><el-table-column :label="$t('results.placement')"
                            ><template #default="{ row }">{{
                              duration(row.placementDurationMs)
                            }}</template></el-table-column
                          ><el-table-column
                            label="NG"
                            prop="ngCount"
                            width="60"
                          /><el-table-column
                            :label="$t('results.result')"
                            width="100"
                            ><template #default="{ row }"
                              ><el-tag
                                :type="
                                  row.result === 'completed'
                                    ? 'success'
                                    : 'danger'
                                "
                                size="small"
                                >{{ stepResult(row.result) }}</el-tag
                              ></template
                            ></el-table-column
                          ></el-table
                        ></el-collapse-item
                      ></el-collapse
                    >
                  </article></el-timeline-item
                ></el-timeline
              >
            </div>
            <el-empty v-else :description="$t('results.no_steps')" />
          </el-tab-pane>
          <el-tab-pane
            :label="`${$t('results.tabs.events')} (${
              detail.events?.length || 0
            })`"
            name="events"
          >
            <div v-if="detail.events?.length" class="event-list">
              <article
                v-for="event in detail.events"
                :key="event.eventId"
                :class="['event-card', event.severity]"
              >
                <div class="event-icon">
                  <WarningFilled
                    v-if="
                      event.severity === 'error' || event.severity === 'warning'
                    "
                  /><CircleCheckFilled v-else />
                </div>
                <div>
                  <div class="event-heading">
                    <b>{{ eventType(event.eventType) }}</b
                    ><span>{{ formatTime(event.timestampMs) }}</span>
                  </div>
                  <p>{{ localizedEventReason(event) || event.code || "-" }}</p>
                  <pre
                    v-if="event.details && Object.keys(event.details).length"
                    >{{ prettyJson(event.details) }}</pre
                  >
                </div>
              </article>
            </div>
            <el-empty v-else :description="$t('results.no_events')" />
          </el-tab-pane>
          <el-tab-pane
            :label="`${$t('results.tabs.evidence')} (${
              detail.media?.length || 0
            })`"
            name="evidence"
          >
            <div v-if="detail.media?.length" class="media-grid">
              <article
                v-for="item in detail.media"
                :key="item.mediaId"
                class="media-card"
              >
                <div class="media-preview">
                  <img
                    v-if="item.mediaType === 'image' && mediaUrls[item.mediaId]"
                    :src="mediaUrls[item.mediaId]"
                  /><video
                    v-else-if="
                      item.mediaType === 'video' && mediaUrls[item.mediaId]
                    "
                    :src="mediaUrls[item.mediaId]"
                    controls
                    preload="metadata"
                  ></video>
                  <div v-else class="media-placeholder">
                    <el-icon
                      ><PictureFilled
                        v-if="item.mediaType === 'image'" /><VideoCameraFilled
                        v-else /></el-icon
                    ><span>{{
                      item.fileAvailable
                        ? $t("results.loading_media")
                        : $t("results.media_unavailable")
                    }}</span>
                  </div>
                  <span class="media-variant">{{ item.variant }}</span>
                </div>
                <div class="media-info">
                  <div>
                    <b>{{ mediaPurpose(item.purpose) }}</b
                    ><span>{{ formatTime(item.capturedAtMs) }}</span>
                  </div>
                  <p>
                    {{ item.width || "-" }} × {{ item.height || "-" }} ·
                    {{ formatBytes(item.sizeBytes)
                    }}<template v-if="item.durationMs">
                      · {{ duration(item.durationMs) }}</template
                    >
                  </p>
                  <el-button
                    :disabled="!item.fileAvailable"
                    link
                    type="primary"
                    :icon="Download"
                    @click="downloadMedia(item)"
                    >{{ $t("button.download") }}</el-button
                  >
                </div>
              </article>
            </div>
            <el-empty v-else :description="$t('results.no_media')" />
          </el-tab-pane>
          <el-tab-pane :label="$t('results.tabs.config')" name="config"
            ><div class="config-view">
              <div class="config-heading">
                <div>
                  <h3>{{ $t("results.sop_snapshot") }}</h3>
                  <p>{{ $t("results.sop_snapshot_hint") }}</p>
                </div>
                <el-tag>{{ detail.run?.sopVersion || "-" }}</el-tag>
              </div>
              <pre>{{ prettyJson(detail.run?.sopConfig || {}) }}</pre>
            </div></el-tab-pane
          >
        </el-tabs>
      </div>
    </el-drawer>
  </el-container>



  <!-- <div class="results-page" v-loading="loading"> -->
  <!-- </div> -->




    <!-- <header class="app-header">
      <div class="brand">
        <b>{{ $t("public.faivs") }}</b> > 
        <b>{{ $t("results.title") }}</b>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" circle @click="loadAll" /><el-dropdown
          trigger="click"
          @command="langChange"
          ><span class="language"
            >{{ currentLanguage }}<el-icon><ArrowDown /></el-icon></span
          ><template #dropdown
            ><el-dropdown-menu
              ><el-dropdown-item command="en">English</el-dropdown-item
              ><el-dropdown-item command="zh"
                >Chinese</el-dropdown-item
              ></el-dropdown-menu
            ></template
          ></el-dropdown
        ><img src="@/assets/img/bosch.26cf9c8e.svg" alt="Bosch" />
      </div>
    </header> -->

    
  <!-- </div> -->
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeMount,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
} from "vue";
import { useI18n } from "vue-i18n";
import { useAppStore } from "@/stores/store";
import { ElMessage } from "element-plus";
import {
  ArrowDown,
  CircleCheckFilled,
  DataAnalysis,
  Download,
  Finished,
  InfoFilled,
  PictureFilled,
  Refresh,
  RefreshLeft,
  Search,
  User,
  VideoCameraFilled,
  View,
  WarningFilled,
} from "@element-plus/icons-vue";
import dayjs from "dayjs";
import api from "@/api/index";
import { translateSopReason } from "@/assets/js/sopReason";

const appStore = useAppStore();
const { t,te,locale } = useI18n();
const loading = ref(false);
const detailLoading = ref(false);
const exporting = ref(false);
const currentLanguage = ref("English");
const lastUpdated = ref(Date.now());
const summary = reactive({
  total: 0,
  completed: 0,
  ok: 0,
  deviation: 0,
  incomplete: 0,
  running: 0,
  withMedia: 0,
  mediaCount: 0,
  completionRate: 0,
  firstPassRate: 0,
});
const overview = reactive<any>({
  trend: [],
  sopRanking: [],
  options: { sopNames: [], cameraNames: [] },
  storage: null,
});
const resultData = reactive<any>({ items: [], total: 0 });
const pagination = reactive({ page: 1, pageSize: 20 });
const filters = reactive<any>({
  keyword: "",
  dateRange: [
    dayjs().subtract(29, "day").startOf("day").valueOf(),
    dayjs().endOf("day").valueOf(),
  ],
  sopName: "",
  cameraName: "",
  executionStatus: "",
  qualityStatus: "",
  hasMedia: "",
});
const executionOptions = ["completed", "running", "stopped", "reset", "failed"];
const qualityOptions = ["ok", "with_deviation", "incomplete"];
const detailVisible = ref(false);
const detailTab = ref("overview");
const detail = reactive<any>({
  run: null,
  steps: [],
  events: [],
  media: [],
  catalog: null,
  storage: null,
});
const mediaUrls = reactive<Record<string, string>>({});
const trend = computed(() => (overview.trend || []).slice(-14));
const ranking = computed(() => overview.sopRanking || []);
const trendMax = computed(() =>
  Math.max(1, ...trend.value.map((item: any) => item.total || 0))
);
const detailPassRate = computed(() =>
  rate(
    (detail.steps || []).filter((item: any) => item.result === "completed")
      .length,
    detail.steps?.length || 0
  )
);
const mediaBytes = computed(() =>
  (detail.media || []).reduce(
    (sum: number, item: any) => sum + Number(item.sizeBytes || 0),
    0
  )
);
const timeBreakdown = computed(() => [
  {
    key: "active",
    label: t("results.active_time"),
    value: detail.run?.activeDurationMs || 0,
    color: "#007bc0",
  },
  {
    key: "paused",
    label: t("results.paused_time"),
    value: detail.run?.pausedDurationMs || 0,
    color: "#8a63d2",
  },
  {
    key: "blocked",
    label: t("results.blocked_time"),
    value: detail.run?.blockedDurationMs || 0,
    color: "#e26b3a",
  },
]);
const localizedReason = (source:any) => translateSopReason(source,{t,te,locale});
const localizedEventReason = (event:any) => translateSopReason({reasonCode:event?.details?.reason_code,reasonParams:event?.details?.reason_params,reason:event?.message},{t,te,locale});

onBeforeMount(() => {
  currentLanguage.value = appStore.locale === "zh" ? "Chinese" : "English";
  locale.value = appStore.locale;
});
onMounted(() => {
  document.title = `${t("public.faivs")} [${t("results.title")}]`;
  loadAll();
});
onBeforeUnmount(clearMediaUrls);
const langChange = (lang: string) => {
  appStore.setLocale(locale, lang);
  currentLanguage.value = appStore.locale === "zh" ? "Chinese" : "English";
};
const params = () => ({
  keyword: filters.keyword.trim(),
  start_ms: filters.dateRange?.[0] ? Number(filters.dateRange[0]) : 0,
  end_ms: filters.dateRange?.[1] ? Number(filters.dateRange[1]) : 0,
  sop_name: filters.sopName,
  camera_name: filters.cameraName,
  execution_status: filters.executionStatus,
  quality_status: filters.qualityStatus,
  has_media: filters.hasMedia === "" ? undefined : filters.hasMedia === "true",
});
const loadOverview = async () => {
  const response = await api.getResultOverview(params());
  Object.assign(summary, response.data?.data?.summary || {});
  Object.assign(overview, response.data?.data || {});
};
const loadResults = async () => {
  const response = await api.getResults({
    ...params(),
    page: pagination.page,
    page_size: pagination.pageSize,
  });
  Object.assign(resultData, response.data?.data || { items: [], total: 0 });
  console.log("resultData", resultData);
};
const changePageSize = () => {
  pagination.page = 1;
  loadResults();
};
const loadAll = async () => {
  loading.value = true;
  try {
    await Promise.all([loadOverview(), loadResults()]);
    lastUpdated.value = Date.now();
  } catch (error: any) {
    ElMessage.error(
      error?.response?.data?.detail ||
        error?.message ||
        t("results.load_failed")
    );
  } finally {
    loading.value = false;
  }
};
const search = async () => {
  pagination.page = 1;
  await loadAll();
};
const resetFilters = () => {
  Object.assign(filters, {
    keyword: "",
    dateRange: [
      dayjs().subtract(29, "day").startOf("day").valueOf(),
      dayjs().endOf("day").valueOf(),
    ],
    sopName: "",
    cameraName: "",
    executionStatus: "",
    qualityStatus: "",
    hasMedia: "",
  });
  search();
};
const openDetail = async (row: any) => {
  detailVisible.value = true;
  detailLoading.value = true;
  detailTab.value = "overview";
  clearMediaUrls();
  try {
    const response = await api.getResultDetail(row.runId);
    Object.assign(detail, response.data?.data || {});
  } catch (error: any) {
    ElMessage.error(
      error?.response?.data?.detail ||
        error?.message ||
        t("results.detail_failed")
    );
  } finally {
    detailLoading.value = false;
  }
};
const handleDetailTab = (name: any) => {
  if (String(name) === "evidence") loadMediaPreviews();
};
const loadMediaPreviews = async () => {
  await Promise.all(
    (detail.media || [])
      .filter((item: any) => item.fileAvailable && !mediaUrls[item.mediaId])
      .map(async (item: any) => {
        try {
          const response = await api.getResultMedia(
            detail.run.runId,
            item.mediaId
          );
          mediaUrls[item.mediaId] = URL.createObjectURL(response.data);
        } catch {}
      })
  );
};
function clearMediaUrls() {
  Object.values(mediaUrls).forEach((url) => URL.revokeObjectURL(url));
  Object.keys(mediaUrls).forEach((key) => delete mediaUrls[key]);
}
const downloadMedia = async (item: any) => {
  try {
    const response = await api.getResultMedia(
      detail.run.runId,
      item.mediaId,
      true
    );
    saveBlob(
      response.data,
      item.relativePath?.split(/[\\/]/).pop() ||
        `${item.mediaId}.${item.mediaType === "video" ? "mp4" : "jpg"}`
    );
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message);
  }
};
const exportData = async () => {
  exporting.value = true;
  try {
    const response = await api.exportResults(params());
    saveBlob(
      response.data,
      `FAIVS_SOP_Results_${dayjs().format("YYYYMMDD_HHmmss")}.csv`
    );
    if (response.headers["x-export-truncated"] === "true")
      ElMessage.warning(t("results.export_truncated"));
    else ElMessage.success(t("results.export_success"));
  } catch (error: any) {
    ElMessage.error(
      error?.response?.data?.detail ||
        error?.message ||
        t("results.export_failed")
    );
  } finally {
    exporting.value = false;
  }
};
const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};
const executionType = (status: string) =>
  (({
    completed: "success",
    running: "primary",
    stopped: "warning",
    reset: "info",
    failed: "danger",
    cancelled: "info",
  }[status] || "info") as any);
const knownExecution = (value: string) =>
  executionOptions.includes(value) || value === "cancelled" ? value : "unknown";
const knownQuality = (value: string) =>
  qualityOptions.includes(value) ? value : "unknown";
const stepType = (step: any) =>
  step.result === "completed"
    ? step.ngCount
      ? "warning"
      : "success"
    : step.result === "running"
    ? "primary"
    : "danger";
const rate = (value: any, total: any) =>
  Number(total) > 0
    ? Math.round((Number(value || 0) * 100) / Number(total))
    : 0;
const percent = (value: any) => `${Number(value || 0).toFixed(1)}%`;
const number = (value: any) =>
  new Intl.NumberFormat().format(Number(value || 0));
const barHeight = (value: any) =>
  Math.max(
    Number(value) ? 7 : 0,
    Math.round((Number(value || 0) * 100) / trendMax.value)
  );
const duration = (value: any) => {
  const ms = Math.max(0, Number(value || 0));
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
};
const runDuration = (run: any) =>
  Number(
    run?.totalDurationMs ||
      (run?.endedAtMs || Date.now()) - Number(run?.startedAtMs || Date.now())
  );
const formatTime = (value: any) =>
  value ? dayjs(Number(value)).format("YYYY-MM-DD HH:mm:ss") : "-";
const formatDate = (value: any) =>
  value ? dayjs(Number(value)).format("YYYY-MM-DD") : "-";
const formatClock = (value: any) =>
  value ? dayjs(Number(value)).format("HH:mm:ss") : "-";
const shortDay = (value: string) => dayjs(value).format("MM/DD");
const shortId = (value: string) =>
  value ? `${value.slice(0, 8)}…${value.slice(-5)}` : "-";
const formatBytes = (value: any) => {
  const bytes = Number(value || 0);
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), 3);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};
const triggerName = (value: string) =>
  value
    ? t(
        `results.triggers.${
          ["manual", "http", "usb", "modbus", "external_api", "reset"].includes(
            value
          )
            ? value
            : "other"
        }`
      )
    : "-";
const stepResult = (value: string) =>
  t(
    `results.step_result.${
      [
        "completed",
        "running",
        "blocked",
        "stopped",
        "reset",
        "failed",
        "retrying",
      ].includes(value)
        ? value
        : "unknown"
    }`
  );
const eventAliases: Record<string, string> = {
  PICKUP_DETECTED: "results.pickup",
  STEP_BLOCKED: "results.event.BLOCKED",
  BLOCK_CLEARED: "results.event.UNBLOCKED",
};
const knownEventTypes = [
  "RUN_STARTED",
  "RUN_FINISHED",
  "STEP_STARTED",
  "STEP_COMPLETED",
  "CYCLE_STARTED",
  "CYCLE_COMPLETED",
  "OPERATION_ERROR",
  "PAUSED",
  "RESUMED",
  "BLOCKED",
  "UNBLOCKED",
];
const eventType = (value: string) =>
  eventAliases[value]
    ? t(eventAliases[value])
    : knownEventTypes.includes(value)
    ? t(`results.event.${value}`)
    : value || t("results.event.other");
const mediaPurpose = (value: string) =>
  t(
    `results.media_purpose.${
      ["operation_error", "step_success", "run_completed"].includes(value)
        ? value
        : "other"
    }`
  );
const prettyJson = (value: any) => JSON.stringify(value ?? {}, null, 2);
</script>

<style scoped lang="scss">
.el-container {
  height: 100vh;
}
.el-header{
  display: flex;
  align-items: center;
  border-bottom: 1px solid #c5c8cb;
  .header-left {
    display: flex;
    align-items: center;
    width: 40%;
    font-size: 20px;
    font-family: var(--fontFamilyBold);
  }
  .header-right {
    width: 70%;
    overflow: hidden;
    display: flex;
    align-items: center;
    flex-direction: row-reverse;
    color: var(--text-color);
    .el-dropdown {
      font-size: 18px;
      margin-right: 20px;
      white-space: nowrap;
      .el-icon--right {
        vertical-align: bottom;
      }
    }
  }
}
.el-main{
  height: calc(100% - 100px);
  overflow-y: auto;
}
.results-content {
  width: min(1740px, calc(100% - 44px));
  margin: 0 auto;
  padding: 22px 0 44px;
}
.hero-panel {
  min-height: 154px;
  padding: 30px 36px;
  color: #fff;
  &:before {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
      120deg,
      rgba(16, 37, 54, 0.9),
      rgba(21, 62, 89, 0.9) 58%,
      rgba(7, 95, 134, 0.9)
    );
    z-index: 0;
  }
  background-image: url("@/assets/img/FAIVS.jpg");
  background-size: inherit;
  background-position: center;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  box-shadow: 0 15px 35px rgba(9, 45, 68, 0.2);
  position: relative;
  overflow: hidden;

  > * {
    position: relative;
    z-index: 1;
  }
}
.hero-panel:after {
  content: "";
  position: absolute;
  width: 380px;
  height: 380px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 50%;
  right: -80px;
  top: -220px;
  z-index: 0;
}
.eyebrow{
  color: #5bd2ff;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1.7px;
}
.eyebrow {
  display: flex;
  align-items: center;
  gap: 8px;
}
.eyebrow span {
  width: 24px;
  height: 2px;
  background: #5bd2ff;
}
.hero-panel h1 {
  margin: 10px 0 6px;
  font-size: 31px;
  letter-spacing: 0.3px;
}
.hero-panel p {
  margin: 0;
  color: #c6d8e5;
}
.hero-meta {
  text-align: right;
  color: #bcd1df;
  font-size: 12px;
  z-index: 1;
}
.live-dot {
  margin-bottom: 10px;
  color: #fff;
  font-weight: 700;
}
.live-dot i {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #49d9a0;
  margin-right: 8px;
  box-shadow: 0 0 0 6px rgba(73, 217, 160, 0.15);
}
.storage-alert {
  margin-top: 14px;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 18px 0;
}
.kpi-card {
  background: #fff;
  padding: 22px;
  display: flex;
  align-items: center;
  
  gap: 30px;
  border: 1px solid #e5eaf0;
  box-shadow: 0 7px 20px rgba(26, 52, 73, 0.06);
  position: relative;
  overflow: hidden;
}
.kpi-card:before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  background: var(--accent);
}

.kpi-card span,
.kpi-card small {
  display: block;
}
.kpi-card strong {
  display: block;
  font-size: 29px;
  line-height: 1.2;
  margin: 4px 0;
}
.kpi-card small {
  font-size: 11px;
}
.kpi-blue {
  --accent: var(--bs-primary-color);
}
.kpi-green {
  --accent: var(--bs-success-color);
}
.kpi-violet {
  --accent: var(--bs-purple-color);
}
.kpi-orange {
  --accent: var(--bs-danger-color);
}
.insight-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
.panel {
  background: #fff;
  border: 1px solid #e1e7ed;
  box-shadow: 0 6px 18px rgba(25, 48, 69, 0.05);
}
.trend-panel,
.ranking-panel,
.query-panel {
  padding: 22px 24px;
}
.panel-heading,
.table-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.panel-heading h3,
.table-title h3 {
  margin: 4px 0 0;
  font-size: 18px;
}

.legend {
  display: flex;
  gap: 18px;
  color: #6c7a88;
  font-size: 12px;
}
.legend i {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 6px;
}
.legend .ok {
  background: var(--bs-success-color);
}
.legend .ng {
  background: var(--bs-danger-color);
}
.trend-chart {
  height: 190px;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding-top: 22px;
}
.trend-column {
  flex: 1;
  min-width: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}
.trend-column span,
.trend-value {
  font-size: 10px;
}
.trend-bar {
  width: min(28px, 70%);
  height: 135px;
  display: flex;
  flex-direction: column-reverse;
  background: #eef3f6;
  overflow: hidden;
}
.trend-bar i {
  width: 100%;
  min-height: 0;
}
.bar-ok {
  background: var(--bs-success-color);
}
.bar-ng {
  background: var(--bs-danger-color);
}
.ranking-list {
  margin-top: 14px;
}
.ranking-item {
  display: grid;
  grid-template-columns: 30px 1fr 46px;
  gap: 10px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #edf0f3;
}
.ranking-item:last-child {
  border: 0;
}
.rank {
  font: 700 12px monospace;
  color: #98a4af;
}
.rank-content > div {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}
.rank-content b {
  font-size: 13px;
}
.rank-content span,
.ranking-item small {
  // color: #6d7a86;
  font-size: 11px;
}
.ranking-item small {
  text-align: right;
}
.query-panel {
  margin-bottom: 16px;
}
.filter-grid {
  display: grid;
  grid-template-columns: 1.35fr 1.65fr repeat(5, 1fr) auto;
  gap: 20px;
  margin-top: 18px;
}
.filter-grid :deep(.el-date-editor) {
  width: 100%;
}
.filter-actions {
  display: flex;
  white-space: nowrap;
}
.table-panel {
  overflow: hidden;
}
.table-title {
  padding: 19px 22px;
  border-bottom: 1px solid #e5e9ed;
}
.table-title h3 {
  display: inline-block;
  margin-right: 12px;
}
.table-title > div > span {
  color: #7a8793;
  font-size: 12px;
}
.table-legend {
  display: flex;
  gap: 16px;
}
.source {
  font-size: 11px;
}
.source:before {
  content: "";
  display: inline-block;
  width: 7px;
  height: 7px;
  // border-radius: 50%;
  margin-right: 6px;
}
.source.configured:before {
  background: var(--bs-primary-color);
}
.source.local:before {
  background: var(--bs-danger-color);
}
.source-line {
  display: block;
  width: 3px;
  height: 34px;
  background: var(--bs-primary-color) !important;
}
.source-line.local {
  background: var(--bs-danger-color) !important;
}
.result-table :deep(.el-table__cell) {
  padding: 13px 0;
}
.status-stack,
.primary-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}
.status-stack .el-tag {
  min-width: 78px;
  justify-content: center;
}
.quality-text {
  font-size: 11px;
  font-weight: 700;
  color: #778591;
}
.quality-text.ok {
  color: #008f66;
}
.quality-text.with_deviation {
  color: #d55c2b;
}
.primary-cell b {
  color: #172b3b;
}
.primary-cell small {
  color: #8995a0;
  font-size: 10px;
}
.icon-cell {
  display: flex;
  align-items: center;
  gap: 7px;
}
.icon-cell .el-icon {
  color: #007bc0;
}
.progress-cell > div {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}
.progress-cell small {
  color: #d55c2b;
}
.mono {
  font-family: Consolas, monospace;
}
.media-icon {
  font-size: 22px;
  color: #aab3bb;
}
// .results-page 
:deep(.evidence-col .cell) {
  overflow: visible;
}

.media-icon.active {
  color: #007bc0;
}
.pagination {
  padding: 16px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid #edf0f2;
}
.drawer-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 18px;
}
.drawer-header span {
  color: #778590;
  font-size: 12px;
}
.drawer-header h2 {
  margin: 3px 0 0;
  color: #172b3b;
}
.drawer-status {
  display: flex;
  align-items: center;
  gap: 14px;
}
.drawer-body {
  min-height: 500px;
}
.detail-hero {
  display: grid;
  grid-template-columns: 140px 1.6fr repeat(3, 1fr);
  align-items: center;
  border: 1px solid #000;
  border-top: 4px solid #007bc0;
  padding: 18px 22px;
  // background: linear-gradient(100deg, #f5fbfe, #fff 60%);
}
.detail-score :deep(.el-progress__text) {
  display: flex;
  flex-direction: column;
}
.detail-score strong {
  font-size: 23px;
}
.detail-score span {
  font-size: 10px;
  // color: #778590;
}
.detail-identity {
  padding: 0 24px;
  border-right: 1px solid #dfe5ea;
}
.detail-identity span,
.detail-stat span,
.detail-stat small {
  color: #74818d;
  font-size: 11px;
}
.detail-identity h3 {
  margin: 5px 0;
  font-size: 22px;
}
.detail-identity p {
  margin: 0;
  color: #60717f;
}
.detail-stat {
  padding-left: 24px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.detail-stat strong {
  font-size: 22px;
}
.detail-stat.danger strong {
  color: #dc5c32;
}
.detail-tabs {
  margin-top: 18px;
}
.overview-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 16px;
}
.detail-panel {
  // border: 1px solid #e1e6eb;
  border: 1px solid #000;
  padding: 19px;
}
.detail-panel h3 {
  margin: 0 0 15px;
}
.detail-panel.full {
  grid-column: 1/-1;
}
.time-bars > div {
  margin-bottom: 16px;
}
.time-bars > div > div {
  display: flex;
  justify-content: space-between;
  margin-bottom: 7px;
}
.reason-box {
  padding: 15px;
  background: #eef8f4;
  color: #25765c;
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.reason-box.danger {
  background: #fff3ed;
  color: #aa4b28;
}
.step-timeline {
  padding: 12px 10px 0;
}
.step-card {
  border: 1px solid #dfe6eb;
  border-left: 4px solid #007bc0;
  padding: 17px 20px;
  box-shadow: 0 5px 15px rgba(23, 52, 73, 0.04);
}
.step-heading {
  display: grid;
  grid-template-columns: 38px 1fr auto;
  gap: 13px;
  align-items: center;
}
.step-order {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  background: #e8f4fa;
  color: #007bc0;
  font-weight: 800;
}
.step-heading h3 {
  margin: 0 0 4px;
}
.step-heading p {
  margin: 0;
  color: #75828d;
  font-size: 12px;
}
.step-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  margin: 16px 0 10px;
  background: #f5f7f9;
}
.step-metrics span {
  padding: 11px 15px;
  border-right: 1px solid #e2e7eb;
  color: #77848f;
  font-size: 11px;
}
.step-metrics span:last-child {
  border: 0;
}
.step-metrics b {
  display: block;
  color: #213746;
  font-size: 15px;
  margin-bottom: 3px;
}
.step-metrics .danger b,
.textDanger {
  color: #d6532a;
}
.event-list {
  display: grid;
  gap: 10px;
}
.event-card {
  display: grid;
  grid-template-columns: 40px 1fr;
  gap: 14px;
  padding: 15px 17px;
  border: 1px solid #e1e6ea;
  border-left: 4px solid #7d8a95;
}
.event-card.error {
  border-left-color: #d95332;
  background: #fff9f6;
}
.event-card.warning {
  border-left-color: #e89a2c;
}
.event-card.info {
  border-left-color: #007bc0;
}
.event-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  background: #eef3f6;
  border-radius: 50%;
  font-size: 18px;
}
.event-heading {
  display: flex;
  justify-content: space-between;
}
.event-heading span {
  color: #7d8994;
  font-size: 11px;
}
.event-card p {
  margin: 7px 0;
}
.event-card pre,
.config-view pre {
  background: #122330;
  color: #cce5f2;
  padding: 14px;
  overflow: auto;
  font: 12px/1.55 Consolas, monospace;
}
.media-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.media-card {
  border: 1px solid #dfe5ea;
  background: #fff;
  overflow: hidden;
}
.media-preview {
  height: 220px;
  background: #142532;
  display: grid;
  place-items: center;
  position: relative;
}
.media-preview img,
.media-preview video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.media-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #91a6b5;
}
.media-placeholder .el-icon {
  font-size: 42px;
}
.media-variant {
  position: absolute;
  left: 10px;
  top: 10px;
  padding: 4px 8px;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  font-size: 10px;
  text-transform: uppercase;
}
.media-info {
  padding: 13px;
}
.media-info > div {
  display: flex;
  justify-content: space-between;
}
.media-info span,
.media-info p {
  color: #7b8893;
  font-size: 11px;
}
.media-info p {
  margin: 8px 0 4px;
}
.config-view {
  border: 1px solid #e0e6eb;
}
.config-heading {
  padding: 18px;
  display: flex;
  justify-content: space-between;
}
.config-heading h3 {
  margin: 0 0 5px;
}
.config-heading p {
  margin: 0;
  color: #75828d;
}
.config-view pre {
  margin: 0;
  max-height: 570px;
}
.results-page :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 17px 22px;
  border-bottom: 1px solid #dfe5ea;
}
.results-page :deep(.el-drawer__body) {
  padding: 18px 22px;
  background: #f5f7f9;
}
.results-page :deep(.el-tabs__content) {
  padding-top: 10px;
}
.results-page :deep(.el-tabs__item.is-active) {
  font-weight: 700;
}
@media (max-width: 1350px) {
  .filter-grid {
    grid-template-columns: repeat(4, 1fr);
  }
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .detail-hero {
    grid-template-columns: 120px 1.5fr repeat(2, 1fr);
  }
  .detail-hero .detail-stat:last-child {
    display: none;
  }
}
@media (max-width: 900px) {
  .results-content {
    width: calc(100% - 20px);
  }
  .insight-grid,
  .overview-grid {
    grid-template-columns: 1fr;
  }
  .kpi-grid {
    grid-template-columns: 1fr;
  }
  .filter-grid {
    grid-template-columns: 1fr 1fr;
  }
  .media-grid {
    grid-template-columns: 1fr;
  }
  .detail-hero {
    grid-template-columns: 1fr 1fr;
  }
  .detail-score {
    display: none;
  }
  .detail-identity {
    border: 0;
    padding: 0;
  }
  .hero-meta {
    display: none;
  }
}
</style>
