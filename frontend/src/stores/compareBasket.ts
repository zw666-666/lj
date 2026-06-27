import { defineStore } from "pinia"
import { ref, computed, watch } from "vue"
import { useAuthStore } from "@/stores/auth"

export interface CaseItem {
  id: number
  case_no: string
  title: string
  court: string
  case_category_2: string
  judgment_date: string
}

const MAX_CASES = 5

function storageKey(uid: number | string | undefined): string {
  return `lvjing_compare_basket_${uid || "anon"}`
}

function loadFromStorage(uid: number | string | undefined): CaseItem[] {
  try {
    const raw = localStorage.getItem(storageKey(uid))
    if (raw) return JSON.parse(raw) as CaseItem[]
  } catch {}
  return []
}

function saveToStorage(cases: CaseItem[], uid: number | string | undefined) {
  localStorage.setItem(storageKey(uid), JSON.stringify(cases))
}

export const useCompareBasketStore = defineStore("compareBasket", () => {
  const auth = useAuthStore()
  const cases = ref<CaseItem[]>([])

  // 用户信息就绪后加载
  watch(() => auth.user?.id, (uid) => {
    if (uid) {
      cases.value = loadFromStorage(uid)
    }
  }, { immediate: true })

  const count = computed(() => cases.value.length)
  const isFull = computed(() => cases.value.length >= MAX_CASES)

  function hasCase(id: number): boolean {
    return cases.value.some(c => c.id === id)
  }

  function addCase(c: CaseItem): boolean {
    if (hasCase(c.id)) return false
    if (cases.value.length >= MAX_CASES) return false
    cases.value.push(c)
    saveToStorage(cases.value, auth.user?.id)
    return true
  }

  function removeCase(id: number) {
    cases.value = cases.value.filter(c => c.id !== id)
    saveToStorage(cases.value, auth.user?.id)
  }

  function clearAll() {
    cases.value = []
    saveToStorage(cases.value, auth.user?.id)
  }

  return { cases, count, isFull, hasCase, addCase, removeCase, clearAll }
})
