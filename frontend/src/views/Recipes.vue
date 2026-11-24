<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Delete, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElTable, ElTableColumn } from 'element-plus'
import { errorText, fetchAll, get, post, put } from '../api.js'
import CsvActions from '../components/CsvActions.vue'
import DataPager from '../components/DataPager.vue'
import LoadError from '../components/LoadError.vue'
import PageHeader from '../components/PageHeader.vue'
import RecipeDetails from '../components/RecipeDetails.vue'
import {
  categoryLabel, compatibleUnits, confirmDelete, nutrients,
  requireField, useEditor, usePage, useQuery, validAmount,
} from '../utils/forms.js'

const filters = reactive({ keyword: '', category_id: undefined, cuisine: '', max_cooking_time: undefined })
const { data, loading, error, pager, load, changePage, search, afterDelete, sort } = usePage('/recipes', filters)
const options = useQuery({ categories: [], ingredients: [] })
const details = useQuery()
const detailOpen = ref(false)
const detailId = ref(null)
const detailName = ref('')
const pendingEdit = ref(null)
const form = reactive({})
const { open, saving, message, field, show, save, touchField, fieldError } = useEditor()
const difficulties = ['简单', '一般', '困难']
let nextLineId = 1
const newLine = (line = {}) => ({ key: nextLineId++, ingredient_id: undefined, quantity: '', unit: undefined, ...line })

function loadOptions() {
  return options.run(async () => {
    const [categories, ingredients] = await Promise.all([
      fetchAll('/categories', { type: 'recipe' }), fetchAll('/ingredients'),
    ])
    return { categories, ingredients }
  })
}
onMounted(() => { load(); loadOptions() })

function detail(row) {
  detailId.value = row.id
  detailName.value = row.name
  details.data.value = null
  detailOpen.value = true
  refreshDetail()
}

function refreshDetail() {
  return details.run(() => get(`/recipes/${detailId.value}`))
}

async function openForm(row) {
  if (pendingEdit.value) return
  let entry
  if (row) {
    pendingEdit.value = row.id
    try {
      entry = await get(`/recipes/${row.id}`)
    } catch (error) {
      ElMessage.error(errorText(error))
      return
    } finally {
      pendingEdit.value = null
    }
  }
  Object.assign(form, {
    id: entry?.id, name: entry?.name || '', category_id: entry?.category_id,
    cuisine: entry?.cuisine || '', difficulty: entry?.difficulty || '简单',
    cooking_time: entry?.cooking_time ?? 15, servings: entry?.servings ?? 2,
    taste_tags: entry?.taste_tags || [], steps: entry?.steps || [''],
    ingredients: entry?.ingredients.map((line) => newLine(line)) || [newLine()],
    ...Object.fromEntries(nutrients.map(({ key }) => [key, entry?.[key] ?? ''])),
  })
  show()
}

function ingredientFor(line) {
  return options.data.value.ingredients.find((item) => item.id === line.ingredient_id)
}

function quantityError(quantity) {
  return validAmount(quantity, .01) ? '' : '用量须为 0.01～99999.00，最多两位小数。'
}

function quantityFeedback(line, index) {
  return fieldError(`ingredients[${index}].quantity`, quantityError(line.quantity), line.key)
}

function submit() {
  return save(async () => {
    requireField(form.name.trim(), 'name', '请输入菜谱名称。')
    requireField(form.category_id, 'category_id', '请选择菜谱分类。')
    requireField(form.cuisine.trim(), 'cuisine', '请输入菜系。')
    requireField(Number.isInteger(form.cooking_time), 'cooking_time', '请输入烹饪分钟数。')
    requireField(Number.isInteger(form.servings) && form.servings > 0, 'servings', '请输入正整数份数。')
    requireField(form.steps.every((text) => text.trim()), 'steps', '请填写每个烹饪步骤。')
    const seen = new Set()
    const ingredients = form.ingredients.map((line, index) => {
      const prefix = `ingredients[${index}]`
      requireField(line.ingredient_id && !seen.has(line.ingredient_id), `${prefix}.ingredient_id`, '请选择食材，且每种食材只能使用一次。')
      const validationMessage = quantityError(line.quantity)
      requireField(!validationMessage, `${prefix}.quantity`, validationMessage)
      requireField(line.unit, `${prefix}.unit`, '请选择单位。')
      seen.add(line.ingredient_id)
      return { ingredient_id: line.ingredient_id, quantity: line.quantity, unit: line.unit }
    })
    const nutrition = {}
    for (const { key, label } of nutrients) {
      requireField(!form[key] || validAmount(form[key], 0, 99999999.99), key, `${label}须为非负数，最多两位小数。`)
      nutrition[key] = form[key] || null
    }
    const payload = {
      name: form.name, category_id: form.category_id, cuisine: form.cuisine, difficulty: form.difficulty,
      cooking_time: form.cooking_time, servings: form.servings, taste_tags: form.taste_tags,
      ingredients, steps: form.steps, ...nutrition,
    }
    return form.id ? put(`/recipes/${form.id}`, payload) : post('/recipes', payload)
  }, async () => {
    ElMessage.success('菜谱已保存')
    await load()
  })
}
</script>

<template>
  <PageHeader title="菜谱管理" description="维护制作步骤、基准份数和每份营养。">
    <CsvActions kind="recipes" @imported="search" />
    <el-button :icon="Plus" type="primary" @click="openForm()">添加菜谱</el-button>
  </PageHeader>
  <LoadError :message="options.error.value" @retry="loadOptions" />
  <section class="panel data-panel">
    <div class="filter-row">
      <el-input v-model="filters.keyword" aria-label="搜索菜谱" placeholder="搜索菜谱" :prefix-icon="Search" clearable @keyup.enter="search" @clear="search" />
      <el-select v-model="filters.category_id" aria-label="筛选菜谱分类" placeholder="全部分类" clearable @change="search">
        <el-option v-for="item in options.data.value.categories" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-input v-model="filters.cuisine" aria-label="筛选菜系" placeholder="菜系" clearable @keyup.enter="search" @clear="search" />
      <el-input-number v-model="filters.max_cooking_time" aria-label="最长耗时" :min="0" :max="1440" :controls="false" :step-strictly="true" placeholder="最长耗时（分钟）" @keyup.enter="search" />
      <el-button @click="search">查询</el-button>
    </div>
    <LoadError :message="error" @retry="load" />
    <el-table v-loading="loading" :data="data.items" row-key="id" empty-text="没有符合条件的菜谱" @sort-change="sort">
      <el-table-column prop="name" label="菜谱" min-width="160" sortable="custom">
        <template #default="{ row }"><el-button link type="primary" @click="detail(row)">{{ row.name }}</el-button><div class="table-secondary">{{ row.category_name }}</div></template>
      </el-table-column>
      <el-table-column prop="cuisine" label="菜系" min-width="100" />
      <el-table-column prop="difficulty" label="难度" min-width="80" />
      <el-table-column label="耗时" min-width="90"><template #default="{ row }">{{ row.cooking_time }} 分钟</template></el-table-column>
      <el-table-column label="基准份数" min-width="90"><template #default="{ row }">{{ row.servings }} 份</template></el-table-column>
      <el-table-column label="操作" min-width="155">
        <template #default="{ row }">
          <el-button link type="primary" :loading="pendingEdit === row.id" @click="openForm(row)">编辑</el-button>
          <el-button link type="danger" @click="confirmDelete(`/recipes/${row.id}`, `删除菜谱「${row.name}」？`, afterDelete)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <DataPager :pager="pager" :total="data.total" @change="changePage" />
  </section>

  <el-dialog v-model="detailOpen" :title="detailName" width="610px">
    <el-skeleton v-if="details.loading.value" :rows="5" animated />
    <LoadError :message="details.error.value" @retry="refreshDetail" />
    <RecipeDetails v-if="details.data.value" :recipe="details.data.value" />
    <template #footer v-if="details.data.value">
      <el-button type="primary" tag="router-link" :to="{ name: 'shopping', query: { recipe: detailId } }">生成采购清单</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="open" :title="form.id ? '编辑菜谱' : '添加菜谱'" width="740px" :close-on-click-modal="false" :before-close="(done) => { if (!saving) done() }">
    <el-form label-position="top" @submit.prevent="submit">
      <el-alert v-if="message" class="form-alert" :title="message" type="error" :closable="false" show-icon />
      <div class="form-grid">
        <el-form-item label="菜谱名称" data-field="name" :error="field === 'name' ? message : ''">
          <el-input v-model="form.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="菜谱分类" data-field="category_id" :error="field === 'category_id' ? message : ''">
          <el-select v-model="form.category_id" filterable placeholder="选择分类">
            <el-option v-for="item in options.data.value.categories" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="菜系" data-field="cuisine" :error="field === 'cuisine' ? message : ''">
          <el-input v-model="form.cuisine" maxlength="50" placeholder="例如 家常" />
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="form.difficulty"><el-option v-for="value in difficulties" :key="value" :label="value" :value="value" /></el-select>
        </el-form-item>
        <el-form-item label="耗时（分钟）" data-field="cooking_time" :error="field === 'cooking_time' ? message : ''">
          <el-input-number v-model="form.cooking_time" :min="0" :max="1440" :step-strictly="true" />
        </el-form-item>
        <el-form-item label="基准份数" data-field="servings" :error="field === 'servings' ? message : ''">
          <el-input-number v-model="form.servings" :min="1" :max="2147483647" :step-strictly="true" />
        </el-form-item>
      </div>
      <p v-if="!options.loading.value && (!options.data.value.categories.length || !options.data.value.ingredients.length)" class="field-hint">
        <router-link class="text-link" :to="{ name: 'catalog' }">先在食材与分类中维护菜谱分类和食材</router-link>
      </p>
      <el-form-item label="口味标签">
        <el-select v-model="form.taste_tags" multiple filterable allow-create default-first-option :reserve-keyword="false" class="wide-input" placeholder="选择或输入口味后按回车">
          <el-option v-for="label in ['清淡', '酸甜', '鲜香', '微辣']" :key="label" :label="label" :value="label" />
        </el-select>
      </el-form-item>
      <h3 class="form-section-title">每份营养（可选）</h3>
      <div class="form-grid-4">
        <el-form-item v-for="{ key, label, unit } in nutrients" :key="key" :label="`${label}（${unit}）`" :data-field="key" :error="field === key ? message : ''">
          <el-input v-model="form[key]" inputmode="decimal" />
        </el-form-item>
      </div>
      <h3 class="form-section-title">食材用量</h3>
      <div v-for="(line, index) in form.ingredients" :key="line.key" class="entry-line ingredient-line">
        <div :data-field="`ingredients[${index}].ingredient_id`">
          <el-select v-model="line.ingredient_id" filterable placeholder="选择食材" :aria-label="`食材 ${index + 1}`" @change="line.unit = ingredientFor(line)?.default_unit">
            <el-option v-for="item in options.data.value.ingredients" :key="item.id" :label="categoryLabel(item)" :value="item.id" />
          </el-select>
        </div>
        <div :data-field="`ingredients[${index}].quantity`">
          <el-input
            v-model="line.quantity" inputmode="decimal" placeholder="用量" :aria-label="`用量 ${index + 1}`"
            :aria-invalid="Boolean(quantityFeedback(line, index))"
            :aria-describedby="quantityFeedback(line, index) ? `recipe-quantity-error-${line.key}` : undefined"
            @blur="touchField(line.key)"
          />
        </div>
        <div :data-field="`ingredients[${index}].unit`">
          <el-select v-model="line.unit" placeholder="单位" :aria-label="`单位 ${index + 1}`">
            <el-option v-for="unit in compatibleUnits(ingredientFor(line)?.default_unit)" :key="unit" :label="unit" :value="unit" />
          </el-select>
        </div>
        <el-button :icon="Delete" text circle :disabled="form.ingredients.length < 2" :aria-label="`移除食材 ${index + 1}`" @click="form.ingredients.splice(index, 1)" />
        <p v-if="quantityFeedback(line, index)" :id="`recipe-quantity-error-${line.key}`" class="ingredient-quantity-error" role="alert">
          {{ quantityFeedback(line, index) }}
        </p>
      </div>
      <el-button :icon="Plus" text type="primary" @click="form.ingredients.push(newLine())">添加用量</el-button>
      <h3 class="form-section-title">烹饪步骤</h3>
      <div v-for="(_, index) in form.steps" :key="index" class="entry-line step-line" :data-field="index === 0 ? 'steps' : `steps[${index}]`">
        <el-input v-model="form.steps[index]" :placeholder="`步骤 ${index + 1}`" :aria-label="`步骤 ${index + 1}`" type="textarea" :rows="2" />
        <el-button :icon="Delete" text circle :disabled="form.steps.length < 2" :aria-label="`移除步骤 ${index + 1}`" @click="form.steps.splice(index, 1)" />
      </div>
      <el-button :icon="Plus" text type="primary" @click="form.steps.push('')">添加步骤</el-button>
      <el-button class="sign-submit" type="primary" native-type="submit" :loading="saving">保存菜谱</el-button>
    </el-form>
  </el-dialog>
</template>

<style scoped>
.ingredient-quantity-error {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--el-color-danger);
  font-size: 12px;
}
</style>
