<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from "vue"
import { useRouter } from "vue-router"
import { useAuthStore } from "@/stores/auth"
import api from "@/api/client"
import { ElMessage } from "element-plus"
import { Loading } from "@element-plus/icons-vue"
import { toDataURL } from "qrcode"

interface Plan {
  id: number
  name: string
  plan_type: string
  price_cents: number
  original_price_cents: number | null
  features: string[] | null
}

const router = useRouter()
const auth = useAuthStore()

const plans = ref<Plan[]>([])
const loading = ref(false)
const creatingOrder = ref(false)
const payUrl = ref("")
const selectedPlan = ref<Plan | null>(null)

onUnmounted(() => { stopPolling() })

onMounted(async () => {
  try {
    const res = await api.get("/payment/plans")
    plans.value = res.data.plans
  } catch {
    ElMessage.error("加载方案失败")
  }
})

const priceYuan = (cents: number) => (cents / 100).toFixed(0)

const showQrDialog = ref(false)
const qrCodeUrl = ref("")
const qrDataUrl = ref("")
const qrOutTradeNo = ref("")
const qrPolling = ref(false)
const qrError = ref("")
const qrAmount = ref("")
let qrTimer: number | null = null
// 防止重复处理支付成功（onPaymentSuccess 只触发一次）
let paymentHandled = false
// 防止 watch 异步竞态：只采用最新一次 qrCodeUrl 的结果
let qrToken = 0

watch(qrCodeUrl, async (url) => {
  if (url) {
    const myToken = ++qrToken
    try {
      // 低纠错+小边距加速生成
      const dataUrl = await toDataURL(url, { width: 240, margin: 0, errorCorrectionLevel: 'L' })
      // 只在本次仍然是最新的请求时写入，避免被旧的异步结果覆盖
      if (myToken === qrToken) {
        qrDataUrl.value = dataUrl
      }
    } catch {
      if (myToken === qrToken) {
        qrDataUrl.value = ""
      }
    }
  } else {
    qrDataUrl.value = ""
  }
})

async function selectPlan(plan: Plan) {
  selectedPlan.value = plan
  creatingOrder.value = true
  qrError.value = ""
  paymentHandled = false

  // 强制先关闭旧对话框，确保 DOM 状态完全重置（防止旧二维码残留）
  if (showQrDialog.value) {
    showQrDialog.value = false
    await nextTick()
  }

  showQrDialog.value = true
  qrCodeUrl.value = ""
  qrDataUrl.value = ""
  qrOutTradeNo.value = ""
  try {
    const res = await api.post("/payment/alipay/create", null, {
      params: { plan: plan.plan_type, plan_id: plan.id }
    })
    if (res.data?.qr_code) {
      qrCodeUrl.value = res.data.qr_code
      qrOutTradeNo.value = res.data.out_trade_no
      qrAmount.value = res.data.amount
      // 立即开始轮询，不延迟
      startPolling()
    } else {
      ElMessage.error("未获取到支付二维码")
      showQrDialog.value = false
    }
  } catch (e: any) {
    const msg = e?.response?.data?.detail || "创建支付失败"
    qrError.value = msg
    ElMessage.error(msg)
    showQrDialog.value = false
  } finally {
    creatingOrder.value = false
  }
}

// 支付成功后的处理
async function onPaymentSuccess() {
  if (paymentHandled) return  // 防止重复处理
  paymentHandled = true
  showQrDialog.value = false
  stopPolling()
  await auth.fetchProfile()
  purchasedPlan.value = selectedPlan.value?.plan_type || ""
  ElMessage.success("支付成功！会员已激活")
  // 强制刷新会员状态
  await nextTick()
  if (selectedPlan.value?.plan_type === 'yearly') {
    // 年度会员覆盖一切
    purchasedPlan.value = 'yearly'
  }
}

const purchasedPlan = ref("")  // 已购买的方案标识

function startPolling() {
  qrPolling.value = true
  const buyingPlan = selectedPlan.value?.plan_type
  let count = 0
  let errStreak = 0  // 连续错误次数
  const MAX_POLL = 120   // 最多轮询 120 次 ≈ 3 分钟
  const MAX_ERR = 10     // 连续 10 次错误才放弃
  // 用 setTimeout 递归代替 setInterval，确保上一次请求完成后才发起下一次，
  // 避免 setInterval + async 导致并发请求和重复触发成功回调
  const tick = async () => {
    if (!qrPolling.value) return
    try {
      const res = await api.get("/payment/alipay/status", { params: { out_trade_no: qrOutTradeNo.value } })
      errStreak = 0
      // 支付宝端已取消支付
      if (res.data?.detail === "支付已取消") {
        qrPolling.value = false
        if (qrTimer) { clearTimeout(qrTimer); qrTimer = null }
        qrError.value = "支付已取消，请重新下单"
        return
      }
      if (res.data?.paid) {
        qrPolling.value = false
        if (qrTimer) { clearTimeout(qrTimer); qrTimer = null }
        purchasedPlan.value = buyingPlan || "monthly"
        await onPaymentSuccess()
        return
      }
      count++
      if (count >= MAX_POLL) {
        qrPolling.value = false
        if (qrTimer) { clearTimeout(qrTimer); qrTimer = null }
        ElMessage.warning("支付状态确认超时，若您已付款请点击「我已完成支付」")
        return
      }
    } catch {
      // 网络抖动不要立即停止，连续多次错误才放弃
      errStreak++
      if (errStreak >= MAX_ERR) {
        qrPolling.value = false
        if (qrTimer) { clearTimeout(qrTimer); qrTimer = null }
        ElMessage.error("网络异常，无法确认支付状态，请检查网络后点击「我已完成支付」")
        return
      }
    }
    if (qrPolling.value) {
      qrTimer = window.setTimeout(tick, 1500)
    }
  }
  qrTimer = window.setTimeout(tick, 1500)
}

// 手动确认支付
async function checkPaymentManually() {
  stopPolling()
  await auth.fetchProfile()
  if (auth.isPremium) {
    purchasedPlan.value = selectedPlan.value?.plan_type || "monthly"
    showQrDialog.value = false
    // 标记已处理，避免后续可能的轮询残留再次弹成功提示
    paymentHandled = true
    ElMessage.success("支付成功！会员已激活")
  } else {
    qrPolling.value = true
    startPolling()
    ElMessage.warning("暂未检测到支付，请确认已完成付款")
  }
}

function stopPolling() {
  qrPolling.value = false
  if (qrTimer) { clearTimeout(qrTimer); qrTimer = null }
}

function cancelPayment() {
  showQrDialog.value = false
  stopPolling()
  // 清空二维码和订单号，避免下次创建时旧数据残留
  qrCodeUrl.value = ""
  qrDataUrl.value = ""
  qrOutTradeNo.value = ""
  qrAmount.value = ""
  auth.fetchProfile()
}

function goHome() {
  router.push("/home")
}
</script>

<template>
  <div class="pricing-page">
    <div class="pricing-header">
      <h1>升级律镜会员</h1>
      <p class="subtitle">解锁全部功能，提升法律检索与案件分析效率</p>
    </div>

    <!-- 已是会员提示 -->
    <div v-if="auth.isPremium" class="already-premium">
      <el-alert :type="auth.isAdmin ? 'info' : 'success'" :closable="false" show-icon>
        <template #title>
          <template v-if="auth.isAdmin">您是管理员，已拥有全部权限</template>
          <template v-else>
            您已是律镜会员
            <span v-if="auth.subscriptionExpiresAt">，有效期至 {{ auth.subscriptionExpiresAt }}</span>
          </template>
        </template>
      </el-alert>
    </div>

    <!-- 方案卡片（始终显示） -->
    <div class="plan-cards" v-loading="loading">
      <div
        v-for="plan in plans"
        :key="plan.id"
        class="plan-card"
        :class="{ recommended: plan.plan_type === 'yearly' }"
      >
        <div v-if="plan.plan_type === 'yearly'" class="plan-tag">推荐</div>
        <div class="plan-name">{{ plan.name }}</div>
        <div class="plan-price">
          <span class="currency">¥</span>
          <span class="amount">{{ priceYuan(plan.price_cents) }}</span>
          <span class="period">/{{ plan.plan_type === 'monthly' ? '月' : '年' }}</span>
        </div>
        <div v-if="plan.original_price_cents" class="plan-original">
          ¥{{ priceYuan(plan.original_price_cents) }}
          <span class="discount-tag">
            省{{ priceYuan(plan.original_price_cents - plan.price_cents) }}元
          </span>
        </div>
        <ul class="plan-features" v-if="plan.features">
          <li v-for="(feat, idx) in plan.features" :key="idx">
            <span class="feat-check">&#x2714;</span> {{ feat }}
          </li>
        </ul>
        <!-- 管理员 -->
        <el-button v-if="auth.isAdmin" class="plan-btn plan-btn-done" type="success" size="large" round disabled>已是会员</el-button>
        <!-- 刚买了年度 → 全部"已成为年度会员" -->
        <el-button v-else-if="purchasedPlan === 'yearly'" class="plan-btn plan-btn-done" type="success" size="large" round disabled>已成为年度会员</el-button>
        <!-- 月度会员 + 月度卡 → 禁用 -->
        <el-button v-else-if="(purchasedPlan === 'monthly' || auth.isPremium) && plan.plan_type === 'monthly'" class="plan-btn plan-btn-done" type="success" size="large" round disabled>已成为月度会员</el-button>
        <!-- 月度会员 + 年度卡 → 立即开通 -->
        <el-button v-else-if="(purchasedPlan === 'monthly' || auth.isPremium) && plan.plan_type === 'yearly'" class="plan-btn plan-btn-blue" type="warning" :loading="creatingOrder && selectedPlan?.id === plan.id" @click="selectPlan(plan)" size="large" round>{{ creatingOrder && selectedPlan?.id === plan.id ? '创建订单中...' : '立即开通' }}</el-button>
        <!-- 未购买 -->
        <button v-else class="play-btn" :disabled="creatingOrder && selectedPlan?.id === plan.id" @click="selectPlan(plan)">
          <span class="play-icon">&#x2696;</span>
          <span class="now">now!</span>
          <span class="play">{{ creatingOrder && selectedPlan?.id === plan.id ? '创建订单中...' : '立即开通' }}</span>
        </button>
      </div>
    </div>

    <!-- 功能对比 -->
    <div class="compare-table">
      <h2>功能对比</h2>
      <el-table :data="compareData" stripe>
        <el-table-column prop="feature" label="功能" min-width="200" />
        <el-table-column label="免费用户" width="180" align="center">
          <template #default="{ row }">
            <span :class="row.freeClass || 'free-text'">{{ row.free }}</span>
          </template>
        </el-table-column>
        <el-table-column label="会员" width="220" align="center">
          <template #default="{ row }">
            <span class="premium-text">{{ row.premium }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 支付宝扫码支付弹窗 -->
    <el-dialog v-model="showQrDialog" title="支付宝扫码支付" width="400px" :close-on-click-modal="false" center>
      <div style="text-align:center">
        <p style="margin-bottom:4px;color:var(--text-secondary);font-size:14px">
          请使用<b>沙箱支付宝 App</b>扫描二维码
        </p>
        <p style="margin-bottom:16px;color:var(--accent-gold-dark);font-size:11px">
          ⚠ 请用沙箱买家账号登录，不能用商家账号扫码
        </p>
        <img v-if="qrDataUrl" :src="qrDataUrl" style="width:240px;height:240px;border-radius:8px;background:#fff;padding:8px" alt="支付二维码" />
        <div v-else-if="qrCodeUrl" style="padding:40px;color:var(--text-tertiary)">二维码生成中...</div>
        <div v-else style="padding:40px;color:var(--text-tertiary)">
          <el-icon class="is-loading" style="font-size:24px"><Loading /></el-icon>
          <div style="margin-top:8px">正在创建支付订单...</div>
        </div>
        <div v-if="qrPolling" style="margin-top:16px;color:var(--accent-blue);font-size:13px">
          等待支付中...（¥{{ qrAmount }} 元）
        </div>
        <div v-if="qrError" style="margin-top:8px;color:var(--accent-red);font-size:12px">{{ qrError }}</div>
      </div>
      <template #footer>
        <el-button @click="cancelPayment">取消支付</el-button>
        <el-button type="success" @click="checkPaymentManually">我已完成支付</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts">
const compareData = [
  { feature: "案例搜索", free: "不限", premium: "✓ 不限", premiumIcon: true },
  { feature: "AI智能问答", free: "每日 5 次", premium: "✓ 不限次数", premiumIcon: true },
  { feature: "案件对比分析", free: "基础 9 维度", premium: "✓ 深度对比（含争议焦点、裁判规则、AI 分析）", premiumIcon: true },
  { feature: "案例报告导出", free: "免费 2 次", premium: "✓ 无限导出", premiumIcon: true },
  { feature: "知识图谱", free: "节点深度 = 1", premium: "✓ 深度探索（depth=3）+ 规则演化", premiumIcon: true },
  { feature: "法官画像", free: "基础统计（案件数 / 法院）", premium: "✓ 深度分析（改判率 / 法条 / 趋势）", premiumIcon: true },
  { feature: "工作台容量", free: "不限", premium: "✓ 不限", premiumIcon: true },
]
</script>

<style scoped>
.pricing-page {
  max-width: 880px;
  margin: 0 auto;
  padding: 20px 0;
}
.pricing-header {
  text-align: center;
  margin-bottom: 36px;
}
.pricing-header h1 {
  font-size: 28px;
  color: var(--text-primary);
  margin: 0 0 8px;
  font-weight: 700;
}
.subtitle {
  color: var(--text-tertiary);
  font-size: 15px;
}
.already-premium {
  max-width: 460px;
  margin: 0 auto 24px;
}
.plan-cards {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin-bottom: 48px;
}
.plan-card {
  position: relative;
  background: var(--bg-card);
  border: 2px solid var(--border-color);
  border-radius: 12px;
  padding: 32px 28px;
  width: 260px;
  text-align: center;
  transition: all 0.2s;
}
.plan-card.recommended {
  border-color: var(--accent-gold);
  box-shadow: 0 4px 20px rgba(240, 192, 64, 0.2);
}
.plan-tag {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--accent-gold);
  color: #1a1a1a;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 14px;
  border-radius: 10px;
}
.plan-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}
.plan-price {
  margin-bottom: 4px;
}
.currency {
  font-size: 20px;
  color: var(--text-primary);
  vertical-align: top;
}
.amount {
  font-size: 42px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
}
.period {
  font-size: 14px;
  color: var(--text-tertiary);
}
.plan-original {
  font-size: 13px;
  color: var(--text-muted);
  text-decoration: line-through;
  margin-bottom: 16px;
}
.discount-tag {
  display: inline-block;
  text-decoration: none;
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  font-size: 11px;
  padding: 0 6px;
  border-radius: 4px;
  margin-left: 6px;
}
.plan-features {
  list-style: none;
  padding: 0;
  margin: 16px 0;
  text-align: left;
}
.plan-features li {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 4px 0;
}
.feat-check {
  color: var(--accent-green);
  margin-right: 6px;
}
.plan-btn {
  width: 100%;
  margin-top: 8px;
}
.plan-btn-done {
  opacity: 0.7;
}
.plan-btn-blue {
  background: #2F65FF !important;
  border-color: #2F65FF !important;
}
.play-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 0 10px;
  width: 100%;
  margin-top: 8px;
  color: white;
  text-shadow: 2px 2px rgb(116, 116, 116);
  text-transform: uppercase;
  cursor: pointer;
  border: solid 2px black;
  letter-spacing: 1px;
  font-weight: 600;
  font-size: 17px;
  background-color: #2F65FF;
  border-radius: 50px;
  position: relative;
  overflow: hidden;
  transition: all 0.5s ease;
}
.play-btn:active {
  transform: scale(0.9);
  transition: all 100ms ease;
}
.play-btn svg {
  transition: all 0.5s ease;
  z-index: 2;
}
.play-btn .play {
  transition: all 0.5s ease;
  transition-delay: 300ms;
}
.play-btn:hover svg {
  transform: scale(3) translate(50%);
}
.play-btn .play-icon {
  font-size: 28px;
  color: #FFD700;
  transition: all 0.5s ease;
  z-index: 2;
  display: inline-block;
  line-height: 1;
}
.play-btn:hover .play-icon {
  transform: scale(2) translate(130%, 0%);
}
.play-btn .now {
  position: absolute;
  left: 0;
  transform: translateX(-100%);
  transition: all 0.5s ease;
  z-index: 2;
}
.play-btn:hover .now {
  transform: translateX(40px);
  transition-delay: 300ms;
}
.play-btn:hover .play {
  transform: translateX(200%);
  transition-delay: 300ms;
}
.play-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
.compare-table {
  max-width: 700px; margin: 0 auto;
}
.compare-table h2 {
  text-align: center; font-size: 20px; color: #F0F6FC; margin-bottom: 16px;
}
.compare-table :deep(.el-table) {
  background: transparent !important; border: none !important;
}
.compare-table :deep(.el-table th.el-table__cell) {
  background: rgba(22,27,34,0.6) !important; color: #F0F6FC !important;
  border-bottom: 1px solid #30363D !important; font-weight: 600; font-size: 13px;
}
.compare-table :deep(.el-table td.el-table__cell) {
  border-bottom: 1px solid #21262D !important; color: #8B949E !important;
  padding: 14px 16px !important;
}
.compare-table :deep(.el-table tr) { background: transparent !important; }
.compare-table :deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(22,27,34,0.3) !important;
}
.compare-table :deep(.el-table__body tr:hover td.el-table__cell) {
  background: rgba(22,27,34,0.5) !important;
}
.free-text { color: #8B949E; }
.free-ok { color: #8B949E; }
.free-limited { color: #8B949E; }
.premium-text {
  color: #FFC542; font-weight: 600; font-size: 13px;
}
</style>
