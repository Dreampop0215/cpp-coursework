<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElDatePicker, ElMessage, ElTable, ElTableColumn } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { errorText, fetchAll, get, post } from '../api.js'
import ChartPanel from '../components/ChartPanel.vue'
import DataPager from '../components/DataPager.vue'
import LoadError from '../components/LoadError.vue'
import PageHeader from '../components/PageHeader.vue'
import { toChartOptions } from '../utils/charts.js'
import {
  businessDate, categoryLabel, compatibleUnits, requireField, useEditor, usePage, useQuery, validAmount,
} from '../utils/forms.js'

const route = useRoute()
const router = useRouter()
const filters = reactive({ start_date: null, end_date: null, category_id: null })
const dates = ref(null)
const group = ref('month')
const groupLabels = { month: '月份', category: '食材分类', reason: '原因' }
const logs = usePage('/waste-logs', filters)
const statistics = useQuery({ items: [] })
const options = useQuery({ ingredients: [], categories: [] })
const batches = useQuery([])
const { open, saving, message, field, show, save, touchField, fieldError } = useEditor()
const form = reactive({})
const picked = computed(() => options.data.value.ingredients.find((entry) => entry.id === form.ingredient_id))
const activeGroupLabel = computed(() => groupLabels[statistics.data.value.group_by])
const amounts = computed(() => toChartOptions({
  labels: statistics.data.value.items.map((entry) => entry.label),
  values: statistics.data.value.items.map((entry) => Number(entry.amount)),
  unit: '元', type: 'bar',
}))
const checks = {
  quantity: () => validAmount(form.quantity, .01) ? '' : '请输入正数量，最多两位小数。',
  amount: () => validAmount(form.amount, 0, 99999999.99) ? '' : '请输入非负金额，最多两位小数。',
  waste_date: () => form.waste_date && form.waste_date <= businessDate() ? '' : '请选择今天或更早的登记日期。',
}

function loadOptions() {
  return options.run(async () => {
    const [ingredients, categories] = await Promise.all([
      fetchAll('/ingredients'), fetchAll('/categories', { type: 'ingredient' }),
    ])
    return { ingredients, categories }
  })
}

function loadStatistics() {
  return statistics.run(() => get('/statistics/waste', { ...filters, group_by: group.value }))
}

function search() {
  const [start, end] = dates.value || []
  filters.start_date = start
  filters.end_date = end
  return Promise.all([logs.search(), loadStatistics()])
}

onMounted(async () => {
  const catalog = loadOptions()
  search()
  if (route.query.batch && /^\d+$/.test(route.query.batch)) {
    try {
      const batch = await get(`/inventory/${route.query.batch}`)
      await catalog
      openForm(batch)
    } catch (error) {
      ElMessage.error(errorText(error))
    }
    router.replace({ query: { ...route.query, batch: undefined } })
  }
})

function refreshBatches() {
  const ingredientId = form.ingredient_id
  return batches.run(async () => {
    if (!ingredientId) return []
    const result = await fetchAll('/inventory', { ingredient_id: ingredientId })
    return result.filter((entry) => Number(entry.quantity) > 0)
  })
}

function openForm(batch) {
  Object.assign(form, {
    ingredient_id: batch?.ingredient_id, inventory_id: batch?.id, quantity: '', unit: batch?.unit,
    amount: '0.00', reason: '', waste_date: businessDate(),
  })
  batches.data.value = []
  show()
  refreshBatches()
}

function changeIngredient() {
  form.inventory_id = undefined
  form.unit = picked.value?.default_unit
  batches.data.value = []
  refreshBatches()
}

function changeBatch(batchId) {
  const batch = batches.data.value.find((entry) => entry.id === batchId)
  if (batch) form.unit = batch.unit
}

function submit() {
  return save(async () => {
    requireField(form.ingredient_id, 'ingredient_id', '请选择浪费食材。')
    requireField(form.reason.trim(), 'reason', '请输入浪费原因。')
    for (const [name, check] of Object.entries(checks)) {
      const validationMessage = check()
      requireField(!validationMessage, name, validationMessage)
    }
    return post('/waste-logs', {
      ingredient_id: form.ingredient_id, inventory_id: form.inventory_id ?? null,
      quantity: form.quantity, unit: form.unit, amount: form.amount,
      reason: form.reason, waste_date: form.waste_date,
    })
  }, async () => {
    ElMessage.success(form.inventory_id ? '浪费已登记，库存已扣减' : '浪费已登记')
    await search()
  })
}
</script>

<template>
  <PageHeader title="浪费记录" description="登记损耗，并按日期、食材分类或原因查看汇总。">
    <el-button :icon="Plus" type="primary" @click="openForm()">登记浪费</el-button>
  </PageHeader>
  <LoadError :message="options.error.value" @retry="loadOptions" />
  <section class="panel waste-chart" v-loading="statistics.loading.value">
    <div class="panel-title">
      <h2>浪费金额</h2>
      <el-select v-model="group" aria-label="统计分组" style="width: 145px" @change="loadStatistics">
        <el-option v-for="(label, key) in groupLabels" :key="key" :label="`按${label}`" :value="key" />
      </el-select>
    </div>
    <div class="filter-row">
      <el-date-picker v-model="dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="起始日期" end-placeholder="结束日期" @change="search" />
      <el-select v-model="filters.category_id" clearable placeholder="全部食材分类" aria-label="筛选食材分类" @change="search">
        <el-option v-for="entry in options.data.value.categories" :key="entry.id" :label="entry.name" :value="entry.id" />
      </el-select>
    </div>
    <LoadError :message="statistics.error.value" @retry="loadStatistics" />
    <template v-if="!statistics.error.value && statistics.data.value.items.length">
      <ChartPanel :options="amounts" :label="`按${activeGroupLabel}统计的浪费金额柱状图`" />
      <el-table :data="statistics.data.value.items" row-key="key">
        <el-table-column prop="label" :label="activeGroupLabel" min-width="120" />
        <el-table-column prop="count" label="记录数" min-width="78" />
        <el-table-column label="损耗数量" min-width="170">
          <template #default="{ row }">
            <div class="shortages">
              <el-tag v-for="part in row.quantities" :key="part.unit" effect="plain">{{ part.quantity }} {{ part.unit }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="金额（元）" min-width="110"><template #default="{ row }">¥{{ row.amount }}</template></el-table-column>
      </el-table>
    </template>
    <el-empty v-else-if="!statistics.loading.value && !statistics.error.value" :image-size="67" description="筛选范围内暂无浪费数据" />
  </section>

  <section class="panel data-panel">
    <div class="panel-title"><h2>登记明细</h2></div>
    <LoadError :message="logs.error.value" @retry="logs.load" />
    <el-table v-loading="logs.loading.value" :data="logs.data.value.items" row-key="id" empty-text="没有符合条件的浪费记录" @sort-change="logs.sort">
      <el-table-column prop="waste_date" label="日期" min-width="110" sortable="custom" />
      <el-table-column prop="ingredient_name" label="食材" min-width="130" />
      <el-table-column label="数量" min-width="95"><template #default="{ row }">{{ row.quantity }} {{ row.unit }}</template></el-table-column>
      <el-table-column prop="amount" label="金额（元）" min-width="105" />
      <el-table-column prop="reason" label="原因" min-width="160" />
      <el-table-column label="关联批次" min-width="100"><template #default="{ row }">{{ row.inventory_id ? `#${row.inventory_id}` : '—' }}</template></el-table-column>
    </el-table>
    <DataPager :pager="logs.pager" :total="logs.data.value.total" @change="logs.changePage" />
  </section>

  <el-dialog v-model="open" title="登记浪费" width="540px" :close-on-click-modal="false" :before-close="(done) => { if (!saving) done() }">
    <el-form label-position="top" @submit.prevent="submit">
      <el-alert v-if="message" class="form-alert" :title="message" type="error" :closable="false" show-icon />
      <el-form-item label="食材" data-field="ingredient_id" :error="field === 'ingredient_id' ? message : ''">
        <el-select v-model="form.ingredient_id" filterable placeholder="选择食材" class="wide-input" @change="changeIngredient">
          <el-option v-for="entry in options.data.value.ingredients" :key="entry.id" :label="categoryLabel(entry)" :value="entry.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="库存批次（可选）" data-field="inventory_id" :error="field === 'inventory_id' ? message : ''">
        <el-select v-model="form.inventory_id" filterable clearable :loading="batches.loading.value" :disabled="!form.ingredient_id" class="wide-input" placeholder="仅登记浪费" @change="changeBatch">
          <el-option v-for="entry in batches.data.value" :key="entry.id" :label="`#${entry.id} · ${entry.quantity} ${entry.unit} · ${entry.expiry_date} 到期`" :value="entry.id" />
        </el-select>
      </el-form-item>
      <LoadError :message="batches.error.value" @retry="refreshBatches" />
      <p v-if="form.inventory_id" class="field-hint">保存后会同时从关联批次扣减该数量。</p>
      <div class="form-grid">
        <el-form-item label="数量" data-field="quantity" :error="fieldError('quantity', checks.quantity())">
          <el-input v-model="form.quantity" inputmode="decimal" @blur="touchField('quantity')" />
        </el-form-item>
        <el-form-item label="单位" data-field="unit" :error="field === 'unit' ? message : ''">
          <el-select v-model="form.unit">
            <el-option v-for="unit in compatibleUnits(picked?.default_unit)" :key="unit" :label="unit" :value="unit" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额（元）" data-field="amount" :error="fieldError('amount', checks.amount())">
          <el-input v-model="form.amount" inputmode="decimal" @blur="touchField('amount')" />
        </el-form-item>
        <el-form-item label="浪费日期" data-field="waste_date" :error="fieldError('waste_date', checks.waste_date())">
          <el-date-picker v-model="form.waste_date" type="date" value-format="YYYY-MM-DD" @blur="touchField('waste_date')" @change="touchField('waste_date')" />
        </el-form-item>
      </div>
      <el-form-item label="原因" data-field="reason" :error="field === 'reason' ? message : ''">
        <el-input v-model="form.reason" maxlength="100" placeholder="例如 变质或烹饪剩余" />
      </el-form-item>
      <el-button class="sign-submit" type="primary" native-type="submit" :loading="saving">保存浪费记录</el-button>
    </el-form>
  </el-dialog>
</template>
