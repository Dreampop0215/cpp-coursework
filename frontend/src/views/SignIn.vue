<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import SignBrand from '../components/SignBrand.vue'
import { useAuth } from '../auth.js'
import { errorText, post } from '../api.js'

const auth = useAuth()
const router = useRouter()
const registration = ref(false)
const busy = ref(false)
const message = ref('')
const form = reactive({ username: '', password: '' })
const title = computed(() => registration.value ? '创建账户' : '登录你的厨房')

function switchMode() {
  registration.value = !registration.value
  message.value = ''
  form.password = ''
}

async function submit() {
  if (busy.value) return
  message.value = ''
  const username = form.username.trim()
  if (!username || Array.from(username).length > 50) {
    message.value = '用户名长度须为 1～50 个字符。'
    return
  }
  if (Array.from(form.password).length < 8 || Array.from(form.password).length > 128) {
    message.value = '密码长度须为 8～128 个字符。'
    return
  }
  busy.value = true
  try {
    const credentials = { username, password: form.password }
    if (registration.value) await post('/auth/register', credentials)
    await auth.signIn(credentials)
    router.replace({ name: 'dashboard' })
  } catch (error) {
    message.value = errorText(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="sign-screen">
    <section class="sign-photo">
      <SignBrand />
      <div class="sign-caption">
        <h1>家庭食材管理</h1>
        <p>记录库存、优先用掉临期食材，按菜谱补齐采购缺口。</p>
      </div>
    </section>
    <section class="sign-body">
      <div class="sign-form">
        <h2>{{ title }}</h2>
        <el-form label-position="top" @submit.prevent="submit">
          <el-form-item label="用户名">
            <el-input v-model="form.username" size="large" autocomplete="username" placeholder="输入用户名" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="form.password" size="large" type="password" show-password
              :autocomplete="registration ? 'new-password' : 'current-password'" placeholder="输入 8～128 位密码"
            />
          </el-form-item>
          <el-alert v-if="message" :title="message" type="error" :closable="false" show-icon class="form-alert" />
          <el-button class="sign-submit" type="primary" size="large" native-type="submit" :loading="busy">
            {{ registration ? '注册并登录' : '登录' }}
          </el-button>
        </el-form>
        <div class="sign-switch">
          {{ registration ? '已有账户？' : '第一次使用？' }}
          <el-button link type="primary" :disabled="busy" @click="switchMode">
            {{ registration ? '返回登录' : '创建账户' }}
          </el-button>
        </div>
      </div>
    </section>
  </main>
</template>
