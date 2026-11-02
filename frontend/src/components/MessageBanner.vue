<script setup>
defineProps({
  message: { type: String, default: '' },
  kind: { type: String, default: 'error' },
});
</script>

<template>
  <p
    v-if="message"
    class="message-banner"
    :class="`message-${kind}`"
    :role="kind === 'error' ? 'alert' : 'status'"
  >
    {{ message }}
  </p>
</template>
