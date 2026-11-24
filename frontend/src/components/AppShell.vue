<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bowl, Expand, Fold, SwitchButton } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuth } from '../auth.js'
import { errorText } from '../api.js'
import { managementPages, primaryPages } from '../router.js'

const route = useRoute()
const router = useRouter()
const auth = useAuth()
const menuOpen = ref(false)
const signingOut = ref(false)
const initials = computed(() => Array.from(auth.user?.username || '食')[0].toUpperCase())
const today = new Intl.DateTimeFormat('zh-CN', {
  month: 'long', day: 'numeric', weekday: 'long', timeZone: 'Asia/Shanghai',
}).format(new Date())

watch(() => route.path, () => { menuOpen.value = false })

async function signOut() {
  signingOut.value = true
  try {
    await auth.signOut()
    router.replace({ name: 'login' })
  } catch (error) {
    if (error.response?.status !== 401) ElMessage.error(errorText(error))
  } finally {
    signingOut.value = false
  }
}
</script>

<template>
  <div class="app-shell" :class="{ 'menu-open': menuOpen }">
    <aside id="primary-navigation" class="sidebar">
      <router-link :to="{ name: 'dashboard' }" class="brand">
        <span class="brand-icon"><Bowl /></span>
        <span>食尽其用</span>
      </router-link>
      <nav aria-label="厨房操作">
        <div v-for="(group, index) in [primaryPages, managementPages]" :key="index" class="nav-group">
          <router-link v-for="page in group" :key="page.name" :to="{ name: page.name }" class="nav-link">
            <component :is="page.icon" />
            {{ page.label }}
          </router-link>
        </div>
      </nav>
      <div class="account">
        <span class="avatar" aria-hidden="true">{{ initials }}</span>
        <span class="account-name" :title="auth.user?.username">{{ auth.user?.username }}</span>
        <el-button
          :icon="SwitchButton" :loading="signingOut" circle text
          title="退出登录" aria-label="退出登录" @click="signOut"
        />
      </div>
    </aside>
    <div class="app-frame">
      <header class="topbar">
        <el-button
          class="menu-toggle" :icon="menuOpen ? Fold : Expand" text circle
          :aria-expanded="menuOpen" aria-controls="primary-navigation"
          aria-label="导航菜单" @click="menuOpen = !menuOpen"
        />
        <time class="topbar-date">{{ today }}</time>
      </header>
      <main class="main-content">
        <router-view />
      </main>
    </div>
  </div>
</template>
