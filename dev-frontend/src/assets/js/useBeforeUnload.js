import { onMounted, onUnmounted, watch, toRef } from 'vue';

export function useBeforeUnload(activeRef, message) {
  // 确保 activeRef 是一个响应式引用
  const active = toRef(activeRef);
  
  const handler = (event) => {
    if (active.value) {  // 使用 .value 访问当前值
      event.preventDefault();
      event.returnValue = message;
      return message;
    }
  };

  // 使用 watch 来响应 active 的变化
  watch(active, (newVal) => {
    if (newVal) {
      window.addEventListener('beforeunload', handler);
    } else {
      window.removeEventListener('beforeunload', handler);
    }
  }, { immediate: true }); // immediate: true 确保初始状态也被处理

  onUnmounted(() => {
    window.removeEventListener('beforeunload', handler);
  });
}