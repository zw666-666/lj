import { createRouter, createWebHistory } from "vue-router"
import { useAuthStore } from "@/stores/auth"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "Login",
      component: () => import("@/views/Login.vue"),
      meta: { guest: true },
    },
    {
      path: "/",
      component: () => import("@/components/layout/UserLayout.vue"),
      redirect: "/landing",
      children: [
        {
          path: "landing",
          name: "Landing",
          component: () => import("@/views/Landing.vue"),
          meta: { title: "律镜 - AI 智能法律检索平台" },
        },
        {
          path: "home",
          name: "Home",
          component: () => import("@/views/Home.vue"),
          meta: { title: "律镜 - 智能类案检索" },
        },
        {
          path: "case/:id",
          name: "CaseReader",
          component: () => import("@/views/CaseReader.vue"),
          meta: { title: "案例阅读" },
        },
        {
          path: "profile/judge/:name",
          name: "JudgeProfile",
          component: () => import("@/views/JudgeProfile.vue"),
          meta: { title: "法官画像" },
        },
        {
          path: "compare",
          name: "Compare",
          component: () => import("@/views/Compare.vue"),
          meta: { title: "案例对标分析" },
        },
        {
          path: "qa",
          name: "QA",
          component: () => import("@/views/QA.vue"),
          meta: { title: "法律智能问答" },
        },
        {
          path: "qa/:sessionId",
          name: "QASession",
          component: () => import("@/views/QA.vue"),
          meta: { title: "智能问答" },
        },
        {
          path: "workspace",
          name: "Workspace",
          component: () => import("@/views/Workspace.vue"),
          meta: { title: "个人工作台" },
        },
        {
          path: "admin",
          name: "Admin",
          component: () => import("@/views/Admin.vue"),
          meta: { title: "管理后台", requireAdmin: true },
        },
        {
          path: "pricing",
          name: "Pricing",
          component: () => import("@/views/Pricing.vue"),
          meta: { title: "升级会员" },
        },
        {
          path: "payment-result",
          name: "PaymentResult",
          component: () => import("@/views/PaymentResult.vue"),
          meta: { title: "支付结果" },
        },
      ],
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/home",
    },
  ],
})

// 路由守卫：未登录跳转登录页，管理员页面权限检查
router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore()
  const hasOauthCallbackTokens =
    typeof to.query.access_token === "string" && typeof to.query.refresh_token === "string"

  // 登录页：已登录用户直接跳首页
  if (to.meta.guest && auth.isLoggedIn && !hasOauthCallbackTokens) {
    return next("/home")
  }

  // 非登录页：验证 token 有效性
  if (!to.meta.guest) {
    if (auth.token) {
      // 每次导航都刷新 profile，确保角色/订阅状态实时更新
      try {
        await auth.fetchProfile()
      } catch {
        auth.logout()
      }
      if (auth.isLoggedIn) return next()
    }
    // token 无效或不存在，跳转登录
    auth.logout()
    return next("/login")
  }

  // 管理员页面检查
  if (to.meta.requireAdmin && !auth.isAdmin) {
    return next("/home")
  }

  // 设置页面标题
  if (to.meta.title) {
    document.title = to.meta.title as string
  }

  next()
})

export default router
