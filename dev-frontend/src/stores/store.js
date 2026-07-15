import { defineStore } from 'pinia'

export const useAppStore = defineStore('FAIVS-A', {
  state: () => ({
    servicePort: 20253,
    version:"0.0.1",
    locale: "en",
    isCollapse: false,
    menuIndex: 0,
    loading: false,
  }),
  actions: {
    setLocale(locale, lang) {
      this.locale = lang;
      locale.value = lang
    },
    setCollapse(isCollapse) {
      this.isCollapse = isCollapse;
    },
    setMenuIndex(index) {
      this.menuIndex = index;
    },
    setLoading(loading){
      this.loading = loading
    },
  },
  persist: {
    pick: ['locale','isCollapse']
  }
})
