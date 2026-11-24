import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ElAlert, ElButton, ElCheckbox, ElConfigProvider, ElDialog, ElEmpty, ElForm,
  ElFormItem, ElInput, ElInputNumber, ElLoading, ElOption, ElSelect, ElSkeleton, ElTag,
} from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import { makeRouter } from './router.js'
import './styles.css'

const app = createApp(App)
const pinia = createPinia()
const components = [
  ElAlert, ElButton, ElCheckbox, ElConfigProvider, ElDialog, ElEmpty, ElForm,
  ElFormItem, ElInput, ElInputNumber, ElOption, ElSelect, ElSkeleton, ElTag,
]
for (const component of components) app.use(component)
app.use(ElLoading)
app.use(pinia)
app.use(makeRouter(pinia))
app.mount('#app')
