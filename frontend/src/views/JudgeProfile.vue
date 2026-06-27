<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue"
import { Loading } from "@element-plus/icons-vue"
import { useRoute } from "vue-router"
import api from "@/api/client"
import * as echarts from "echarts"

const route = useRoute()
const profile = ref<any>(null)
const loading = ref(true)
const error = ref("")

onMounted(async () => {
  try {
    const name = route.params.name as string
    const res = await api.get(`/profile/judge/${encodeURIComponent(name)}`)
    profile.value = res.data
    await nextTick()
    renderCharts()
  } catch (e: any) {
    error.value = e.response?.data?.detail || "加载失败"
  } finally {
    loading.value = false
  }
})

function renderCharts() {
  if (!profile.value) return

  // 裁判倾向饼图
  const pieEl = document.getElementById("chart-ruling-tendency")
  if (pieEl) {
    const chart = echarts.init(pieEl)
    chart.setOption({
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [{
        type: "pie", radius: ["45%", "75%"], avoidLabelOverlap: false,
        label: { show: true, formatter: "{b}\n{d}%" },
        data: [
          { value: profile.value.support_plaintiff_ratio || 0, name: "支持原告", itemStyle: { color: "#3B82F6" } },
          { value: profile.value.support_defendant_ratio || 0, name: "支持被告", itemStyle: { color: "#EF4444" } },
          { value: profile.value.partial_support_ratio || 0, name: "部分支持", itemStyle: { color: "#F59E0B" } },
        ].filter(d => d.value > 0),
      }],
    })
  }

  // 案件类型分布柱状图
  const barEl = document.getElementById("chart-case-types")
  if (barEl && profile.value.case_type_distribution?.length) {
    const chart = echarts.init(barEl)
    const data = profile.value.case_type_distribution.slice(0, 10)
    chart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 20, right: 20, bottom: 20, top: 10, containLabel: true },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: data.map((d: any) => d.name || d.label || ""), axisLabel: { fontSize: 11 } },
      series: [{ type: "bar", data: data.map((d: any) => d.value || d.count || 0), itemStyle: { color: "#3B82F6", borderRadius: [0, 4, 4, 0] } }],
    })
  }

  // 高频法条
  const artEl = document.getElementById("chart-top-articles")
  if (artEl && profile.value.top_articles?.length) {
    const chart = echarts.init(artEl)
    const data = profile.value.top_articles.slice(0, 10)
    chart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 20, right: 40, bottom: 20, top: 10, containLabel: true },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: data.map((d: any) => (d.name || d.article || "").slice(0, 20)), axisLabel: { fontSize: 10 } },
      series: [{ type: "bar", data: data.map((d: any) => d.value || d.count || 0), itemStyle: { color: "#10B981", borderRadius: [0, 4, 4, 0] } }],
    })
  }
}

const pct = (v: any) => v != null ? (v * 100).toFixed(1) + "%" : "-"
</script>

<template>
  <div style="max-width: 1060px; margin: 0 auto">
    <div v-if="loading" style="text-align:center;padding:80px">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
    </div>

    <div v-else-if="error" style="text-align:center;padding:80px">
      <el-empty :description="error" />
    </div>

    <div v-else-if="profile">
      <h3 style="color:var(--text-primary);margin-bottom:4px">法官画像：{{ profile.judge_name }}</h3>
      <p style="color:var(--text-tertiary);font-size:13px;margin-bottom:24px">
        {{ profile.court || '' }}{{ profile.division ? ' · ' + profile.division : '' }}
        <el-tag v-if="profile.total_cases < 10" size="small" type="warning" style="margin-left:8px">
          样本量较小（N={{ profile.total_cases }}），仅供参考
        </el-tag>
      </p>

      <!-- 概览卡片 -->
      <el-row :gutter="16" style="margin-bottom:24px">
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-value">{{ profile.total_cases || 0 }}</div>
            <div class="stat-label">审理案件总数</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-value">{{ profile.avg_duration_days || '-' }}<span v-if="profile.avg_duration_days" style="font-size:14px"> 天</span></div>
            <div class="stat-label">平均审理周期</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-value">{{ pct(profile.appeal_reversal_ratio) }}</div>
            <div class="stat-label">二审改判率</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-value">{{ pct(profile.reversed_by_superior_ratio) }}</div>
            <div class="stat-label">被上级改判率</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 图表 -->
      <el-row :gutter="16" style="margin-bottom:24px">
        <el-col :span="12">
          <el-card shadow="never">
            <h4 style="margin-bottom:12px">裁判倾向分布</h4>
            <div id="chart-ruling-tendency" style="height:280px" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <h4 style="margin-bottom:12px">案件类型分布 (Top 10)</h4>
            <div v-if="profile.case_type_distribution?.length" id="chart-case-types" style="height:280px" />
            <el-empty v-else description="暂无数据" :image-size="60" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-card shadow="never">
            <h4 style="margin-bottom:12px">高频援引法条 (Top 10)</h4>
            <div v-if="profile.top_articles?.length" id="chart-top-articles" style="height:280px" />
            <el-empty v-else description="暂无数据" :image-size="60" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <h4 style="margin-bottom:12px">论证风格标签</h4>
            <div v-if="profile.style_tags?.length">
              <el-tag v-for="t in profile.style_tags" :key="t" style="margin:4px" size="large">{{ t }}</el-tag>
            </div>
            <el-empty v-else description="暂无数据" :image-size="60" />
            <div v-if="profile.avg_opinion_length" style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border-color)">
              <span style="color:var(--text-tertiary);font-size:13px">平均裁判意见字数：</span>
              <b style="font-size:16px;color:var(--text-primary)">{{ profile.avg_opinion_length?.toLocaleString() }}</b>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  text-align: center; padding: 16px;
  border-radius: var(--radius-lg);
  box-shadow: 0 0 0 1px var(--ring-color);
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(26, 39, 68, 0.06); }
.stat-value { font-size: 30px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 13px; color: var(--text-tertiary); margin-top: 4px; font-weight: 500; }
</style>
