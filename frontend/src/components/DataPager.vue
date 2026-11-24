<script setup>
import { ElPagination } from 'element-plus'

defineProps({ pager: Object, total: Number })
const emit = defineEmits(['change'])
</script>

<template>
  <div class="pager" v-if="total > 0">
    <el-pagination
      background layout="total, sizes, prev, pager, next" :total="total"
      :current-page="pager.page" :page-size="pager.size" :page-sizes="[10, 20, 50, 100]"
      @update:current-page="(page) => emit('change', { page })"
      @update:page-size="(size) => emit('change', { page: 1, size })"
    />
  </div>
</template>
