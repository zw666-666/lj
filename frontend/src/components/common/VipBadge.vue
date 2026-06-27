<script setup lang="ts">
defineProps<{
  compact?: boolean
}>()
</script>

<template>
  <span class="vip-badge" :class="{ compact }">
    <span class="vip-diamond">◆</span>
    <span class="vip-text">会员</span>
  </span>
</template>

<style scoped>
.vip-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border: none;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-gold-dark);
  background: rgba(139, 105, 20, 0.06);
  box-shadow: 0 0 0 1px rgba(240, 192, 64, 0.4);
  user-select: none;
  vertical-align: middle;
  margin-left: 4px;
}
.vip-badge.compact {
  padding: 1px 6px;
  font-size: 10px;
  gap: 2px;
}
.vip-diamond {
  color: var(--accent-gold);
  font-size: 8px;
}
.vip-text {
  letter-spacing: 0.5px;
}
</style>
