<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { errorText, fetchAll, get, put } from '../api.js'
import LoadError from '../components/LoadError.vue'
import PageHeader from '../components/PageHeader.vue'
import { categoryLabel, confirmAction, nutrients, useQuery, validAmount } from '../utils/forms.js'

const ingredients = useQuery([])
const busy = ref(false)
const fetching = ref(false)
const ready = ref(false)
const loadError = ref('')
const message = ref('')
const form = reactive({ taste_preferences: [], avoid_ingredients: [], max_cooking_time: undefined, nutrition: {} })

function apply(data) {
  form.taste_preferences = data.taste_preferences
  form.avoid_ingredients = data.avoid_ingredients
  form.max_cooking_time = data.max_cooking_time ?? undefined
  form.nutrition = { ...data.nutrition_targets }
}

async function load() {
  fetching.value = true
  loadError.value = ''
  try {
    apply(await get('/preferences'))
    ready.value = true
  } catch (error) {
    loadError.value = errorText(error)
  } finally {
    fetching.value = false
  }
}

function loadIngredients() {
  return ingredients.run(() => fetchAll('/ingredients'))
}
onMounted(() => { load(); loadIngredients() })

async function clearFields() {
  if (!await confirmAction('清空当前表单？保存后将更新已保存的偏好。', '清空偏好', '清空表单')) return
  apply({ taste_preferences: [], avoid_ingredients: [], max_cooking_time: null, nutrition_targets: {} })
  message.value = ''
}

async function submit() {
  if (!ready.value || fetching.value || busy.value) return
  message.value = ''
  const nutrition_targets = {}
  for (const { key, label } of nutrients) {
    const value = form.nutrition[key]
    if (!value) continue
    if (!validAmount(value, .01, 99999999.99)) {
      message.value = `${label}目标须为正数，最多两位小数。`
      return
    }
    nutrition_targets[key] = value
  }
  busy.value = true
  try {
    apply(await put('/preferences', {
      taste_preferences: form.taste_preferences, avoid_ingredients: form.avoid_ingredients,
      max_cooking_time: form.max_cooking_time ?? null, nutrition_targets,
    }))
    ElMessage.success('偏好已保存')
  } catch (error) {
    message.value = errorText(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <PageHeader title="偏好设置" description="忌口食材和耗时上限用于筛选推荐菜谱。" />
  <LoadError :message="loadError" @retry="load" />
  <LoadError :message="ingredients.error.value" @retry="loadIngredients" />
  <section v-if="ready || fetching" class="panel preference-panel" v-loading="fetching || busy">
    <el-form v-if="ready" label-position="top" @submit.prevent="submit">
      <el-alert v-if="message" class="form-alert" :title="message" type="error" :closable="false" show-icon />
      <el-form-item label="喜欢的口味">
        <el-select v-model="form.taste_preferences" multiple filterable allow-create default-first-option :reserve-keyword="false" placeholder="选择标签或输入后按回车" class="wide-input">
          <el-option v-for="label in ['清淡', '酸甜', '鲜香', '微辣']" :key="label" :label="label" :value="label" />
        </el-select>
      </el-form-item>
      <el-form-item label="忌口食材">
        <el-select v-model="form.avoid_ingredients" multiple filterable :loading="ingredients.loading.value" placeholder="选择要避开的食材" class="wide-input">
          <el-option v-for="entry in ingredients.data.value" :key="entry.id" :label="categoryLabel(entry)" :value="entry.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="最长耗时（分钟）">
        <el-input-number v-model="form.max_cooking_time" :min="0" :max="1440" :step-strictly="true" placeholder="不限" />
      </el-form-item>
      <h2 class="form-section-title">每份营养目标</h2>
      <p class="field-hint">选择需要参与推荐评分的指标填写。</p>
      <div class="form-grid-4">
        <el-form-item v-for="{ key, label, unit } in nutrients" :key="key" :label="`${label}（${unit}）`">
          <el-input v-model="form.nutrition[key]" inputmode="decimal" />
        </el-form-item>
      </div>
      <div class="inline-actions">
        <el-button type="primary" native-type="submit" :loading="busy">保存偏好</el-button>
        <el-button @click="clearFields">清空表单</el-button>
      </div>
    </el-form>
  </section>
</template>
