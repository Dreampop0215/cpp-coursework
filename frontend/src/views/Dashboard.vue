<script setup>
import { computed, onMounted, reactive } from 'vue'
import { Box, CircleCheck, Plus, Timer, Warning } from '@element-plus/icons-vue'
import { ElDatePicker } from 'element-plus'
import ChartPanel from '../components/ChartPanel.vue'
import LoadError from '../components/LoadError.vue'
import PageHeader from '../components/PageHeader.vue'
import { fetchAll, get } from '../api.js'
import { useQuery } from '../utils/forms.js'
import { toChartOptions } from '../utils/charts.js'

const { data: summary, loading, error, run } = useQuery()
const categories = useQuery([])
const filters = reactive({ category_id: undefined, dates: null })
const metrics = [
  { key: 'total', label: '实存批次', icon: Box, tone: 'pine' },
  { key: 'fresh', label: '正常', icon: CircleCheck, tone: 'leaf' },
  { key: 'expiring', label: '临期', icon: Timer, tone: 'amber' },
  { key: 'expired', label: '已过期', icon: Warning, tone: 'rose' },
]

function loadCategories() {
  return categories.run(() => fetchAll('/categories', { type: 'ingredient' }))
}
function load() {
  const [start_date, end_date] = filters.dates || []
  return run(() => get('/dashboard/summary', { start_date, end_date, category_id: filters.category_id }))
}
onMounted(() => {
  load()
  loadCategories()
})

const hasWaste = computed(() => summary.value?.waste_monthly.some((entry) => entry.count))
const line = computed(() => toChartOptions({
  labels: summary.value.waste_monthly.map((entry) => entry.label),
  values: summary.value.waste_monthly.map((entry) => Number(entry.amount)),
  unit: '元', type: 'line',
}))
const categoriesChart = computed(() => toChartOptions({
  labels: summary.value.inventory_by_category.map((entry) => entry.name),
  values: summary.value.inventory_by_category.map((entry) => entry.count),
  unit: '批', type: 'pie',
}))
const money = computed(() => summary.value?.waste_monthly.reduce((sum, entry) => sum + Number(entry.amount), 0).toFixed(2))
</script>

<template>
  <PageHeader title="厨房总览">
    <el-button :icon="Plus" type="primary" tag="router-link" :to="{ name: 'inventory', query: { new: '1' } }">
      添加库存
    </el-button>
  </PageHeader>
  <LoadError :message="error" @retry="load" />
  <LoadError :message="categories.error.value" @retry="loadCategories" />
  <el-skeleton v-if="!summary && loading" :rows="8" animated />
  <div v-if="summary" v-loading="loading" class="dashboard">
    <section class="pantry-hero" aria-labelledby="expiry-heading">
      <div class="pantry-hero-image" />
      <div class="pantry-hero-content">
        <div class="hero-label"><Timer /> 临期提醒</div>
        <h2 id="expiry-heading">
          {{ summary.inventory_counts.expiring ? `${summary.inventory_counts.expiring} 批食材即将到期` : '当前没有临期食材' }}
        </h2>
        <p>{{ summary.expiry_warning_days }} 天内到期且仍有余量的批次会优先显示。</p>
        <router-link class="hero-button" :to="{ name: 'inventory', query: { status: 'expiring' } }">查看临期库存</router-link>
      </div>
    </section>
    <div class="dashboard-metrics">
      <div v-for="metric in metrics" :key="metric.key" class="metric">
        <span class="metric-icon" :class="metric.tone"><component :is="metric.icon" /></span>
        <div>
          <span class="metric-label">{{ metric.label }}</span>
          <div class="metric-number">{{ summary.inventory_counts[metric.key] }} <small>批</small></div>
        </div>
      </div>
    </div>
    <div class="dashboard-filters">
      <label>
        <span>食材分类</span>
        <el-select v-model="filters.category_id" clearable placeholder="全部分类" style="width: 150px" @change="load">
          <el-option v-for="item in categories.data.value" :key="item.id" :value="item.id" :label="item.name" />
        </el-select>
      </label>
      <label>
        <span>浪费日期</span>
        <el-date-picker
          v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD"
          start-placeholder="起始日期" end-placeholder="结束日期" :default-value="new Date()" @change="load"
        />
      </label>
    </div>
    <div class="dashboard-grid">
      <section class="panel dashboard-preview">
        <div class="panel-title">
          <div>
            <h2>优先使用</h2>
            <p>按到期日排列</p>
          </div>
          <router-link class="text-link" :to="{ name: 'inventory', query: { status: 'expiring' } }">查看全部</router-link>
        </div>
        <ul v-if="summary.expiring_preview.length" class="expiry-list">
          <li v-for="item in summary.expiring_preview" :key="item.id">
            <div class="expiry-item">
              <span class="mini-icon"><Box /></span>
              <div><strong>{{ item.ingredient_name }}</strong><small>{{ item.category_name }} · {{ item.quantity }} {{ item.unit }}</small></div>
            </div>
            <div class="expiry-date">
              <time :datetime="item.expiry_date">{{ item.expiry_date }}</time>
              <el-tag type="warning" effect="light" round>{{ item.days_left === 0 ? '今天到期' : `剩 ${item.days_left} 天` }}</el-tag>
            </div>
          </li>
        </ul>
        <el-empty v-else :image-size="66" description="暂无临期批次">
          <router-link class="text-link" :to="{ name: 'inventory', query: { new: '1' } }">登记库存批次</router-link>
        </el-empty>
      </section>
      <section class="panel">
        <div class="panel-title">
          <div><h2>浪费金额</h2><p>{{ summary.start_date }} 至 {{ summary.end_date }}</p></div>
          <strong class="chart-total">¥{{ money }}</strong>
        </div>
        <ChartPanel v-if="hasWaste" :options="line" label="按月汇总的浪费金额折线图" />
        <el-empty v-else :image-size="66" description="该日期范围内暂无浪费记录" />
      </section>
      <section class="panel">
        <div class="panel-title"><div><h2>库存分类</h2><p>按实存批次数统计</p></div></div>
        <ChartPanel v-if="summary.inventory_by_category.length" :options="categoriesChart" label="库存分类批次数环形图" />
        <el-empty v-else :image-size="66" description="暂无有余量的库存批次" />
      </section>
    </div>
  </div>
</template>
