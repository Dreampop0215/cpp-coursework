import { createRouter, createWebHistory } from 'vue-router'
import {
  Box, Collection, DataAnalysis, Food, House, List, MagicStick, Setting,
} from '@element-plus/icons-vue'
import { useAuth } from './auth.js'
import { onSessionExpired } from './api.js'

export const primaryPages = [
  { name: 'dashboard', label: '厨房总览', icon: House },
  { name: 'inventory', label: '库存管理', icon: Box },
  { name: 'recommendations', label: '智能推荐', icon: MagicStick },
  { name: 'shopping', label: '采购清单', icon: List },
  { name: 'waste', label: '浪费记录', icon: DataAnalysis },
]

export const managementPages = [
  { name: 'catalog', label: '食材与分类', icon: Food },
  { name: 'recipes', label: '菜谱管理', icon: Collection },
  { name: 'preferences', label: '偏好设置', icon: Setting },
]

const pages = {
  dashboard: () => import('./views/Dashboard.vue'),
  inventory: () => import('./views/Inventory.vue'),
  recommendations: () => import('./views/Recommendations.vue'),
  shopping: () => import('./views/Shopping.vue'),
  waste: () => import('./views/Waste.vue'),
  catalog: () => import('./views/Catalog.vue'),
  recipes: () => import('./views/Recipes.vue'),
  preferences: () => import('./views/Preferences.vue'),
}

export function makeRouter(pinia) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/login', name: 'login', component: () => import('./views/SignIn.vue'), meta: { label: '登录' } },
      {
        path: '/', component: () => import('./components/AppShell.vue'), redirect: { name: 'dashboard' },
        children: [...primaryPages, ...managementPages].map(({ name, label }) => ({
          path: name, name, component: pages[name], meta: { label },
        })),
      },
      { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } },
    ],
    scrollBehavior: () => ({ top: 0 }),
  })
  const auth = useAuth(pinia)
  router.beforeEach(async (to) => {
    await auth.restore()
    if (to.name !== 'login' && !auth.user) return { name: 'login' }
    if (to.name === 'login' && auth.user) return { name: 'dashboard' }
  })
  router.afterEach((to) => { document.title = `${to.meta.label || '厨房总览'} · 食尽其用` })
  onSessionExpired(() => {
    auth.clear()
    if (router.currentRoute.value.name !== 'login') router.replace({ name: 'login' })
  })
  return router
}
