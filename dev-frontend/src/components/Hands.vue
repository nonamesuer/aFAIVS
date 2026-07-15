<template>
  <div class="hand-selector">
    <!-- 左手 -->
    <div class="hand-card" v-if="activeHands.includes('l')">
      <div class="title">{{ t('displaytext.left') }}</div>
      <svg viewBox="0 0 300 380">
        <!-- 骨架 -->
        <line
          v-for="(item,index) in connections"
          :key="'l'+index"
          class="line"
          :x1="point(item[0],false).x"
          :y1="point(item[0],false).y"
          :x2="point(item[1],false).x"
          :y2="point(item[1],false).y"
        />

        <!-- 点 -->
        <g v-for="(p,index) in points" :key="'lp'+index" @click="toggle('l',index)">
          <circle class="point" :class="{active:selected.l.includes(index) || false}" :cx="p.x" :cy="p.y" :r="pointRadius" />
        </g>
      </svg>

    </div>
    <!-- 右手 -->
    <div class="hand-card" v-if="activeHands.includes('r')">
      <div class="title">
        {{ t('displaytext.right') }}
        </div>
      <svg viewBox="0 0 300 400">
        <line
          v-for="(item,index) in connections"
          :key="'r'+index"
          class="line"
          :x1="point(item[0],true).x"
          :y1="point(item[0],true).y"
          :x2="point(item[1],true).x"
          :y2="point(item[1],true).y"
        />
        <g v-for="(p,index) in points" :key="'rp'+index" @click="toggle('r',index)">
          <circle class="point" :class="{active:selected.r.includes(index)} || false" :cx="300-p.x" :cy="p.y" :r="pointRadius"/>
        </g>
      </svg>

    </div>

  </div>
</template>

<script setup >

import { reactive,ref,computed,watch } from "vue";
import { useI18n } from "vue-i18n";
const { t } = useI18n();
const pointRadius = ref(15);
const props = defineProps({
    handsPoints:{
        type:Object,
        default:()=>({l:[],r:[]})
    }
});
const emit = defineEmits(['update:handsPoints']);

const points=[

{x:150,y:360},

//拇指
{x:70,y:300},
{x:50,y:250},
{x:30,y:200},
{x:20,y:150},

//食指
{x:110,y:260},
{x:95,y:185},
{x:85,y:115},
{x:75,y:45},

//中指
{x:160,y:250},
{x:160,y:170},
{x:156,y:90},
{x:155,y:15},

{x:210,y:260},
{x:215,y:190},
{x:215,y:120},
{x:215,y:60},

{x:250,y:280},
{x:260,y:220},
{x:270,y:170},
{x:275,y:120},

]

const connections=[
[0,1],[1,2],[2,3],[3,4],
[0,5],[5,6],[6,7],[7,8],
[5,9],[9,10],[10,11],[11,12],
[9,13],[13,14],[14,15],[15,16],
[13,17],[17,18],[18,19],[19,20],
[0,17]
]

const selected = reactive({
    l: [...(props.handsPoints?.l || [])],
    r: [...(props.handsPoints?.r || [])],
});
watch(() => props.handsPoints,newValue => {
    selected.l = [...(newValue?.l || []),];
    selected.r = [...(newValue?.r || []),];
  },
  {deep: true,immediate: true,}
);
const activeHands = computed(() => {
  return ['l', 'r'].filter(hand => Array.isArray(selected[hand]) && selected[hand].length > 0);
});

function toggle(hand, id) {
  const arr = selected[hand];
  const index = arr.indexOf(id);
  if (index >= 0) {
    arr.splice(index, 1);
  } else {
    arr.push(id);
    arr.sort((a, b) => a - b);
  }
  emit('update:handsPoints',{l: [...selected.l],r: [...selected.r],});
}

function point(index,mirror){
    const p=points[index]
    return{x:mirror?300-p.x:p.x,y:p.y}
}

</script>

<style scoped>

.hand-selector{
    display:flex;
    flex-direction:column;
    gap:18px;
    width:100%;
    height:100%;
}

.hand-card{
    flex: 1;
    min-height: 0;
    width:100%;
    box-sizing:border-box;
    padding:10px 5px;
    background:white;
    box-shadow:0 0 10px rgba(0,0,0,.12);
    display: flex;
    flex-direction: column;
}

.title{
    font-size:20px;
    font-weight:bold;
}

svg{
    flex: 1; /* SVG 填满卡片剩余空间 */
    width: 100%;
    height: auto; /* 让 flex 控制高度 */
    min-height: 0;
}

.line{
    stroke:#000;
    stroke-width:3;
}

.point{
    fill:var(--bs-bgcolor);
    stroke:#000;
    stroke-width:1;
    cursor:pointer;
    transition:.2s;
}

.point:hover{
    fill:var(--bs-info-color);
}

.point.active{
    fill:var(--bs-primary-color);
}

.label{
    font-size:11px;
    user-select:none;
}

</style>