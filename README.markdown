# 在线YOLO目标检测工具 (Online YOLO Object Detection Toolkit)

本项目是一个基于Web的YOLO目标检测工具，允许用户上传数据集、进行模型微调、对模型进行验证，并最终使用训练好的模型进行在线推理。

## 主要功能

*   **用户认证**: 用户注册、登录、会话管理。
*   **模型推理 (Inference)**:
    *   用户上传图片。
    *   选择已有的预训练模型或用户自己训练的模型进行目标检测。
    *   实时显示检测结果。
*   **模型微调 (Finetune)**:
    *   创建微调任务，指定基础模型（预设或上传）。
    *   上传自定义数据集（YOLO格式的图片和标签，ZIP压缩包及`data.yaml`配置文件）。
    *   配置训练参数（如epochs, batch size, learning rate等）。
    *   异步执行微调任务，用户可查看任务列表、详情、进度和日志。
    *   下载训练完成的模型（如 `best.pt`, `last.pt`）。
    *   取消正在进行的微调任务。
    *   删除已完成或失败的微调任务及其关联文件。
*   **模型验证 (Validate)**:
    *   创建验证任务，选择待验证模型（用户上传的模型、推理库中的模型或微调任务的输出模型）。
    *   选择验证数据集（上传新数据集、使用微调任务的验证集或预设数据集）。
    *   配置验证参数。
    *   异步执行验证任务，用户可查看任务列表、详情、进度和日志。
    *   查看验证结果指标（如mAP, Precision, Recall）。
    *   下载验证相关的输出（如结果JSON、图表）。
    *   取消正在进行的验证任务。
    *   删除已完成或失败的验证任务及其关联文件。
*   **任务管理**:
    *   用户可以查看自己创建的所有微调和验证任务。
    *   实时轮询更新任务状态和进度。
    *   近似的排队位置信息展示。
*   **文件管理**:
    *   用户数据隔离，每个用户拥有独立的模型和任务文件存储空间。
    *   清晰的文件目录结构。

## 技术栈

*   **后端**:
    *   Python 3.x
    *   Flask (Web框架)
    *   Flask-Session (会话管理)
    *   SQLAlchemy (ORM)
    *   SQLite (数据库，易于部署和开发)
    *   Celery (分布式异步任务队列)
    *   Redis (Celery Broker 和 Result Backend)
    *   Ultralytics YOLO (v8 或更高版本，用于训练、验证和推理核心)
    *   Waitress (WSGI服务器，用于生产环境部署)
    *   PyYAML (处理YAML配置文件)
*   **前端**:
    *   HTML, CSS, JavaScript
*   **其他**:
    *   Git (版本控制)

## 项目结构

```
.
├── app/                      # Flask应用核心代码
│   ├── __init__.py           # 应用工厂，初始化Flask App, Celery, DB等
│   ├── auth/                 # 用户认证模块
│   ├── finetune/             # 微调模块 (routes, services, forms等)
│   ├── inference/            # 推理模块
│   ├── validate/             # 验证模块
│   ├── ultralyticsCust/      # 定制化的Ultralytics YOLO调用逻辑 (训练、验证函数，回调等)
│   ├── static/               # 静态文件 (CSS, JS, images)
│   ├── templates/            # HTML模板
│   ├── models.py             # SQLAlchemy数据库模型 (User, FinetuneTask, ValidateTask)
│   ├── database.py           # 数据库实例 (db = SQLAlchemy())
│   ├── config.py             # Flask配置加载类 (Config)
│   ├── celery_utils.py       # Celery辅助函数 (make_celery)
│   └── utils/                # 通用工具 (如装饰器)
├── cert/                     # SSL证书存放目录
├── migrations/               # 数据库迁移脚本
├── user_models/              # 用户数据存储根目录 (由程序创建)
│   └── <username>/
│       ├── inference_models/ # 用户上传的用于推理的模型
│       ├── train/            # 微调任务相关文件
│       │   └── <task_id>/
│       │       ├── input/
│       │       ├── dataset/
│       │       └── output/
│       └── val/              # 验证任务相关文件
│           └── <task_id>/
│               ├── input/
│               ├── dataset/
│               └── output/
├── user_uploads/             # 用户缓存数据存储根目录 (由程序创建)
├── models/                   # 预设模型存放目录 (如yolov8n.pt)
├── .flask_session/           # Flask-Session文件存储目录 (gitignore中应忽略)
├── celery_worker.py          # Celery Worker启动脚本
├── config.yaml               # 应用配置文件 (数据库URI, Celery Broker, 密钥等)
├── main.py                   # 应用启动脚本 (使用Waitress)
├── requirements.txt          # Python依赖包列表
└── README.md                 # 项目说明文件

```

## 安装与运行

### 1. 环境准备

*   Python 3.8+
*   Redis 服务器 (用于Celery Broker和Result Backend)
*   Git

### 2. 克隆项目

```bash
git clone <repository_url>
cd <project_directory>
```

### 3. 创建并激活虚拟环境

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 配置 `config.yaml`

*   **主要配置项**:
    *   `SECRET_KEY`: 设置一个复杂且唯一的密钥。
    *   `DATABASE_URI`: 默认为 `sqlite:///./database.db`。
    *   `CELERY_BROKER_URL`: 例如 `redis://localhost:6379/0`。
    *   `CELERY_RESULT_BACKEND`: 例如 `redis://localhost:6379/1`。
    *   `MODEL_DIR`: 用户模型存储的基础路径，例如 `user_models`。
    *   `PRESET_MODELS_DIR`:预设模型存放路径，例如 `models`。
    *   (可选) `CERT_FILE` 和 `KEY_FILE`: 如果使用HTTPS，配置SSL证书路径。

### 6. 初始化数据库

应用首次运行时，会自动根据 `app/models.py` 中的定义创建数据库表 (`database.db` 文件)。

### 7. 启动Redis服务器

确保你的Redis服务器正在运行，并且Celery配置中的URL是正确的。
例如：使用Docker启动Redis:
```bash
docker run -d -p 6379:6379 redis
```

### 8. 启动Celery Worker

打开一个新的终端，激活虚拟环境，然后运行：
```bash
celery -A celery_worker.celery_app worker -l info -P eventlet
```
(Windows用户如果遇到 `eventlet` 问题，可以尝试去掉 `-P eventlet` 或使用 `-P solo` 进行测试)
观察Celery Worker是否成功连接到Broker并声明已准备好接收任务。

### 9. 启动Flask应用 (Web服务器)

在另一个新的终端，激活虚拟环境，然后运行：
```bash
python main.py
```
应用将根据 `config.yaml` 中的 `SERVER_HOST` 和 `SERVER_PORT` (以及HTTPS配置) 启动。

### 10. 访问应用

在浏览器中打开应用地址 (例如 `http://localhost:你设置的端口` 或 `https://localhost:你设置的端口`)。

## 开发

*   **数据库迁移**: 如果对 `app/models.py` 中的模型进行了更改，需要相应地更新数据库。如果使用Flask-Migrate，可以使用其命令。对于SQLite的简单更改，有时删除旧的 `database.db` 文件并让应用重新创建它也是一种方法（仅限开发阶段！）。
*   **Celery任务**: 异步任务定义在 `celery_worker.py` 中。实际的业务逻辑（如YOLO训练/验证调用）应封装在 `app/ultralyticsCust/` 或相应的服务模块中，由Celery任务调用。
*   **日志**: 应用和Celery Worker都会产生日志，注意查看终端输出或配置的日志文件。

## 未来可能的改进

*   **WebSocket/Server-Sent Events (SSE)**: 用于任务状态和进度的实时更新，替代前端轮询。
*   **更细致的权限管理**
*   **支持更多模型类型和框架**。
*   **数据集版本控制与管理**。
*   **模型评估指标可视化** (使用Chart.js等)。
*   **更健壮的错误处理和重试机制**。
*   **单元测试和集成测试**。
*   **使用更生产级的数据库** (如PostgreSQL, MySQL) 替代SQLite。
*   **更详细的Celery监控** (使用Flower等工具)。
*   **任务优先级队列**。

## 贡献

*   **此开源项目由露露个人开发**。

## 许可证

本项目根据 [MIT 许可证](LICENSE) 发布。详情请见 `LICENSE` 文件。

This project is licensed under the [MIT License](LICENSE). See the `LICENSE` file for details.

```