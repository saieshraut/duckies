import { reactive } from "vue";
export const toasts = reactive([]);
let id = 0;
export function toast(message, type = "info") {
  const t = { id: ++id, message, type };
  toasts.push(t);
  setTimeout(() => {
    const i = toasts.findIndex((x) => x.id === t.id);
    if (i > -1) toasts.splice(i, 1);
  }, 3200);
}
