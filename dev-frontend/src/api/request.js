import axios from "axios"
const errorHandle = (status, info) => {
    switch (status) {
        case 400:
            console.log("语义有误");
            break;
        case 401:
            console.log("服务器认证失败");
            break;
        case 403:
            console.log("服务器拒绝访问");
            break;
        case 404:
            console.log("地址错误");
            break;
        case 407:
            console.log("跨域错误");
            break;
        case 500:
            console.log("服务器遇到意外");
            break;
        case 502:
            console.log("服务器无响应");
            break;
        default:
            console.log(info);
            break;
    }
}
const instance = axios.create({
    timeout: 15000,

})
//发送数据之前（interceptors：拦截器）
instance.interceptors.request.use(
    config => {
        if (config.method === "post") {
            config.data = JSON.stringify(config.data)
        }
        return config; //config包含网络请求所有信息
    },
    error => Promise.reject(error)
)
//获取数据之前
instance.interceptors.response.use(
    response => response.status === 200 ? Promise.resolve(response) : Promise.reject(response),
    error => {
        const { response } = error;
        if (response) {
            errorHandle(response.status, response.info)
        } else {
            error.message = "后端服务连接中断"
            errorHandle(0, error.message)
        }
        return Promise.reject(error)
    }
)
export default instance;