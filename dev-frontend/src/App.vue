<template>
  <Loading v-show="appStore.loading" />
  <router-view></router-view>
</template>
<script setup lang="ts">
import Loading from './views/Loading.vue';
import { useAppStore } from "@/stores/store";
const appStore = useAppStore();
</script>
<style>
</style>