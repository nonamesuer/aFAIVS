import { ElMessageBox,ElNotification } from "element-plus";
import { ref } from 'vue';
const mse_type = {
  info: {"color":"#007bc0","icon":"Warning"},
  success: {"color":"#00884a","icon":"CircleCheck"},
  error: {"color":"#ed0007","icon":"CircleClose"},
  warning: {"color":"#ffcf00","icon":"Warning"},
} as const; // 使用 as const 让 TypeScript 推断为字面量类型

// 获取 mse_type 的键作为类型
type MseType = keyof typeof mse_type;
export const MesAlertWTitle=(type:MseType,title:String,content_header:String,content:String,button_text:String="OK")=>{
  const color = mse_type[type]['color'];  
  const icon = mse_type[type]['icon']
  ElMessageBox.alert(
        `
      <div class="top-line" style="background-color: ${color};"></div>
      <hr/>
      <b class="content-title">${content_header}</b>
      <div class="content-body">${content}</div>
      `,
        `${title}`,
        {
          
          confirmButtonText: `${button_text}`,
          modalClass: "bs-shade",
          customClass: "bs-messagebox",
          dangerouslyUseHTMLString: true,
          center: true,
          icon: icon,
        }
      );
};
export const MesConfirmWTitle=(type:MseType,title:String,content_header:String,content:String,confirm_button_text:String,cancle_button_text:String)=>{
  const color = mse_type[type]['color'];  
  const icon = mse_type[type]['icon']
  return ElMessageBox.confirm(
        `
      <div class="top-line" style="background-color: ${color};"></div>
      <hr/>
      <b class="content-title">${content_header}</b>
      <div class="content-body">${content}</div>
      `,
        `${title}`,
        {
          
          confirmButtonText: `${confirm_button_text}`,
          cancelButtonText:`${cancle_button_text}`,
          modalClass: "bs-shade",
          customClass: "bs-messagebox",
          dangerouslyUseHTMLString: true,
          center: true,
          icon: icon,
        }
      )
}
export const MesPrompt=(title:String,content:String,confirm_button_text:String,cancle_button_text:String)=>{
  return ElMessageBox.prompt(content, title, {
    confirmButtonText: confirm_button_text,
    cancelButtonText: cancle_button_text,
    inputValidator:(value)=>{
      if (!value) {
        return 'The name cannot be empty!';
      }
      const invalidChars = /[<>!@#$%^&*():"/\\|?*\x00-\x1F\s]/;
      if (invalidChars.test(value)){
        return 'Invalid Project Name'
      };
      return true
    },
    modalClass: "bs-shade",
    customClass: "bs-messagebox-prompt",
    dangerouslyUseHTMLString: true,
  })
}
export const Notification=(type:MseType,title:String,content:String,duration:number=4500,position:String="top-right")=>{
  const color = mse_type[type]['color'];  
  const icon = mse_type[type]['icon']
  return ElNotification({
    title: `${title}`,
    message: `${content}`,
    icon: icon,
    duration:duration,
    position: position,
    customClass:`notify_color_${type}`,
  })
}
//生成时间戳
export function getTimestamp() {
  return Date.now();
}

export function getRandomHexColor() {
  const letters = '0123456789ABCDEF';
  let color = '#';
  for (let i = 0; i < 6; i++) {
    color += letters[Math.floor(Math.random() * 16)];
  }
  return color;
}
export function getImageDimensions(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      resolve({
        width: img.naturalWidth,
        height: img.naturalHeight
      });
    };
    img.src = url;
  });
}
//防抖(先等后执行)
export function useDebounce(fn, delay = 500) {
  const timeout = ref(null);
  
  return function(...args) {
    clearTimeout(timeout.value);
    timeout.value = setTimeout(() => {
      fn.apply(this, args);
    }, delay);
  };
}
//节流(先执行后等)
export function useThrottle(fn, delay = 500) {
  const lastExecuted = ref(0); // 记录上次执行时间
  
  return function(...args) {
    const now = Date.now();
    if (now - lastExecuted.value < delay) {
      return; // 如果距离上次执行时间小于delay，则直接返回
    }
    
    lastExecuted.value = now; // 更新最后执行时间
    return fn.apply(this, args); // 执行函数
  };
}