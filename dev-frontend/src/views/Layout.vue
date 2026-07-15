<template>
  <div class="common-layout">
    <el-container>
      <el-aside :class="{ 'el-aside-close': isCollapse }">
        <div class="menu-title-close el-menu--collapse" :class="{ 'menu-title-open': !isCollapse }" >
          <span></span>
          <div class="sider-title" style="" v-show="!isCollapse">{{ $t("public.faivs") }}</div>
          <span></span>
          <el-icon size="30px" style="height: 100%; cursor: pointer" @click="menuCollapse">
            <Expand v-show="isCollapse" />
            <Close v-show="!isCollapse"/>
          </el-icon>
        </div>
        <el-menu :default-active="currentMenu" :collapse-transition="false" class="el-menu-vertical-demo menu-top" :collapse="isCollapse"  background-color="#2e3033" active-text-color="#fff" text-color="#fff" style="border-right: none; overflow-y: auto"  @select="changeMenu">
          <el-menu-item v-for="(item, index) in menuItems" :key="index" :index="index.toString()" style="--el-menu-item-font-size: 16px">
            <el-icon>
              <component :is="item.icon" />
            </el-icon>
            <template #title>{{ t(`menu.${item.title}`) }}</template>
          </el-menu-item>
        </el-menu>
        <el-menu :collapse-transition="false" class="el-menu-vertical-demo menu-bottom el-menu-vertical-bottom" :collapse="isCollapse" background-color="#2e3033" active-text-color="#fff" text-color="#fff" style="border-right: none;overflow-y: auto;" @select="changeMenuBottom">
          <el-menu-item index="4" style="--el-menu-item-font-size: 16px">
            <el-icon><Clock /></el-icon>
            <template #title>{{ $t("menu.historyresult") }}</template>
          </el-menu-item>
          <el-menu-item index="3" style="--el-menu-item-font-size: 16px">
            <el-icon><List /></el-icon>
            <template #title>{{ $t("menu.syslog") }}</template>
          </el-menu-item>
          <el-menu-item index="1" style="--el-menu-item-font-size: 16px">
            <el-icon><Message /></el-icon>
            <template #title>{{ $t("menu.support") }}</template>
          </el-menu-item>
          <el-menu-item index="2" style="--el-menu-item-font-size: 16px">
            <el-icon><Guide /></el-icon>
            <template #title>{{ $t("menu.guidelines") }}</template>
          </el-menu-item>
        </el-menu>
      </el-aside>
      <el-container>
        <el-header height="50px">
          <div class="header-left">
            <b>{{ $t(`menu.${menuItems[currentMenu].title}`) }}</b>
            <el-button v-show="refreshAvalible" :icon="RefreshRight"  circle style="margin-left: 0"  @click="refreshCurrentComponent" :title="$t('button.title.refreshpage')"/>
          </div>
          <div class="header-right">
            <img src="@/assets/img/bosch.26cf9c8e.svg" style="height: 28px; vertical-align: middle" alt="" />
            <div style="margin-top: auto">
            <el-button :title="$t('button.title.fullscreen')" :icon="FullScreen" style="color: #000;margin-right: 10px;" circle @click="toggleFullscreen" />
          </div>
            <el-icon v-if="runMethod === 'electron'" @click="openBrowser" :title="$t('button.title.openinbrowser')" color="var(--bs-primary-color)" size="20" style="vertical-align: bottom;margin-right: 20px;cursor: pointer;"><ChromeFilled /></el-icon>
            <el-dropdown trigger="click"  @command="langChange" style="cursor: pointer">
              <span class="el-dropdown-link"> {{ currentLanguage }}<el-icon class="el-icon--right"><arrow-down /></el-icon></span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="en">English</el-dropdown-item>
                  <el-dropdown-item command="zh">Chinese</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-dropdown trigger="click" style="cursor: pointer">
              <span class="el-dropdown-link">
                <el-icon class="el-icon--right" style="vertical-align: middle; margin-right: 10px" ><Avatar /></el-icon>{{ loginUser }}
              </span>
              <template #dropdown>
                <el-dropdown-menu> </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </el-header>
        <el-main>
          <div style="height: 100%">
            <!-- <keep-alive> -->
              <component :is="currentComponent" v-if="currentComponent" :key="`${menuItems[currentMenu]?.title}-${componentRefreshKeys[menuItems[currentMenu]?.title] || 0}`" :changeMenu="changeMenu" :refreshAvalible="hideRefresh"/>
            <!-- </keep-alive> -->
          </div>
        </el-main>
        <el-footer>
          <i style="margin-right: 8px">©</i
          ><span>{{ $t("public.developed") }}(v-{{ appStore.version }})</span>
        </el-footer>
      </el-container>
    </el-container>
    <el-dialog v-model="contactVisible" modal-class="bs-shade" align-center :title="`${$t('description.support.title')}`">
      <h2>English</h2>
      <div style="margin-left: 24px; margin-bottom: 16px; border-left: 5px solid var(--bs-primary-color); padding-left: 12px;">
        <p><b>Contact:</b> Lauber Phillip (PkP/TEF1 PkP/TEF10)</p>
        <p><b>Email:</b> Phillip.Lauber@boschrexroth.de</p>
      </div>
      <h2>Chinese</h2>
      <div
        style="margin-left: 24px;  margin-bottom: 12px; border-left: 5px solid var(--bs-primary-color); padding-left: 12px;">
        <p><b>联系人：</b>TIAN Hao (PkP/TEF1) <i>-【业务与使用支持】</i></p>
        <p><b>邮箱：</b>Hao.Tian2@boschrexroth.com.cn</p>
      </div>
      <div style="margin-left: 24px;  margin-bottom: 0; border-left: 5px solid var(--bs-primary-color); padding-left: 12px;">
        <p><b>联系人：</b>LI Aiguo (PkP/TEF1) <i>-【技术支持】</i></p>
        <p><b>邮箱：</b>Aiguo.LI@boschrexroth.com.cn</p>
      </div>
    </el-dialog>
  </div>
</template>
<script lang="ts" setup>
import { ref, markRaw, onBeforeMount, onMounted, reactive, shallowRef } from "vue";
import { FullScreen,Camera,Expand,VideoCamera,RefreshRight,Setting,Connection,DataLine,} from "@element-plus/icons-vue";
import { useAppStore } from "@/stores/store";
import { useI18n } from "vue-i18n";
import { MesAlertWTitle } from "@/assets/js/secondpk";
import Config from "./Config.vue";
import Detection from "./Detection.vue";
import api from "@/api/index";
import { ElMessage } from "element-plus";
const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    // (fullscreenElement.value || document.body)
    document.body.requestFullscreen().then(() => {})
    .catch((err) => {
        ElMessage({message: "Failed to enter full screen: " + err.message,type: "error",});
      });
  } else {
    document.exitFullscreen().then(() => {});
  }
};
const appStore = useAppStore(); //localstorage
const isCollapse = ref(false); //sider menu open&hide
const currentMenu = ref("0"); //pagr title
const currentLanguage = ref("English"); //current language
const loginUser = ref("User"); //default User
const refreshAvalible = ref(true); //refresh avalible
const { locale } = useI18n();
const { t } = useI18n();
const runMethod=ref("electron")
const menuItems = ref([
  {icon: markRaw(VideoCamera),title: "detect",component: markRaw(Detection),},
  { icon: markRaw(Setting), title: "config", component: markRaw(Config) },
]);
// 当前选中的组件
const currentComponent = shallowRef(null);
// 已加载的组件缓存（避免重复加载）
const componentRefreshKeys = reactive({}); // 为每个组件维护独立的刷新计数
// 初始化刷新计数器
const refreshCurrentComponent = () => {
  if (currentMenu.value !== null) {
    const menuKey = menuItems.value[currentMenu.value].title;
    componentRefreshKeys[menuKey]++; // 只增加当前组件的刷新计数
  }
};
onBeforeMount(() => {
  currentLanguage.value = appStore.locale == "zh" ? "Chinese" : "English";
  locale.value = appStore.locale;
  isCollapse.value = appStore.isCollapse;
  getLoginUse();
  // loadedComponents.add(Collect);
  currentComponent.value = Detection;
  menuItems.value.forEach((item) => {
    componentRefreshKeys[item.title] = 0;
  });
});
onMounted(() => {
  if (window.electronEnv && window.electronEnv.isElectron) {
  runMethod.value = "electron";
} else {
  runMethod.value = "browser";
}
});
const langChange = (lang: string) => {
  appStore.setLocale(locale, lang);
  currentLanguage.value = appStore.locale == "zh" ? "Chinese" : "English";
};
const menuCollapse = () => {
  isCollapse.value = !isCollapse.value;
  appStore.setCollapse(isCollapse.value);
};
const hideRefresh = (val) => {refreshAvalible.value = val};
const changeMenu = async (item) => {
  currentMenu.value = item;
  currentComponent.value = menuItems.value[item].component;
  appStore.setMenuIndex(item);
  // loadedComponents.add(menuItems.value[item].component); // 记录已加载
};
const contactVisible = ref(false);
const changeMenuBottom = async (item) => {
  if (item === "1") {
    contactVisible.value = true;
  } else if (item === "2") {
    window.open(t('url.guideline'),"_blank");
  }else if (item === "3") {
    window.open("#/logs", "_blank");
  }else if (item === "4") {
    api.openResult()
      .then((res) => {
        if (res.data.status) {
          ElMessage({message: t("message.messagetext.successopen"),type: "success",});
        } else {
          MesAlertWTitle("error",t("message.error"),t("message.messagetext.failedopen"),res.data.msg,t("button.ok"));
        }
      })
      .catch((error) => {
        MesAlertWTitle("error",t("message.error"),t("message.messagetext.failedopen"),error.message,t("button.ok"));
      });
  }
};
const getLoginUse = () => {
  api
    .getLoginUser()
    .then((res) => {
      loginUser.value = res.data.username;
    })
    .catch((error) => {
      MesAlertWTitle("warning",t("message.warning"),t("message.messagetext.failed_get_user_title"),t("message.messagetext.failed_get_user_body"),t("button.ok"));
    });
};
const openBrowser=()=>{
  api.openBrowser()
}
</script>
  <style scoped>
.common-layout {
  height: 100%;
}
.el-container {
  height: 100%;
  background: #fff;
}
.el-aside {
  width: var(--sider-width);
  background-color: #2e3033;
  --el-menu-item-font-size: 16px;
  .is-active {
    background-color: #595e62;
  }
  .sider-title {
    text-align: center;
    align-content: center;
    font-family: var(--fontFamilyBold);
    font-weight: 900;
    font-size: 28px;
  }
  .menu-title-close {
    font-size: 20px;
    color: #fff;
    position: relative;
    text-align: center;
    white-space: nowrap;
    background-color: #2e3033;
    height: 60px;
  }
  .menu-title-open {
    width: calc(var(--sider-width) - 48px);
    text-align: right;
    padding: 0 24px;
    display: flex;
    justify-content: space-between;
  }
  .menu-top {
    height: calc(100% - 300px);
  }

  .menu-bottom {
    /* height: 115px; */
    height: 238px;
    border-top: 1px solid #fff;
  }
  .el-menu-vertical-demo .el-menu-item [class^="el-icon"] {
    margin-right: 12px;
    font-size: 24px;
  }
  .el-menu-vertical-bottom {
    .el-menu-item.is-active {
      background-color: transparent;
    }
  }
}
.el-aside-close {
  width: calc(
    var(--el-menu-icon-width) + var(--el-menu-base-level-padding) * 2
  ) !important;
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
  padding: 0;
  overflow: hidden;
}
.el-footer {
  height: 40px;
  border-top: 1px solid #c5c8cb;
  display: flex;
  align-items: center;
}
</style>