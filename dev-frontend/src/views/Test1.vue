<template>
    <div>
    <VueDraggable ref="el" v-model="list">
      <div v-for="item in list" :key="item.id">
        {{ item.name }}
      </div>
    </VueDraggable>
    </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
const list = ref([
  {
    name: 'Joao',
    id: 1
  },
  {
    name: 'Jean',
    id: 2
  },
  {
    name: 'Johanna',
    id: 3
  },
  {
    name: 'Juan',
    id: 4
  }
])
</script>