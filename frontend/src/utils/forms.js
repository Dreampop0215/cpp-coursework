import { nextTick, onScopeDispose, reactive, ref, toValue } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorText, get, remove } from '../api.js'

export const unitGroups = [['g', 'kg'], ['mL', 'L'], ['个'], ['把']]
export const units = unitGroups.flat()
export const nutrients = [
  { key: 'calories', label: '能量', unit: 'kcal' }, { key: 'protein', label: '蛋白质', unit: 'g' },
  { key: 'fat', label: '脂肪', unit: 'g' }, { key: 'carbohydrate', label: '碳水化合物', unit: 'g' },
]

export const stockLabels = { fresh: '正常', expiring: '临期', expired: '已过期' }
export const listLabels = { open: '待采购', completed: '已完成' }

export function compatibleUnits(defaultUnit) {
  return unitGroups.find((group) => group.includes(defaultUnit)) || units
}

export function businessDate() {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
}

export function validAmount(value, min = 0, max = 99999) {
  return /^\d+(?:\.\d{1,2})?$/.test(String(value)) && Number(value) >= min && Number(value) <= max
}

export function categoryLabel(item) {
  return `${item.name} · ${item.category_name}`
}

export function useQuery(initial = null) {
  const data = ref(initial)
  const loading = ref(false)
  const error = ref('')
  let requestId = 0
  onScopeDispose(() => { requestId += 1 })

  async function run(load) {
    const id = ++requestId
    loading.value = true
    error.value = ''
    try {
      const result = await load()
      if (id === requestId) data.value = result
    } catch (failure) {
      if (id === requestId) error.value = errorText(failure)
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  return { data, loading, error, run }
}

export function usePage(path, filters) {
  const pager = reactive({ page: 1, size: 20 })
  const query = useQuery({ items: [], total: 0 })
  function load() {
    return query.run(() => get(toValue(path), { ...filters, page: pager.page, page_size: pager.size }))
  }
  function changePage({ page, size = pager.size }) {
    pager.page = page
    pager.size = size
    return load()
  }
  function search() {
    pager.page = 1
    return load()
  }
  async function afterDelete() {
    if (query.data.value.items.length === 1 && pager.page > 1) pager.page -= 1
    await load()
  }
  function sort({ order }) {
    filters.order = { ascending: 'asc', descending: 'desc' }[order]
    return search()
  }
  return { ...query, pager, load, changePage, search, afterDelete, sort }
}

export function useEditor() {
  const open = ref(false)
  const saving = ref(false)
  const message = ref('')
  const field = ref('')
  const touchedFields = reactive(new Set())

  function show() {
    message.value = ''
    field.value = ''
    touchedFields.clear()
    open.value = true
  }

  function fieldError(name, validationMessage, key = name) {
    if (touchedFields.has(key) && validationMessage) return validationMessage
    return field.value === name ? message.value : ''
  }

  function touchField(key) {
    touchedFields.add(key)
  }

  async function save(action, onSaved) {
    if (saving.value) return
    saving.value = true
    message.value = ''
    field.value = ''
    try {
      const value = await action()
      open.value = false
      await onSaved(value)
    } catch (error) {
      message.value = error.uiMessage || errorText(error)
      field.value = error.response?.data?.data?.field || error.uiField || ''
      if (field.value) {
        await nextTick()
        const element = [...document.querySelectorAll('[data-field]')].find(
          (candidate) => candidate.dataset.field === field.value && candidate.offsetParent,
        )
        element?.querySelector('input, textarea')?.focus()
      }
    } finally {
      saving.value = false
    }
  }
  return { open, saving, message, field, show, save, touchField, fieldError }
}

export function requireField(condition, uiField, uiMessage) {
  if (!condition) throw Object.assign(new Error(uiMessage), { uiField, uiMessage })
}

export async function confirmAction(message, title, button = '删除') {
  try {
    await ElMessageBox.confirm(message, title, {
      type: 'warning', confirmButtonText: button, cancelButtonText: '取消',
    })
    return true
  } catch {
    return false
  }
}

export async function confirmDelete(url, message, onDeleted) {
  if (!await confirmAction(message, '确认删除')) return
  try {
    await remove(url)
    ElMessage.success('已删除')
    await onDeleted()
  } catch (error) {
    ElMessage.error(errorText(error))
  }
}
