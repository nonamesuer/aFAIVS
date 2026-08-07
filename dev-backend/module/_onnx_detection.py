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
        self.low_confidence = max(0.01,min(float(self.other_params.get("lowConfidence",confidence)),float(confidence)))
        self.top_k = max(2,int(self.other_params.get("topK",3)))
        
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
                class_scores = x[..., class_scores_start:class_scores_end]
                max_scores = np.amax(class_scores, axis=-1)
                valid_mask = max_scores > self.low_confidence
                x = x[valid_mask]
                if len(x) == 0:return return_default
                filtered_scores = class_scores[valid_mask];class_ids = np.argmax(filtered_scores,axis=-1);scores = np.amax(filtered_scores,axis=-1)
                if len(x) > 0:
                    boxes = x[:,:4].copy();boxes[:,0] -= boxes[:,2]/2;boxes[:,1] -= boxes[:,3]/2
                    indices = cv2.dnn.NMSBoxes(boxes.tolist(),scores.tolist(),self.low_confidence,self.iouthres)
                    if len(indices) > 0:
                        selected = indices.flatten();selected_boxes = x[selected,:4].copy();selected_scores = filtered_scores[selected];selected_class_ids = class_ids[selected]
                        # 边界框格式转换：从 cxcywh -> xyxy
                        selected_boxes[..., [0, 1]] -= selected_boxes[..., [2, 3]] / 2
                        selected_boxes[..., [2, 3]] += selected_boxes[..., [0, 1]]
                        selected_boxes -= [dw, dh, dw, dh]
                        selected_boxes /= min(ratio)
                        # 限制边界框在图像边界内
                        selected_boxes[..., [0, 2]] = selected_boxes[:, [0, 2]].clip(0, self.img_width)
                        selected_boxes[..., [1, 3]] = selected_boxes[:, [1, 3]].clip(0, self.img_height)
                        return self.draw_detect(input_image,selected_boxes,selected_scores,selected_class_ids)
                return return_default
            else:
                return return_default
    def draw_detect(self,input_image,boxes,class_scores,class_ids):
        count_labels = {}
        score_result = []
        label_box_datas={"type":"rectangle","datas":[]}
        if len(boxes) >0:
            for box,scores,class_id in zip(boxes,class_scores,class_ids):
                x1,y1,x2,y2 = box;class_id = int(class_id);conf = float(scores[class_id])
                class_name = self.class_name[class_id]
                top_indices = np.argsort(scores)[::-1][:self.top_k]
                top_k = [{"label":self.class_name[int(index)],"score":round(float(scores[index]),4)} for index in top_indices]
                label_box_datas["datas"].append({"label":class_name,"points":[[float(x1),float(y1)],[float(x2),float(y2)]],"score":round(conf,4),"class_id":class_id,"top_k":top_k,"high_confidence":conf >= self.confidence})
        return (input_image,count_labels,score_result,label_box_datas)
    def predict(self,input_image):
        img_data, ratio, (pad_w, pad_h) = self.preprocess_img(input_image)
        outputs = self.session.run(None, {self.model_inputs[0].name: img_data})
        return self.postprocess(input_image,outputs, ratio, pad_w, pad_h, 0)
