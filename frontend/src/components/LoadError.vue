<script setup>
defineProps({ message: String })
defineEmits(['retry'])
</script>

<template>
  <div v-if="message" class="load-error" role="alert">
    <span>{{ message }}</span>
    <el-button text type="primary" @click="$emit('retry')">重试</el-button>
  </div>
</template>
