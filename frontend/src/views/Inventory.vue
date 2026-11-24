<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Search } from '@element-plus/icons-vue'
import { ElDatePicker, ElMessage, ElTable, ElTableColumn } from 'element-plus'
import { fetchAll, post, put } from '../api.js'
import DataPager from '../components/DataPager.vue'
import LoadError from '../components/LoadError.vue'
import PageHeader from '../components/PageHeader.vue'
import {
  businessDate, categoryLabel, compatibleUnits, confirmDelete, requireField, stockLabels,
  useEditor, usePage, useQuery, validAmount,
} from '../utils/forms.js'

const route = useRoute()
const router = useRouter()
const filters = reactive({ keyword: '', category_id: null, status: null, start_date: null, end_date: null })
const selectedDates = ref(null)
const endpoint = computed(() => filters.status === 'expiring' ? '/inventory/expiring' : '/inventory')
const { data, loading, error, pager, load, changePage, search, afterDelete, sort } = usePage(endpoint, filters)
const options = useQuery({ ingredients: [], categories: [] })
const editor = useEditor()
const { open, saving, message, field, show, save, touchField, fieldError } = editor
const form = reactive({})
const picked = computed(() => options.data.value.ingredients.find((item) => item.id === form.ingredient_id))
const availableUnits = computed(() => compatibleUnits(picked.value?.default_unit))
const checks = {
  quantity: () => validAmount(form.quantity) ? '' : '数量须为 0～99999.00，最多两位小数。',
  purchase_date: () => form.purchase_date && form.purchase_date <= businessDate() ? '' : '请选择今天或更早的购买日期。',
  expiry_date: () => form.expiry_date && form.purchase_date && form.expiry_date < form.purchase_date
    ? '到期日期不能早于购买日期。' : '',
}

function loadOptions() {
  return options.run(async () => {
    const [ingredients, categories] = await Promise.all([
      fetchAll('/ingredients'), fetchAll('/categories', { type: 'ingredient' }),
    ])
    return { ingredients, categories }
  })
}

function syncRoute() {
  filters.status = Object.hasOwn(stockLabels, route.query.status) ? route.query.status : null
  search()
  if (route.query.new === '1') {
    openForm()
    router.replace({ query: { ...route.query, new: undefined } })
  }
}

onMounted(() => {
  loadOptions()
  syncRoute()
})
watch(() => [route.query.status, route.query.new], ([status, add], [oldStatus]) => {
  if (status !== oldStatus || add === '1') syncRoute()
})

function datesChanged(value) {
  filters.start_date = value?.[0]
  filters.end_date = value?.[1]
  search()
}

function openForm(row) {
  Object.assign(form, {
    id: row?.id, ingredient_id: row?.ingredient_id, quantity: row?.quantity ?? '',
    unit: row?.unit, purchase_date: row?.purchase_date || businessDate(),
    expiry_date: row?.expiry_date || null, shelf_life_days: undefined,
  })
  show()
}

function ingredientChanged() {
  form.unit = picked.value?.default_unit
}

function purchaseDateChanged() {
  touchField('purchase_date')
  touchField('expiry_date')
}

function submit() {
  return save(async () => {
    requireField(form.ingredient_id, 'ingredient_id', '请选择食材。')
    for (const [name, check] of Object.entries(checks)) {
      const validationMessage = check()
      requireField(!validationMessage, name, validationMessage)
    }
    const payload = {
      ingredient_id: form.ingredient_id, quantity: form.quantity, unit: form.unit,
      purchase_date: form.purchase_date, expiry_date: form.expiry_date || null,
      shelf_life_days: form.shelf_life_days ?? null,
    }
    return form.id ? put(`/inventory/${form.id}`, payload) : post('/inventory', payload)
  }, async () => {
    ElMessage.success('库存批次已保存')
    await load()
  })
}

const tagType = { fresh: 'success', expiring: 'warning', expired: 'danger' }
</script>

<template>
  <PageHeader title="库存管理" description="按批次记录数量和到期日。">
    <el-button type="primary" :icon="Plus" @click="openForm()">添加批次</el-button>
  </PageHeader>
  <LoadError :message="options.error.value" @retry="loadOptions" />
  <section class="panel data-panel">
    <div class="filter-row">
      <el-input v-model="filters.keyword" aria-label="搜索食材" placeholder="搜索食材" :prefix-icon="Search" clearable @keyup.enter="search" @clear="search" />
      <el-select v-model="filters.category_id" placeholder="全部分类" clearable aria-label="筛选分类" @change="search">
        <el-option v-for="item in options.data.value.categories" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-select v-model="filters.status" placeholder="全部状态" clearable aria-label="筛选状态" @change="search">
        <el-option v-for="(label, key) in stockLabels" :key="key" :label="label" :value="key" />
      </el-select>
      <el-date-picker v-model="selectedDates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="到期日起始" end-placeholder="到期日结束" @change="datesChanged" />
      <el-button @click="search">查询</el-button>
    </div>
    <LoadError :message="error" @retry="load" />
    <el-table v-loading="loading" :data="data.items" row-key="id" empty-text="没有符合条件的库存批次" @sort-change="sort">
      <el-table-column label="食材" min-width="145">
        <template #default="{ row }"><span class="table-main">{{ row.ingredient_name }}</span><div class="table-secondary">{{ row.category_name }}</div></template>
      </el-table-column>
      <el-table-column label="实存量" min-width="110"><template #default="{ row }">{{ row.quantity }} {{ row.unit }}</template></el-table-column>
      <el-table-column prop="purchase_date" label="购买日期" min-width="110" />
      <el-table-column prop="expiry_date" label="到期日期" min-width="110" sortable="custom" />
      <el-table-column label="状态" min-width="105">
        <template #default="{ row }">
          <el-tag :type="tagType[row.status]" round>{{ stockLabels[row.status] }}</el-tag>
          <div v-if="row.status === 'expiring'" class="table-secondary">{{ row.days_left === 0 ? '今天到期' : `剩 ${row.days_left} 天` }}</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="175">
        <template #default="{ row }">
          <div class="inline-actions">
            <el-button link type="primary" @click="openForm(row)">编辑</el-button>
            <el-button link type="primary" tag="router-link" :to="{ name: 'waste', query: { batch: row.id } }" v-if="Number(row.quantity) > 0">记浪费</el-button>
            <el-button link type="danger" @click="confirmDelete(`/inventory/${row.id}`, `删除「${row.ingredient_name}」的这批库存？`, afterDelete)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <DataPager :pager="pager" :total="data.total" @change="changePage" />
  </section>

  <el-dialog v-model="open" :title="form.id ? '编辑库存批次' : '登记库存批次'" width="540px" :close-on-click-modal="false" :before-close="(done) => { if (!saving) done() }">
    <el-form label-position="top" @submit.prevent="submit">
      <el-alert v-if="message" class="form-alert" :title="message" type="error" :closable="false" show-icon />
      <el-form-item label="食材" data-field="ingredient_id" :error="field === 'ingredient_id' ? message : ''">
        <el-select v-model="form.ingredient_id" :disabled="Boolean(form.id)" :loading="options.loading.value" filterable placeholder="选择食材" class="wide-input" @change="ingredientChanged">
          <el-option v-for="item in options.data.value.ingredients" :key="item.id" :label="categoryLabel(item)" :value="item.id" />
        </el-select>
      </el-form-item>
      <p v-if="!options.loading.value && !options.data.value.ingredients.length" class="field-hint">
        <router-link class="text-link" :to="{ name: 'catalog' }">前往维护食材字典</router-link>
      </p>
      <div class="form-grid">
        <el-form-item label="数量" data-field="quantity" :error="fieldError('quantity', checks.quantity())">
          <el-input v-model="form.quantity" inputmode="decimal" placeholder="例如 250.00" @blur="touchField('quantity')" />
        </el-form-item>
        <el-form-item label="单位" data-field="unit" :error="field === 'unit' ? message : ''">
          <el-select v-model="form.unit" placeholder="选择单位">
            <el-option v-for="unit in availableUnits" :key="unit" :label="unit" :value="unit" />
          </el-select>
        </el-form-item>
        <el-form-item label="购买日期" data-field="purchase_date" :error="fieldError('purchase_date', checks.purchase_date())">
          <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" @blur="touchField('purchase_date')" @change="purchaseDateChanged" />
        </el-form-item>
        <el-form-item label="到期日期（可选）" data-field="expiry_date" :error="fieldError('expiry_date', checks.expiry_date())">
          <el-date-picker v-model="form.expiry_date" type="date" value-format="YYYY-MM-DD" placeholder="指定到期日" @blur="touchField('expiry_date')" @change="touchField('expiry_date')" />
        </el-form-item>
        <el-form-item label="保质期（天，可选）" data-field="shelf_life_days" :error="field === 'shelf_life_days' ? message : ''">
          <el-input-number v-model="form.shelf_life_days" :min="0" :max="3652058" :step-strictly="true" controls-position="right" />
        </el-form-item>
      </div>
      <p v-if="picked && !form.id" class="field-hint">到期日和保质期均留空时，使用该食材的默认保质期 {{ picked.shelf_life_days }} 天。</p>
      <el-button class="sign-submit" type="primary" native-type="submit" :loading="saving">保存批次</el-button>
    </el-form>
  </el-dialog>
</template>
