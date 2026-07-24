import onnxruntime as ort
import cv2
import multiprocessing
from PIL import ImageColor
import numpy as np
import logging
logger = logging.getLogger(__name__)
class ONNXDetection:
    def __init__(self, onnx_model,classes,confidence=0.5,iouthres=0.5,other_params=None,model_type="detect"):
        self.onnx_model = onnx_model
        self.classes = classes
        self.class_name = list(classes.keys())
        self.confidence = confidence
        self.iouthres = iouthres
        self.other_params = other_params or {}
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.model_type = model_type  
        
    def load_model(self):
        self.classes = {k: list(reversed(ImageColor.getrgb(v))) for k, v in self.classes.items()}
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        cpu_count = multiprocessing.cpu_count()
        sess_options.intra_op_num_threads = min(cpu_count, 4)  # 内部并行，限制最大4
        sess_options.inter_op_num_threads = 1  # 外部并行
        # 自动检测可用provider（更健壮）
        available_providers = ort.get_available_providers()
        providers = []
        if "CUDAExecutionProvider" in available_providers:
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")  # CPU始终可用
        self.session = ort.InferenceSession(self.onnx_model,sess_options=sess_options,providers=providers)
        # 获取模型输入信息
        self.model_inputs = self.session.get_inputs()
        input_shape = self.model_inputs[0].shape
        # 确定输入尺寸
        self.model_height = input_shape[2] if len(input_shape) >= 4 and isinstance(input_shape[2], int) else 640
        self.model_width = input_shape[3] if len(input_shape) >= 4 and isinstance(input_shape[3], int) else 640
        self.ndtype = np.half if self.model_inputs[0].type == "tensor(float16)" else np.single
        self.class_num = len(self.class_name)
    
    def preprocess_img(self, input_image):
        self.img = input_image.copy()
        self.img_height, self.img_width = self.img.shape[:2]
        img, ratio, (dw, dh) = self.letterbox(input_image, new_shape=(self.model_width, self.model_height))
        img = np.ascontiguousarray(np.einsum("HWC->CHW", img)[::-1], dtype=self.ndtype) / 255.0
        img_process = img[None] if len(img.shape) == 3 else img
        return img_process,ratio, (dw, dh)
    def letterbox(self, img, new_shape=(640, 640), color=(114, 114, 114)):
        """
        将图像进行 letterbox 填充，保持纵横比不变，并缩放到指定尺寸。
        """
        shape = img.shape[:2]  # 当前图像的宽高
        if isinstance(new_shape, int):new_shape = (new_shape, new_shape)
        #检测new_shape中的元素类型
        if not all(isinstance(x, int) for x in new_shape):new_shape=(640, 640)
        # 计算缩放比例
        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])  # 选择宽高中最小的缩放比
        new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))# 缩放后的未填充尺寸
        dw, dh = (new_shape[1] - new_unpad[0])/2, (new_shape[0] - new_unpad[1])/2  # 计算填充的尺寸
        # 缩放图像
        if shape[::-1] != new_unpad:  # 如果当前图像尺寸不等于 new_unpad，则缩放
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
        # 为图像添加边框以达到目标尺寸
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)#填充边框
        return img, (r, r), (dw, dh)
    def postprocess(self, input_image, output, ratio, dw, dh, nm=0):
        return_default = (input_image, {}, [],{})
        if self.model_type == "detect":
            x = output[0]
            if self.class_num <= 0:
                logger.error(f"The calculated number of categories {self.class_num} is invalid. Please check the nm parameter")
                return return_default
            x = np.einsum("bcn->bnc", x) # 转换维度
            # 使用动态计算的切片范围
            class_scores_start = 4
            class_scores_end = 4 + self.class_num
            if x.size>0:
                max_scores = np.amax(x[..., class_scores_start:class_scores_end], axis=-1)
                valid_mask = max_scores > self.confidence
                x = x[valid_mask]
                if len(x) == 0:return return_default
                max_class_scores = np.amax(x[..., class_scores_start:class_scores_end], axis=-1, keepdims=True)
                class_ids = np.argmax(x[..., class_scores_start:class_scores_end], axis=-1, keepdims=True)
                # 构建结果数组
                result = np.concatenate([
                    x[..., :4],  # 边界框坐标
                    max_class_scores,  # 最大类别置信度
                    class_ids,  # 类别ID
                    x[..., class_scores_end:]  # 掩膜部分（如果有）
                ], axis=-1)
                if len(result) > 0:
                    boxes = result[:, :4].tolist()
                    scores = result[:, 4].flatten().tolist()
                    indices = cv2.dnn.NMSBoxes(boxes, scores, self.confidence, self.iouthres)
                    if len(indices) > 0:
                        x = result[indices.flatten()]
                        # 边界框格式转换：从 cxcywh -> xyxy
                        x[..., [0, 1]] -= x[..., [2, 3]] / 2
                        x[..., [2, 3]] += x[..., [0, 1]]
                        x[..., :4] -= [dw, dh, dw, dh]
                        x[..., :4] /= min(ratio)
                        # 限制边界框在图像边界内
                        x[..., [0, 2]] = x[:, [0, 2]].clip(0, self.img_width)
                        x[..., [1, 3]] = x[:, [1, 3]].clip(0, self.img_height)
                        return self.draw_detect(input_image, x[..., :6])
                return return_default
            else:
                return return_default
    def draw_detect(self, input_image,boxes):
        count_labels = {}
        score_result = []
        label_box_datas={"type":"rectangle","datas":[]}
        if len(boxes) >0:
            for box in boxes:
                x1, y1, x2, y2, conf, class_id = box
                class_id = int(class_id)
                class_name = self.class_name[class_id]
                score = "{:.2f}".format(conf)
                label_box_datas["datas"].append({"label": class_name, "points": [[x1, y1],[ x2, y2]], "score": score,"class_id":class_id})
        return (input_image,count_labels,score_result,label_box_datas)
    def predict(self,input_image):
        img_data, ratio, (pad_w, pad_h) = self.preprocess_img(input_image)
        outputs = self.session.run(None, {self.model_inputs[0].name: img_data})
        return self.postprocess(input_image,outputs, ratio, pad_w, pad_h, 0)

