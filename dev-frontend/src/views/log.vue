<template>
  <Loading v-show="myLoading" />
  <el-container>
    <el-header height="50px">
      <div class="header-left">
        <b>{{ $t("public.faivs") }} </b> >
        <p>{{ $t("log.syslog") }}</p>
      </div>
      <div class="header-right">
        <img
          src="@/assets/img/bosch.26cf9c8e.svg"
          style="height: 28px; vertical-align: middle"
          alt=""
        />
        <el-dropdown
          trigger="click"
          @command="langChange"
          style="cursor: pointer"
        >
          <span class="el-dropdown-link">
            {{ currentLanguage
            }}<el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
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
      <div style="float: right; padding: 15px">
        <el-select size="large" v-model="logLevel" style="width: 120px">
          <el-option label="ALL" value="all" />
          <el-option label="INFO" value="info" />
          <el-option label="WARNING" value="warning" />
          <el-option label="ERROR" value="error" />
          <el-option label="DEBUG" value="debug" />
        </el-select>
        <el-date-picker
          size="large"
          v-model="dateRange"
          type="daterange"
          :range-separator="$t('log.to')"
          :start-placeholder="$t('log.startdate')"
          :end-placeholder="$t('log.enddate')"
          style="margin-left: 10px; width: 300px"
        />
        <el-button type="primary" style="margin-left: 10px" @click="searchLogs">
          {{ $t("button.search") }}
        </el-button>
        <el-button plain type="primary" @click="clearLogs">{{
          $t("button.clear")
        }}</el-button>
        <el-button
          v-if="filteredLogs.length > 0"
          link
          type="primary"
          :loading="downloading"
          @click="downloadLogs"
          >{{ $t("button.download") }}</el-button
        >
      </div>
      <el-table
        :data="filteredLogs"
        border
        style="width: 100%"
        height="calc(100vh - 250px)"
        stripe
      >
        <el-table-column
          prop="timestamp"
          :label="$t('log.time')"
          width="180"
          sortable
        >
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="level"
          :label="$t('log.level')"
          width="100"
          sortable
        >
          <template #default="{ row }">
            <el-tag :type="getLevelType(row.level)" effect="dark" size="small">
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source" :label="$t('log.source')" width="150" />
        <el-table-column prop="message" :label="$t('log.msgcontent')" />
        <el-table-column :label="$t('button.operate')" width="120">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              link
              @click="showDetail(row)"
              >{{ $t("log.detail") }}</el-button
            >
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="totalLogs"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-main>
    <el-footer>
      <i style="margin-right: 8px">©</i
      ><span>{{ $t("public.developed") }}(v-{{ appStore.version }})</span>
    </el-footer>
  </el-container>
  <!-- 日志详情对话框 -->
  <el-dialog v-model="detailVisible" :title="$t('log.logdetails')" width="70%">
    <el-descriptions border :column="1">
      <el-descriptions-item :label="$t('log.time')">
        {{ formatTime(currentLog.timestamp) }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('log.level')">
        <el-tag
          :type="getLevelType(currentLog.level)"
          effect="dark"
          size="small"
        >
          {{ currentLog.level }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item :label="$t('log.source')">{{
        currentLog.source
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('log.msgcontent')">{{
        currentLog.message
      }}</el-descriptions-item>
      <el-descriptions-item :label="$t('log.detail')" v-if="currentLog.detail">
        <el-input
          type="textarea"
          :rows="8"
          readonly
          v-model="currentLog.detail"
        />
      </el-descriptions-item>
    </el-descriptions>
    <template #footer>
      <el-button type="primary" @click="detailVisible = false">{{
        $t("button.close")
      }}</el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, computed, onBeforeMount, onMounted } from "vue";
import { useAppStore } from "@/stores/store";
import { useI18n } from "vue-i18n";
import Loading from "./Loading.vue";
import { ElMessage } from "element-plus";
import dayjs from "dayjs";
import api from "@/api/index";
import { MesAlertWTitle } from "@/assets/js/secondpk";
const appStore = useAppStore();
const currentLanguage = ref("English");
const { locale } = useI18n();
const { t } = useI18n();
onBeforeMount(() => {
  currentLanguage.value = appStore.locale == "zh" ? "Chinese" : "English";
  locale.value = appStore.locale;
});
onMounted(() => {
  fetchLogs();
  document.title = document.title + " [Logs]";
});
const langChange = (lang: string) => {
  appStore.setLocale(locale, lang);
  currentLanguage.value = appStore.locale == "zh" ? "Chinese" : "English";
};

const myLoading = ref(false);
const logs = ref([]);
const filteredLogs = ref([]);
const logLevel = ref("all");
const dateRange = ref([]);
const currentPage = ref(1);
const pageSize = ref(20);
const totalLogs = ref(0);
const detailVisible = ref(false);
const currentLog = ref({});
const downloading = ref(false);

// 获取日志数据

const fetchLogs = async () => {
  myLoading.value = true;
  api.getLog().then((res) => {
      const resData = res.data;
      if (!resData) return MesAlertWTitle("error",t("message.error"),t("message.messagetext.failedget"),resData.msg );
      const logData = resData.data;
      logs.value = logData;
      totalLogs.value = logs.value.length;
      filterLogs();
    })
    .catch((error) => {MesAlertWTitle("error",t("message.error"),t("message.messagetext.failed_public_body"),error.message);})
    .finally(() => {myLoading.value = false;});
};

// 过滤日志
const filterLogs = () => {
  let result = [...logs.value];
  // 按日志级别过滤
  if (logLevel.value !== "all") {
    result = result.filter((log) => log.level === logLevel.value.toUpperCase());
  }

  // 按日期范围过滤
  if (dateRange.value && dateRange.value.length === 2) {
    const [start, end] = dateRange.value;
    result = result.filter((log) => {
      const logDate = new Date(log.timestamp);
      return logDate >= start && logDate <= end;
    });
  }

  totalLogs.value = result.length;
  // 分页处理
  const start = (currentPage.value - 1) * pageSize.value;
  filteredLogs.value = result.slice(start, start + pageSize.value);
};

// 搜索日志
const searchLogs = () => {
  currentPage.value = 1;
  filterLogs();
};

// 清空筛选条件
const clearLogs = () => {
  logLevel.value = "all";
  dateRange.value = [];
  api
    .clearLog()
    .then(() => {
      ElMessage.success(t("message.messagetext.successdelete"));
      fetchLogs();
    })
    .catch((error) => {
      ElMessage.error(t("message.messagetext.faileddelete") + error.message);
    });
};

// 显示日志详情
const showDetail = (log) => {
  currentLog.value = log;
  detailVisible.value = true;
};

// 格式化时间
const formatTime = (timestamp) => {
  return dayjs(timestamp).format("YYYY-MM-DD HH:mm:ss");
};

// 获取日志级别对应的标签类型
const getLevelType = (level) => {
  switch (level) {
    case "INFO":
      return "primary";
    case "WARNING":
      return "warning";
    case "ERROR":
      return "danger";
    case "DEBUG":
      return "info";
    default:
      return "";
  }
};

// 分页大小改变
const handleSizeChange = (val) => {
  pageSize.value = val;
  filterLogs();
};

// 当前页改变
const handleCurrentChange = (val) => {
  currentPage.value = val;
  filterLogs();
};

const downloadLogs = async () => {
  downloading.value = true;
  try {
    const response = await fetch(api.downloadLog);
    if (!response.ok) {
      ElMessage.error("Download log failed: " + response.statusText);
      throw new Error("Download log failed");
    }

    // 创建下载链接
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "FAIVS.log"; // 设置下载文件名
    document.body.appendChild(a);
    a.click();

    // 清理
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);

    ElMessage.success("Download log started");
  } catch (error) {
    ElMessage.error("Download log failed: " + error.message);
  } finally {
    downloading.value = false;
  }
};
</script>

<style scoped>
.el-container {
  height: 100%;
}
.el-header {
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

.el-main {
  padding: 0 10px;
  padding-bottom: 15px;
  overflow: hidden;
}
.el-footer {
  height: 40px;
  border-top: 1px solid #c5c8cb;
  display: flex;
  align-items: center;
}

.pagination {
  margin-top: 15px;
  display: flex;
  justify-content: flex-end;
}

.el-table {
  margin-top: 10px;
}

.el-tag {
  margin-right: 5px;
}
</style>