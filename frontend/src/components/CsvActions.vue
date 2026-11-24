<script setup>
import { ref } from 'vue'
import { Download, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElTable, ElTableColumn } from 'element-plus'
import { errorText, http } from '../api.js'
import { confirmAction } from '../utils/forms.js'

const props = defineProps({ kind: { type: String, required: true } })
const emit = defineEmits(['imported'])
const input = ref(null)
const busy = ref(false)
const downloading = ref(false)
const errors = ref([])
const showErrors = ref(false)

async function upload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || busy.value) return
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error('CSV 文件大小须在 2 MiB 以内')
    return
  }
  if (!await confirmAction(`导入 ${file.name} 中的资料？`, '批量导入', '确认导入')) return
  busy.value = true
  try {
    const multipart = new FormData()
    multipart.append('file', file)
    const { data } = await http.post(`/import/${props.kind}`, multipart)
    ElMessage.success(`已导入 ${data.data.inserted_count} 条记录`)
    emit('imported')
  } catch (error) {
    errors.value = error.response?.data?.data?.errors || []
    if (errors.value.length) showErrors.value = true
    else ElMessage.error(errorText(error))
  } finally {
    busy.value = false
  }
}

async function download() {
  downloading.value = true
  try {
    const response = await http.get(`/export/${props.kind}`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = `${props.kind}.csv`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <div class="inline-actions">
    <input ref="input" type="file" accept=".csv,text/csv" hidden @change="upload">
    <el-button :icon="Upload" :loading="busy" @click="input?.click()">导入 CSV</el-button>
    <el-button :icon="Download" :loading="downloading" @click="download">导出 CSV</el-button>
  </div>
  <el-dialog v-model="showErrors" title="CSV 导入失败" width="620px">
    <p class="field-hint">请修正下列记录后重新上传。表头计为第 1 行。</p>
    <el-table :data="errors" max-height="380">
      <el-table-column prop="row" label="记录号" width="85" />
      <el-table-column prop="field" label="字段" min-width="100" />
      <el-table-column prop="message" label="问题" min-width="210" />
    </el-table>
    <template #footer><el-button @click="showErrors = false">关闭</el-button></template>
  </el-dialog>
</template>
