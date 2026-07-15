import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './assets/css/public.css';
import './assets/css/eltobs.css';
import './assets/css/fonts.css';
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import { i18n } from '@/lang/index'
const app = createApp(App)
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component)
  }
  const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)
app.use(i18n)
app.use(pinia)
app.use(router)
app.use(ElementPlus)

app.mount('#app')
