# app/ultralyticsCust/validation.py
import os
import json
import logging
from ultralytics import YOLO
from typing import Dict, Any, Tuple


def run_yolo_validation(
        model_path: str,  # 待验证模型的路径
        data_yaml_path: str,  # 数据集配置文件路径 (data.yaml)
        project_path: str,  # YOLO验证输出的根目录
        run_name: str,  # YOLO验证运行的名称
        validation_params: Dict[str, Any],  # 包含 batch, imgsz, conf, iou, device, etc.
        # log_file_path: str, # YOLOv8 会在 project_path/run_name 下自动生成日志
        logger: logging.Logger = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    执行 YOLO 模型验证。

    :param model_path: 待验证模型的路径。
    :param data_yaml_path: 数据集配置文件的路径。
    :param project_path: 验证输出的根目录。
    :param run_name: 本次验证的名称。
    :param validation_params: 验证参数字典。
    :param logger: 日志记录器。
    :return: (success_flag, message_or_error, results_metrics_dict)
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        if not logger.hasHandlers():
            logger.addHandler(logging.StreamHandler())

    logger.info(f"开始 YOLO 验证: model={model_path}, data={data_yaml_path}, project={project_path}, name={run_name}")
    logger.info(f"验证参数: {validation_params}")

    if not os.path.exists(model_path):
        msg = f"模型文件未找到: {model_path}"
        logger.error(msg)
        return False, msg, {}
    if not os.path.exists(data_yaml_path):
        msg = f"数据集配置文件未找到: {data_yaml_path}"
        logger.error(msg)
        return False, msg, {}

    try:
        model = YOLO(model_path)

        # Ultralytics YOLOv8 的 val 方法参数
        # 常见参数: data, batch, imgsz, conf, iou, device, project, name, plots, save_json, save_hybrid
        yolo_val_args = {
            'data': data_yaml_path,
            'project': project_path,
            'name': run_name,
            'save_json': True,  # 确保保存JSON格式的结果，方便解析
            'plots': validation_params.get('plots', True),  # 通常需要绘图
            **validation_params  # 解包用户传入的参数
        }

        logger.info(f"传递给 YOLO.val() 的参数: {yolo_val_args}")

        # 执行验证
        metrics = model.val(**yolo_val_args)

        # metrics 对象 (例如 ultralyticsCBAM.engine.results.Metrics) 包含各种指标
        # metrics.box.map (mAP50-95), metrics.box.map50 (mAP50), metrics.box.map75 (mAP75)
        # metrics.box.precision, metrics.box.recall
        # results.speed (preprocess, inference, postprocess times)

        # metrics.save_dir 是输出目录
        output_dir = metrics.save_dir

        # Ultralytics 会在 output_dir 下生成一个json文件，例如 coco_ evaluarion_results.json 或类似名称
        # 或者 metrics.results_dict 包含这些信息
        # 我们直接使用 metrics 对象提取指标

        results_metrics = {
            "mAP50-95(B)": round(metrics.box.map, 5) if hasattr(metrics.box, 'map') else None,
            "mAP50(B)": round(metrics.box.map50, 5) if hasattr(metrics.box, 'map50') else None,
            "mAP75(B)": round(metrics.box.map75, 5) if hasattr(metrics.box, 'map75') else None,
            "Precision(B)": round(metrics.box.mp, 5) if hasattr(metrics.box, 'mp') else (
                round(metrics.box.p[0], 5) if hasattr(metrics.box, 'p') and metrics.box.p else None),
            # metrics.box.p 是一个列表，通常取第一个
            "Recall(B)": round(metrics.box.mr, 5) if hasattr(metrics.box, 'mr') else (
                round(metrics.box.r[0], 5) if hasattr(metrics.box, 'r') and metrics.box.r else None),
            # metrics.box.r 是一个列表
            "Fitness": round(metrics.fitness, 5) if hasattr(metrics, 'fitness') else None,
            "Speed_preprocess_ms": metrics.speed['preprocess'] if 'preprocess' in metrics.speed else None,
            "Speed_inference_ms": metrics.speed['inference'] if 'inference' in metrics.speed else None,
            "Speed_postprocess_ms": metrics.speed['postprocess'] if 'postprocess' in metrics.speed else None,
            "output_directory": str(output_dir)
        }
        # 移除值为None的键，使结果更干净
        results_metrics = {k: v for k, v in results_metrics.items() if v is not None}

        logger.info(f"验证成功完成。指标: {results_metrics}")
        logger.info(f"验证输出保存在: {output_dir}")

        return True, "验证成功完成。", results_metrics

    except Exception as e:
        logger.error(f"YOLO 验证过程中发生严重错误: {str(e)}", exc_info=True)
        return False, f"YOLO 验证失败: {str(e)}", {}