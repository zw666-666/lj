<script setup lang="ts">
import { computed } from "vue"
import { useRouter } from "vue-router"

const props = defineProps<{
  visible: boolean
  title?: string
  description?: string
  featureName?: string
}>()

const emit = defineEmits<{
  (e: "update:visible", v: boolean): void
}>()

const router = useRouter()

const displayTitle = computed(() => props.title || "会员专属功能")
const displayDesc = computed(() => props.description || `「${props.featureName || "该功能"}」需要升级会员后才能使用。`)

function handleUpgrade() {
  emit("update:visible", false)
  router.push("/pricing")
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
    :title="displayTitle"
    width="420px"
    :close-on-click-modal="false"
    center
  >
    <div class="upgrade-body">
      <div class="upgrade-icon">&#x1F48E;</div>
      <p class="upgrade-desc">{{ displayDesc }}</p>
      <div class="upgrade-benefits">
        <div class="benefit-item">
          <span class="check">&#x2714;</span> 不限次数AI智能问答
        </div>
        <div class="benefit-item">
          <span class="check">&#x2714;</span> 深度案件对比分析
        </div>
        <div class="benefit-item">
          <span class="check">&#x2714;</span> 无限案例报告导出
        </div>
        <div class="benefit-item">
          <span class="check">&#x2714;</span> 知识图谱深度探索
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('update:visible', false)">暂不升级</el-button>
      <el-button type="warning" @click="handleUpgrade">立即升级</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.upgrade-body {
  text-align: center;
  padding: 8px 0;
}
.upgrade-icon {
  font-size: 44px;
  margin-bottom: 14px;
  filter: drop-shadow(0 0 12px rgba(240, 192, 64, 0.3));
}
.upgrade-desc {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 18px;
}
.upgrade-benefits {
  text-align: left;
  background: var(--bg-input);
  border: none;
  border-radius: 14px;
  box-shadow: 0 0 0 1px var(--ring-color);
  padding: 14px 18px;
}
.benefit-item {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 5px 0;
}
.check {
  color: var(--accent-green);
  margin-right: 8px;
  font-weight: bold;
}
</style>
