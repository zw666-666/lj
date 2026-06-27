<script setup lang="ts">
import { ref, onMounted } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useAuthStore } from "@/stores/auth"
import api from "@/api/client"

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const status = ref<"loading" | "success" | "failed">("loading")
const orderInfo = ref<any>(null)
const errorMsg = ref("")

onMounted(async () => {
  const orderNo = route.query.order_no as string
  if (!orderNo) {
    status.value = "failed"
    errorMsg.value = "缺少订单号"
    return
  }

  // 轮询订单状态
  let attempts = 0
  const maxAttempts = 30
  const poll = async () => {
    try {
      const res = await api.get(`/payment/order/${orderNo}`)
      orderInfo.value = res.data
      if (res.data.status === "paid") {
        status.value = "success"
        await auth.fetchProfile()
        return
      }
      if (res.data.status === "failed" || res.data.status === "expired") {
        status.value = "failed"
        errorMsg.value = res.data.status === "expired" ? "订单已过期" : "支付失败"
        return
      }
      attempts++
      if (attempts < maxAttempts) {
        setTimeout(poll, 2000)
      } else {
        status.value = "failed"
        errorMsg.value = "支付确认超时，请在订单记录中查看"
      }
    } catch {
      attempts++
      if (attempts < maxAttempts) {
        setTimeout(poll, 3000)
      } else {
        status.value = "failed"
        errorMsg.value = "无法确认支付状态，请稍后重试"
      }
    }
  }

  poll()
})

function goHome() {
  router.push("/home")
}
</script>

<template>
  <div class="result-page">
    <div class="result-card" v-loading="status === 'loading'">
      <!-- 加载中 -->
      <template v-if="status === 'loading'">
        <div class="result-icon loading-icon">&#x23F3;</div>
        <h2>支付确认中...</h2>
        <p class="result-hint">正在等待支付宝确认，请稍候</p>
      </template>

      <!-- 成功 -->
      <template v-else-if="status === 'success'">
        <div class="result-icon success-icon">&#x2705;</div>
        <h2>支付成功！</h2>
        <p class="result-hint">您已成功开通律镜会员，所有会员功能已解锁</p>
        <div class="result-actions">
          <el-button type="primary" @click="goHome">开始使用</el-button>
        </div>
      </template>

      <!-- 失败 -->
      <template v-else>
        <div class="result-icon fail-icon">&#x274C;</div>
        <h2>支付未完成</h2>
        <p class="result-hint">{{ errorMsg }}</p>
        <div class="result-actions">
          <el-button @click="goHome">返回首页</el-button>
          <el-button type="warning" @click="router.push('/pricing')">重新选择方案</el-button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.result-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 200px);
}
.result-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 48px 40px;
  text-align: center;
  max-width: 440px;
  width: 100%;
  box-shadow: var(--shadow-md);
}
.result-icon {
  font-size: 52px;
  margin-bottom: 16px;
}
h2 {
  font-size: 22px;
  color: var(--text-primary);
  margin: 0 0 12px;
}
.result-hint {
  color: var(--text-tertiary);
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 24px;
}
.result-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
