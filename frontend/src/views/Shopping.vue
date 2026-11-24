<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Edit, MagicStick, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { errorText, fetchAll, get, post, put } from '../api.js'
import DataPager from '../components/DataPager.vue'
import LoadError from '../components/LoadError.vue'
import PageHeader from '../components/PageHeader.vue'
import {
  categoryLabel, compatibleUnits, confirmDelete, listLabels, requireField, useEditor, usePage, useQuery, validAmount,
} from '../utils/forms.js'

const route = useRoute()
const router = useRouter()
const filters = reactive({ status: null })
const { data, loading, error, pager, load, changePage, search, afterDelete } = usePage('/shopping-lists', filters)
const detail = useQuery()
const selectedId = ref(null)
const availableRecipes = useQuery([])
const availableIngredients = useQuery([])
const listEditor = useEditor()
const itemEditor = useEditor()
const listForm = reactive({ mode: 'manual', id: null, name: '', recipes: [] })
const itemForm = reactive({})
const mutating = ref(false)
let nextSelection = 0

const selected = computed(() => detail.data.value)
const picked = computed(() => availableIngredients.data.value.find((entry) => entry.id === itemForm.ingredient_id))
const recipeLine = (recipe_id, servings) => ({ key: nextSelection++, recipe_id, servings })

function refreshDetail() {
  return detail.run(() => get(`/shopping-lists/${selectedId.value}`))
}

function showList(row) {
  selectedId.value = row.id
  detail.data.value = null
  return refreshDetail()
}

function loadRecipes() {
  return availableRecipes.run(() => fetchAll('/recipes'))
}

function loadIngredients() {
  return availableIngredients.run(() => fetchAll('/ingredients'))
}

onMounted(async () => {
  const rows = load()
  if (route.query.recipe) {
    await openGenerator(Number(route.query.recipe))
    router.replace({ query: { ...route.query, recipe: undefined } })
  } else {
    await rows
    if (data.value.items.length && !selectedId.value) showList(data.value.items[0])
  }
})

function openName(row) {
  Object.assign(listForm, { mode: 'manual', id: row?.id, name: row?.name || '', recipes: [] })
  listEditor.show()
}

async function openGenerator(initialId) {
  Object.assign(listForm, { mode: 'generate', id: null, name: '', recipes: [recipeLine(initialId, 1)] })
  listEditor.show()
  if (!availableRecipes.data.value.length) await loadRecipes()
  const initial = availableRecipes.data.value.find((entry) => entry.id === initialId)
  if (initial && listEditor.open.value && listForm.mode === 'generate' && listForm.recipes[0]?.recipe_id === initialId) {
    listForm.recipes[0].servings = initial.servings
    if (!listForm.name) listForm.name = `${Array.from(initial.name).slice(0, 95).join('')}采购`
  }
}

function changeRecipe(row) {
  row.servings = availableRecipes.data.value.find((entry) => entry.id === row.recipe_id)?.servings || 1
}

function submitList() {
  return listEditor.save(async () => {
    const name = listForm.name.trim()
    requireField(name, 'name', '请输入清单名称。')
    if (listForm.mode === 'generate') {
      const ids = new Set()
      const recipes = listForm.recipes.map(({ recipe_id, servings }, i) => {
        requireField(recipe_id && !ids.has(recipe_id), `recipes[${i}].recipe_id`, '请选择菜谱，每道菜谱只能选一次。')
        requireField(Number.isInteger(servings) && servings > 0, `recipes[${i}].servings`, '请输入正整数份数。')
        ids.add(recipe_id)
        return { recipe_id, servings }
      })
      return post('/shopping-lists/generate', { name, recipes })
    }
    return listForm.id ? put(`/shopping-lists/${listForm.id}`, { name }) : post('/shopping-lists', { name })
  }, async (row) => {
    ElMessage.success(listForm.mode === 'generate' && !row.items.length ? '现有库存足够，无需采购' : '清单已保存')
    selectedId.value = row.id
    await detail.run(() => row)
    await search()
  })
}

function openItem(row) {
  Object.assign(itemForm, {
    listId: selectedId.value, id: row?.id, ingredient_id: row?.ingredient_id, quantity: row?.quantity ?? '',
    unit: row?.unit, is_checked: row?.is_checked ?? false,
  })
  itemEditor.show()
  if (!availableIngredients.data.value.length) loadIngredients()
}

function submitItem() {
  const target = itemForm.listId
  return itemEditor.save(async () => {
    requireField(itemForm.ingredient_id, 'ingredient_id', '请选择食材。')
    requireField(validAmount(itemForm.quantity, .01), 'quantity', '请输入正数量，最多两位小数。')
    const path = `/shopping-lists/${target}/items`
    const payload = {
      ingredient_id: itemForm.ingredient_id, quantity: itemForm.quantity, unit: itemForm.unit, is_checked: itemForm.is_checked,
    }
    return itemForm.id ? put(`${path}/${itemForm.id}`, payload) : post(path, payload)
  }, async () => {
    ElMessage.success('采购项已保存')
    await refreshAfterItems(target)
  })
}

async function refreshAfterItems(listId) {
  await Promise.all([load(), ...(selectedId.value === listId ? [refreshDetail()] : [])])
}

async function toggle(row, checked) {
  if (mutating.value) return
  const id = selectedId.value
  mutating.value = true
  try {
    await put(`/shopping-lists/${id}/items/${row.id}`, { is_checked: checked })
    await refreshAfterItems(id)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    mutating.value = false
  }
}

function deleteList(row) {
  return confirmDelete(`/shopping-lists/${row.id}`, `删除「${row.name}」及其采购项？`, async () => {
    if (selectedId.value === row.id) {
      selectedId.value = null
      await detail.run(() => null)
    }
    await afterDelete()
  })
}

function deletePurchaseItem(item) {
  const listId = selectedId.value
  return confirmDelete(
    `/shopping-lists/${listId}/items/${item.id}`,
    `删除采购项「${item.ingredient_name}」？`,
    () => refreshAfterItems(listId),
  )
}
</script>

<template>
  <PageHeader title="采购清单" description="合并菜谱用量，并用有效库存抵扣采购量。">
    <el-button :icon="Plus" @click="openName()">手动创建</el-button>
    <el-button :icon="MagicStick" type="primary" @click="openGenerator()">从菜谱生成</el-button>
  </PageHeader>

  <div class="shopping-layout">
    <section class="panel shopping-list-panel">
      <div class="panel-title">
        <h2>我的清单</h2>
        <el-select v-model="filters.status" placeholder="全部状态" clearable aria-label="筛选清单状态" style="width: 122px" @change="search">
          <el-option v-for="(label, key) in listLabels" :key="key" :label="label" :value="key" />
        </el-select>
      </div>
      <LoadError :message="error" @retry="load" />
      <div v-loading="loading" class="list-choices">
        <button
          v-for="row in data.items" :key="row.id" type="button" class="list-choice"
          :class="{ 'is-current': selectedId === row.id }" :aria-pressed="selectedId === row.id" @click="showList(row)"
        >
          <span><strong>{{ row.name }}</strong><small>{{ row.created_at.slice(0, 10) }}</small></span>
          <el-tag :type="row.status === 'completed' ? 'success' : 'info'" round>{{ listLabels[row.status] }}</el-tag>
        </button>
      </div>
      <el-empty v-if="!loading && !data.items.length" :image-size="66" description="没有符合条件的清单" />
      <DataPager :pager="pager" :total="data.total" @change="changePage" />
    </section>
    <section class="panel" v-loading="detail.loading.value">
      <LoadError :message="detail.error.value" @retry="refreshDetail" />
      <template v-if="selected">
        <div class="panel-title">
          <div><h2>{{ selected.name }}</h2><p>{{ listLabels[selected.status] }}</p></div>
          <div class="inline-actions">
            <el-button :icon="Edit" text aria-label="重命名清单" title="重命名清单" @click="openName(selected)" />
            <el-button link type="danger" @click="deleteList(selected)">删除清单</el-button>
          </div>
        </div>
        <div class="inline-actions shopping-add"><el-button :icon="Plus" type="primary" plain @click="openItem()">添加采购项</el-button></div>
        <ul v-if="selected.items.length" class="purchase-items">
          <li v-for="row in selected.items" :key="row.id" :class="{ 'is-checked': row.is_checked }">
            <el-checkbox
              class="purchase-check" :model-value="row.is_checked" :disabled="mutating"
              @change="(value) => toggle(row, value)"
            >{{ row.ingredient_name }}</el-checkbox>
            <span>{{ row.quantity }} {{ row.unit }}</span>
            <div class="inline-actions">
              <el-button link type="primary" :disabled="mutating" @click="openItem(row)">编辑</el-button>
              <el-button link type="danger" :disabled="mutating" @click="deletePurchaseItem(row)">删除</el-button>
            </div>
          </li>
        </ul>
        <el-empty v-else :image-size="72" description="这份清单暂无采购项" />
      </template>
      <el-empty v-else-if="!detail.loading.value && !detail.error.value" :image-size="72" description="选取一份清单，查看采购项" />
    </section>
  </div>

  <el-dialog
    v-model="listEditor.open.value" :title="listForm.mode === 'generate' ? '从菜谱生成清单' : listForm.id ? '重命名清单' : '创建采购清单'"
    width="550px" :close-on-click-modal="false" :before-close="(done) => { if (!listEditor.saving.value) done() }"
  >
    <el-form label-position="top" @submit.prevent="submitList">
      <el-alert v-if="listEditor.message.value" class="form-alert" :title="listEditor.message.value" type="error" :closable="false" show-icon />
      <el-form-item label="清单名称" data-field="name" :error="listEditor.field.value === 'name' ? listEditor.message.value : ''">
        <el-input v-model="listForm.name" maxlength="100" placeholder="例如 周末采购" />
      </el-form-item>
      <template v-if="listForm.mode === 'generate'">
        <LoadError :message="availableRecipes.error.value" @retry="loadRecipes" />
        <div v-for="(row, index) in listForm.recipes" :key="row.key" class="entry-line selection-line">
          <el-form-item label="菜谱" :data-field="`recipes[${index}].recipe_id`">
            <el-select v-model="row.recipe_id" filterable placeholder="选择菜谱" :loading="availableRecipes.loading.value" @change="changeRecipe(row)">
              <el-option v-for="entry in availableRecipes.data.value" :key="entry.id" :label="categoryLabel(entry)" :value="entry.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="制作份数" :data-field="`recipes[${index}].servings`">
            <el-input-number v-model="row.servings" :min="1" :max="2147483647" :step-strictly="true" />
          </el-form-item>
          <el-button link type="danger" :disabled="listForm.recipes.length === 1" @click="listForm.recipes.splice(index, 1)">移除</el-button>
        </div>
        <el-button :icon="Plus" text type="primary" @click="listForm.recipes.push(recipeLine(undefined, 1))">添加一道菜谱</el-button>
      </template>
      <el-button class="sign-submit" type="primary" native-type="submit" :loading="listEditor.saving.value" :disabled="listForm.mode === 'generate' && availableRecipes.loading.value">
        {{ listForm.mode === 'generate' ? '计算并生成清单' : '保存清单' }}
      </el-button>
    </el-form>
  </el-dialog>
  <el-dialog
    v-model="itemEditor.open.value" :title="itemForm.id ? '编辑采购项' : '添加采购项'" width="470px"
    :close-on-click-modal="false" :before-close="(done) => { if (!itemEditor.saving.value) done() }"
  >
    <el-form label-position="top" @submit.prevent="submitItem">
      <LoadError :message="availableIngredients.error.value" @retry="loadIngredients" />
      <el-alert v-if="itemEditor.message.value" class="form-alert" :title="itemEditor.message.value" type="error" :closable="false" show-icon />
      <el-form-item label="食材" data-field="ingredient_id" :error="itemEditor.field.value === 'ingredient_id' ? itemEditor.message.value : ''">
        <el-select v-model="itemForm.ingredient_id" filterable placeholder="选择食材" class="wide-input" :loading="availableIngredients.loading.value" @change="itemForm.unit = picked?.default_unit">
          <el-option v-for="entry in availableIngredients.data.value" :key="entry.id" :label="categoryLabel(entry)" :value="entry.id" />
        </el-select>
      </el-form-item>
      <div class="form-grid">
        <el-form-item label="数量" data-field="quantity" :error="itemEditor.field.value === 'quantity' ? itemEditor.message.value : ''">
          <el-input v-model="itemForm.quantity" inputmode="decimal" />
        </el-form-item>
        <el-form-item label="单位" data-field="unit" :error="itemEditor.field.value === 'unit' ? itemEditor.message.value : ''">
          <el-select v-model="itemForm.unit">
            <el-option v-for="unit in compatibleUnits(picked?.default_unit)" :key="unit" :label="unit" :value="unit" />
          </el-select>
        </el-form-item>
      </div>
      <el-checkbox v-model="itemForm.is_checked">已采购</el-checkbox>
      <el-button class="sign-submit" type="primary" native-type="submit" :loading="itemEditor.saving.value">保存采购项</el-button>
    </el-form>
  </el-dialog>
</template>
