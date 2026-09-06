import { defineStore } from "pinia"
import { ref } from "vue"

export const useSearchStore = defineStore("search", () => {
  const refreshFlag = ref(0)
  const query = ref("")

  function triggerRefresh() {
    refreshFlag.value++
  }

  function setQuery(q: string) {
    query.value = q
  }

  return { refreshFlag, query, triggerRefresh, setQuery }
})
