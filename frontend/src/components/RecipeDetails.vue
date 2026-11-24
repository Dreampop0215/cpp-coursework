<script setup>
import { computed } from 'vue'
import { nutrients } from '../utils/forms.js'

const props = defineProps({ recipe: { type: Object, required: true } })
const facts = computed(() => nutrients.filter(({ key }) => props.recipe[key] !== null))
</script>

<template>
  <div class="recipe-details">
    <div class="recipe-meta">{{ recipe.cuisine }} · {{ recipe.difficulty }} · {{ recipe.cooking_time }} 分钟 · {{ recipe.servings }} 份</div>
    <div v-if="recipe.taste_tags.length" class="inline-actions">
      <el-tag v-for="tag in recipe.taste_tags" :key="tag" round>{{ tag }}</el-tag>
    </div>
    <div v-if="facts.length">
      <h3>每份营养</h3>
      <dl class="nutrition-facts">
        <div v-for="{ key, label, unit } in facts" :key="key">
          <dt>{{ label }}</dt><dd>{{ recipe[key] }} {{ unit }}</dd>
        </div>
      </dl>
    </div>
    <div>
      <h3>食材用量</h3>
      <ul class="quantity-list">
        <li v-for="line in recipe.ingredients" :key="line.id">
          <span>{{ line.ingredient_name }}</span><strong>{{ line.quantity }} {{ line.unit }}</strong>
        </li>
      </ul>
    </div>
    <div>
      <h3>做法</h3>
      <ol class="recipe-steps"><li v-for="(step, index) in recipe.steps" :key="index">{{ step }}</li></ol>
    </div>
  </div>
</template>
