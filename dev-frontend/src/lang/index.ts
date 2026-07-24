import { createI18n } from "vue-i18n";
import zhCn from "element-plus/es/locale/lang/zh-cn"; // Element CN-package
import en from "element-plus/es/locale/lang/en"; // Element EN-package
import zh_CN from "./zh_CN"
import en_US from "./en_US";
const appLocal = localStorage.getItem("FAIVS-A");
const locale = (appLocal)?appLocal.locale:"zh" || "zh"
const i18n = createI18n({
  locale: locale,
  legacy: false,
  globalInjection: true,
  messages: {
    zh: {
      ...zh_CN,
      ...zhCn,
    },
    en: {
      ...en_US,
      ...en,
    },
  }
});
export { i18n };
 