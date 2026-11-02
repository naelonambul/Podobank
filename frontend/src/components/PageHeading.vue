<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
});
</script>

<template>
  <div class="page-heading">
    <p class="eyebrow">PODOBANK</p>
    <h1>{{ title }}</h1>
    <p v-if="description" class="page-description">{{ description }}</p>
  </div>
</template>
