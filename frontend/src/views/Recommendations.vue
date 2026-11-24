<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { MagicStick, Timer } from '@element-plus/icons-vue'
import { errorText, get, post } from '../api.js'
import ChartPanel from '../components/ChartPanel.vue'
import LoadError from '../components/LoadError.vue'
import PageHeader from '../components/PageHeader.vue'
import RecipeDetails from '../components/RecipeDetails.vue'
import { useQuery } from '../utils/forms.js'
import { toChartOptions } from '../utils/charts.js'

const scoreLabels = { expiring: '临期利用', stock: '库存覆盖', taste: '口味匹配', time: '烹饪耗时', nutrition: '营养匹配' }
const form = reactive({ top_n: 5, max_cooking_time: undefined })
const weights = reactive({ expiring: '0.35', stock: '0.30', taste: '0.15', time: '0.10', nutrition: '0.10' })
const advanced = ref(false)
const { data: result, loading, error, run } = useQuery()
const data = computed(() => result.value?.recommendations)
const explanations = ref({})
const scoreOpen = ref(null)
const details = useQuery()
const detailOpen = ref(false)
const detailItem = ref(null)

function load() {
  const options = { ...form, weights: advanced.value ? { ...weights } : undefined }
  const params = { ...options, weights: options.weights ? JSON.stringify(options.weights) : undefined }
  return run(async () => ({ recommendations: await get('/recommendations', params), options }))
}
onMounted(load)
watch(result, () => {
  explanations.value = {}
  scoreOpen.value = null
})

function scoreChart(item) {
  return toChartOptions({
    labels: Object.values(scoreLabels), values: Object.keys(scoreLabels).map((key) => Number(item.score_details[key])),
    unit: '分', type: 'bar', horizontal: true, max: 100,
  })
}

async function explain(item) {
  if (explanations.value[item.recipe_id]?.loading) return
  const records = explanations.value
  records[item.recipe_id] = { loading: true }
  const entry = records[item.recipe_id]
  try {
    entry.result = await post(`/recommendations/${item.recipe_id}/explain`, result.value.options)
  } catch (error) {
    entry.error = errorText(error)
  } finally {
    entry.loading = false
  }
}

function refreshDetail() {
  return details.run(() => get(`/recipes/${detailItem.value.recipe_id}`))
}

function showDetails(item) {
  detailItem.value = item
  details.data.value = null
  detailOpen.value = true
  refreshDetail()
}
</script>

<template>
  <PageHeader title="智能推荐" description="按临期利用、库存、口味、耗时与营养匹配选择菜谱。" />
  <section class="panel recommendation-options">
    <el-form label-position="top" @submit.prevent="load">
      <div class="recommendation-fields">
        <el-form-item label="推荐数量">
          <el-input-number v-model="form.top_n" :min="1" :max="20" :step-strictly="true" />
        </el-form-item>
        <el-form-item label="最长耗时（分钟）">
          <el-input-number v-model="form.max_cooking_time" :min="0" :max="1440" :controls="false" :step-strictly="true" placeholder="不限" />
        </el-form-item>
        <div class="inline-actions">
          <el-button type="primary" native-type="submit" :loading="loading">更新推荐</el-button>
          <el-button link type="primary" :aria-expanded="advanced" @click="advanced = !advanced">{{ advanced ? '收起权重' : '调整权重' }}</el-button>
        </div>
      </div>
      <div v-if="advanced">
        <p class="field-hint">五项权重均为非负数，合计需要等于 1。</p>
        <div class="weight-fields">
          <el-form-item v-for="(label, key) in scoreLabels" :key="key" :label="label">
            <el-input v-model="weights[key]" inputmode="decimal" />
          </el-form-item>
        </div>
      </div>
    </el-form>
  </section>
  <LoadError :message="error && data ? `${error} 当前显示上次成功的推荐。` : error" @retry="load" />
  <el-skeleton v-if="loading && !data" :rows="5" animated />
  <div v-if="data" v-loading="loading">
    <el-alert v-if="data.degraded" class="form-alert" title="评分暂不可用，已按命中的临期食材种类推荐。" type="warning" :closable="false" show-icon />
    <el-empty v-if="!data.items.length" class="panel" description="暂无符合忌口或耗时要求的菜谱">
      <router-link class="text-link" :to="{ name: 'recipes' }">查看菜谱库</router-link>
    </el-empty>
    <div class="recommendation-grid">
      <article v-for="item in data.items" :key="item.recipe_id" class="panel recommendation-card">
        <div class="recommendation-title">
          <div>
            <h2>{{ item.name }}</h2>
            <div class="recipe-meta"><Timer /> {{ item.cooking_time }} 分钟 · {{ item.servings }} 份</div>
          </div>
          <div v-if="item.score !== null" class="recipe-score"><strong>{{ item.score }}</strong><span>分</span></div>
        </div>
        <ul class="reasons"><li v-for="reason in item.reasons" :key="reason">{{ reason }}</li></ul>
        <div v-if="item.missing.length" class="shortages">
          <el-tag v-for="line in item.missing" :key="line.ingredient_id" type="warning" effect="plain" round>{{ line.name }} {{ line.quantity }} {{ line.unit }}</el-tag>
        </div>
        <div v-if="item.score !== null">
          <el-button link type="primary" :aria-expanded="scoreOpen === item.recipe_id" @click="scoreOpen = scoreOpen === item.recipe_id ? null : item.recipe_id">
            {{ scoreOpen === item.recipe_id ? '收起评分' : '查看五维评分' }}
          </el-button>
          <ChartPanel v-if="scoreOpen === item.recipe_id" :options="scoreChart(item)" :label="`${item.name} 的五维推荐评分`" />
        </div>
        <div v-if="explanations[item.recipe_id]?.result" class="explanation" aria-live="polite">
          <strong>{{ explanations[item.recipe_id].result.source === 'deepseek' ? 'DeepSeek 解读' : '本地解读' }}</strong>
          <p>{{ explanations[item.recipe_id].result.text }}</p>
        </div>
        <LoadError :message="explanations[item.recipe_id]?.error" @retry="explain(item)" />
        <div class="inline-actions recommendation-actions">
          <el-button type="primary" tag="router-link" :to="{ name: 'shopping', query: { recipe: item.recipe_id } }">生成清单</el-button>
          <el-button @click="showDetails(item)">查看菜谱</el-button>
          <el-button :icon="MagicStick" :loading="explanations[item.recipe_id]?.loading" @click="explain(item)">DeepSeek 解读</el-button>
        </div>
      </article>
    </div>
  </div>
  <el-dialog v-model="detailOpen" :title="detailItem?.name" width="610px">
    <el-skeleton v-if="details.loading.value" :rows="5" animated />
    <LoadError :message="details.error.value" @retry="refreshDetail" />
    <RecipeDetails v-if="details.data.value" :recipe="details.data.value" />
  </el-dialog>
</template>
