/**
 * electron 的主进程
 */
// 导入模块
const { app, BrowserWindow } = require('electron')
const path = require('path')
// 创建主窗口
const createWindow = () => {
  const win = new BrowserWindow({
    width: 800,
    height: 600,
    show: false,
    icon: path.join(__dirname, 'src/assets/img/FAIVS.jpg'), // 添加这行，指定图标路径
    webPreferences: {
    nodeIntegration: true,
    contextIsolation: false
  },
  webPreferences: {
    preload: path.join(__dirname, 'proload.js') // 指定 preload 脚本
  }
  });
  // 窗口最大化
  win.maximize()

  // 当窗口准备好后显示，避免闪烁
  win.on('ready-to-show', () => {
    win.show()
  })
  win.loadFile(path.resolve(__dirname, 'dist/index.html'))
}

// 应用准备就绪，加载窗口
app.whenReady().then(() => {
  createWindow()
  // mac 上默认保留一个窗口
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// 关闭所有窗口 ： 程序退出 ： windows & linux
app.on('window-all-closed',async () => {
  try {
      // 等待请求完成（最多 5 秒）
      await Promise.race([
        fetch('http://127.0.0.1:20253/shutdown', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        }),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Request timeout')), 5000)
        )
      ]);
    } catch (err) {
      console.error('Shutdown request failed:', err);
    } finally {
      app.quit(); // 确保最终退出
    }

})

