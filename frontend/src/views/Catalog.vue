<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElTable, ElTableColumn, ElTabPane, ElTabs } from 'element-plus'
import { fetchAll, post, put } from '../api.js'
import CsvActions from '../components/CsvActions.vue'
import DataPager from '../components/DataPager.vue'
import LoadError from '../components/LoadError.vue'
import PageHeader from '../components/PageHeader.vue'
import {
  compatibleUnits, confirmDelete, requireField, units, useEditor, usePage, useQuery,
} from '../utils/forms.js'

const tab = ref('ingredients')
const kinds = { ingredient: '食材分类', recipe: '菜谱分类' }
const ingredientFilters = reactive({ keyword: '', category_id: null })
const categoryFilters = reactive({ keyword: '', type: null })
const ingredients = usePage('/ingredients', ingredientFilters)
const categories = usePage('/categories', categoryFilters)
const categoryOptions = useQuery([])
const form = reactive({})
const editingCategory = ref(false)
const { open, saving, message, field, show, save } = useEditor()
const allowedUnits = computed(() => form.originalUnit ? compatibleUnits(form.originalUnit) : units)

function loadOptions() {
  return categoryOptions.run(() => fetchAll('/categories', { type: 'ingredient' }))
}

onMounted(() => {
  loadOptions()
  ingredients.load()
})

function changeTab(value) {
  if (value === 'categories') categories.load()
  else ingredients.load()
}

function openForm(category, row) {
  editingCategory.value = category
  Object.assign(form, {
    id: row?.id, name: row?.name || '', type: row?.type || 'ingredient',
    category_id: row?.category_id, default_unit: row?.default_unit || 'g',
    originalUnit: row?.default_unit, shelf_life_days: row?.shelf_life_days ?? 3,
  })
  show()
}

function submit() {
  return save(async () => {
    const name = form.name.trim()
    requireField(name, 'name', '请输入名称。')
    let endpoint, payload
    if (editingCategory.value) {
      endpoint = '/categories'
      payload = { name, type: form.type }
    } else {
      requireField(form.category_id, 'category_id', '请选择食材分类。')
      requireField(Number.isInteger(form.shelf_life_days), 'shelf_life_days', '请输入非负整数天数。')
      endpoint = '/ingredients'
      payload = { name, category_id: form.category_id, default_unit: form.default_unit, shelf_life_days: form.shelf_life_days }
    }
    return form.id ? put(`${endpoint}/${form.id}`, payload) : post(endpoint, payload)
  }, async () => {
    ElMessage.success('资料已保存')
    if (editingCategory.value) await Promise.all([categories.load(), loadOptions()])
    else await ingredients.load()
  })
}
</script>

<template>
  <PageHeader title="食材与分类" description="维护库存和菜谱共用的食材字典。">
    <CsvActions v-if="tab === 'ingredients'" kind="ingredients" @imported="ingredients.search" />
    <el-button :icon="Plus" type="primary" @click="openForm(tab === 'categories')">{{ tab === 'categories' ? '添加分类' : '添加食材' }}</el-button>
  </PageHeader>
  <LoadError :message="categoryOptions.error.value" @retry="loadOptions" />
  <section class="panel data-panel">
    <el-tabs v-model="tab" @tab-change="changeTab">
      <el-tab-pane name="ingredients" label="食材字典">
        <div class="filter-row">
          <el-input v-model="ingredientFilters.keyword" aria-label="搜索食材" placeholder="搜索食材" :prefix-icon="Search" clearable @keyup.enter="ingredients.search" @clear="ingredients.search" />
          <el-select v-model="ingredientFilters.category_id" placeholder="全部分类" clearable aria-label="筛选分类" @change="ingredients.search">
            <el-option v-for="item in categoryOptions.data.value" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-button @click="ingredients.search">查询</el-button>
        </div>
        <LoadError :message="ingredients.error.value" @retry="ingredients.load" />
        <el-table v-loading="ingredients.loading.value" :data="ingredients.data.value.items" row-key="id" empty-text="没有符合条件的食材" @sort-change="ingredients.sort">
          <el-table-column prop="name" label="食材" min-width="140" sortable="custom" />
          <el-table-column prop="category_name" label="分类" min-width="110" />
          <el-table-column prop="default_unit" label="默认单位" min-width="100" />
          <el-table-column label="保质期" min-width="120"><template #default="{ row }">{{ row.shelf_life_days }} 天</template></el-table-column>
          <el-table-column label="操作" min-width="135">
            <template #default="{ row }">
              <el-button link type="primary" @click="openForm(false, row)">编辑</el-button>
              <el-button link type="danger" @click="confirmDelete(`/ingredients/${row.id}`, `删除食材「${row.name}」？`, ingredients.afterDelete)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <DataPager :pager="ingredients.pager" :total="ingredients.data.value.total" @change="ingredients.changePage" />
      </el-tab-pane>
      <el-tab-pane name="categories" label="分类" lazy>
        <div class="filter-row">
          <el-input v-model="categoryFilters.keyword" aria-label="搜索分类" placeholder="搜索分类" :prefix-icon="Search" clearable @keyup.enter="categories.search" @clear="categories.search" />
          <el-select v-model="categoryFilters.type" placeholder="所有类型" clearable aria-label="筛选分类类型" @change="categories.search">
            <el-option v-for="(label, kind) in kinds" :key="kind" :label="label" :value="kind" />
          </el-select>
          <el-button @click="categories.search">查询</el-button>
        </div>
        <LoadError :message="categories.error.value" @retry="categories.load" />
        <el-table v-loading="categories.loading.value" :data="categories.data.value.items" row-key="id" empty-text="没有符合条件的分类" @sort-change="categories.sort">
          <el-table-column prop="name" label="分类" min-width="130" sortable="custom" />
          <el-table-column label="类型" min-width="115"><template #default="{ row }">{{ kinds[row.type] }}</template></el-table-column>
          <el-table-column label="操作" min-width="135">
            <template #default="{ row }">
              <el-button link type="primary" @click="openForm(true, row)">编辑</el-button>
              <el-button link type="danger" @click="confirmDelete(`/categories/${row.id}`, `删除分类「${row.name}」？`, () => Promise.all([categories.afterDelete(), loadOptions()]))">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <DataPager :pager="categories.pager" :total="categories.data.value.total" @change="categories.changePage" />
      </el-tab-pane>
    </el-tabs>
  </section>

  <el-dialog v-model="open" :title="`${form.id ? '编辑' : '添加'}${editingCategory ? '分类' : '食材'}`" width="500px" :close-on-click-modal="false" :before-close="(done) => { if (!saving) done() }">
    <el-form label-position="top" @submit.prevent="submit">
      <el-alert v-if="message" class="form-alert" :title="message" type="error" :closable="false" show-icon />
      <el-form-item label="名称" data-field="name" :error="field === 'name' ? message : ''">
        <el-input v-model="form.name" :maxlength="editingCategory ? 50 : 100" />
      </el-form-item>
      <el-form-item v-if="editingCategory" label="分类类型" data-field="type" :error="field === 'type' ? message : ''">
        <el-select v-model="form.type" :disabled="Boolean(form.id)">
          <el-option v-for="(label, kind) in kinds" :key="kind" :label="label" :value="kind" />
        </el-select>
      </el-form-item>
      <template v-else>
        <el-form-item label="食材分类" data-field="category_id" :error="field === 'category_id' ? message : ''">
          <el-select v-model="form.category_id" filterable placeholder="选择分类" class="wide-input">
            <el-option v-for="item in categoryOptions.data.value" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <p v-if="!categoryOptions.loading.value && !categoryOptions.data.value.length" class="field-hint">
          <el-button link type="primary" @click="openForm(true)">先创建一个食材分类</el-button>
        </p>
        <div class="form-grid">
          <el-form-item label="默认单位" data-field="default_unit" :error="field === 'default_unit' ? message : ''">
            <el-select v-model="form.default_unit"><el-option v-for="unit in allowedUnits" :key="unit" :label="unit" :value="unit" /></el-select>
          </el-form-item>
          <el-form-item label="保质期（天）" data-field="shelf_life_days" :error="field === 'shelf_life_days' ? message : ''">
            <el-input-number v-model="form.shelf_life_days" :min="0" :max="2147483647" :step-strictly="true" controls-position="right" />
          </el-form-item>
        </div>
      </template>
      <el-button class="sign-submit" type="primary" native-type="submit" :loading="saving">保存资料</el-button>
    </el-form>
  </el-dialog>
</template>
