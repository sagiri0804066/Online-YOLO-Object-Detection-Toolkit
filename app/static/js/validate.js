/**
 * @file validate.js
 * @description 处理验证任务相关的客户端逻辑，包括表单交互、任务提交、任务列表展示和详情查看。
 */

document.addEventListener('DOMContentLoaded', () => {
    const validateSection = document.getElementById('validate-content');
    // 如果验证内容区域不存在，则不执行后续代码
    if (!validateSection) return;

    // 获取DOM元素
    const taskNameInput = document.getElementById('validate-task-name-input');
    const uploadModelButton = document.getElementById('validate-upload-model-button');
    const modelFileInput = document.getElementById('validate-model-file-input');
    const clearModelButton = validateSection.querySelector('.model-selection-section .clear-model-button');
    const uploadModelButtonText = uploadModelButton.querySelector('.button-text');

    const uploadDatasetButton = document.getElementById('validate-upload-dataset-button');
    const datasetFileInput = document.getElementById('validate-dataset-file-input');
    const clearDatasetButton = validateSection.querySelector('.dataset-upload-section .clear-dataset-button');
    const uploadDatasetButtonText = uploadDatasetButton.querySelector('.button-text');
    const uploadDatasetDefaultIcon = uploadDatasetButton.querySelector('.default-icon');
    const uploadDatasetUploadedIcon = uploadDatasetButton.querySelector('.uploaded-icon');

    const uploadYamlButton = document.getElementById('validate-upload-yaml-button');
    const yamlFileInput = document.getElementById('validate-yaml-file-input');
    const yamlFileNameDisplay = document.getElementById('validate-yaml-filename');
    const uploadYamlButtonText = uploadYamlButton.querySelector('.button-text');

    const startValidateButton = document.getElementById('validate-start-button');

    // 验证参数与对应HTML元素ID的映射
    const validationParamsMap = {
        batch: 'validate-batch-size', imgsz: 'validate-imgsz',
        conf: 'validate-conf-thres', iou: 'validate-iou-thres',
        split: 'validate-split', max_det: 'validate-max-det',
        half: 'validate-half', save_json: 'validate-save-json',
        plots: 'validate-plots', save_txt: 'validate-save-txt',
        augment: 'validate-augment', rect: 'validate-rect'
    };

    // 状态变量，存储选中的文件
    let selectedModelFile = null;
    let selectedDatasetZipFile = null;
    let selectedYamlFile = null;

    // 按钮的原始文本，用于重置
    const originalUploadModelBtnText = "上传待验证模型";
    const originalUploadDatasetBtnText = "上传数据集";
    const originalUploadYamlBtnText = "配置 data.yaml";

    /**
     * @function getParamsFromForm
     * @description 从表单元素中提取参数值。
     * @param {object} paramsMap - 参数键与HTML元素ID的映射。
     * @returns {object} 提取的参数对象。
     */
    function getParamsFromForm(paramsMap) {
        const params = {};
        for (const key in paramsMap) {
            const element = document.getElementById(paramsMap[key]);
            if (element) {
                if (element.type === 'checkbox') {
                    params[key] = element.checked;
                } else if (element.type === 'number' || element.type === 'range') {
                    const val = parseFloat(element.value);
                    params[key] = isNaN(val) ? element.value : val;
                } else if (element.tagName === 'SELECT') {
                    // 将字符串 'true'/'false' 转换为布尔值
                    if (element.value === 'true') params[key] = true;
                    else if (element.value === 'false') params[key] = false;
                    else params[key] = element.value;
                } else {
                    params[key] = element.value;
                }
            }
        }
        return params;
    }

    /**
     * @function resetFileInput
     * @description 重置文件输入框及其相关的UI元素。
     * @param {HTMLInputElement} fileInput - 文件输入框元素。
     * @param {HTMLElement} buttonTextElement - 显示文件名的按钮内文本元素。
     * @param {string} originalText - 按钮的原始文本。
     * @param {HTMLElement} clearButton - 清除按钮元素。
     * @param {HTMLElement} [iconDefault] - (可选) 默认状态图标。
     * @param {HTMLElement} [iconUploaded] - (可选) 已上传状态图标。
     * @param {function} stateVariableSetter - 用于重置对应状态变量的函数。
     */
    function resetFileInput(fileInput, buttonTextElement, originalText, clearButton, iconDefault, iconUploaded, stateVariableSetter) {
        fileInput.value = null; // 清空文件输入框
        if (buttonTextElement) buttonTextElement.textContent = originalText;
        if (clearButton) clearButton.classList.add('hidden');
        if (iconDefault) iconDefault.classList.remove('hidden');
        if (iconUploaded) iconUploaded.classList.add('hidden');
        // 移除按钮的选中状态样式
        if (buttonTextElement && buttonTextElement.parentElement.classList.contains('upload-button-styled')) {
            buttonTextElement.parentElement.classList.remove('file-selected');
        }
        stateVariableSetter(null); // 重置对应的状态变量
    }

    /**
     * @function getDisplayStatus
     * @description 将任务状态键映射为用户友好的显示文本。
     * @param {string} statusKey - 内部状态键。
     * @returns {string} 显示用的状态文本。
     */
    function getDisplayStatus(statusKey) {
        const statusMap = {
            'pending': '已提交',
            'queued': '排队中',
            'running': '进行中',
            'completed': '已成功',
            'failed': '已失败',
            'cancelled': '已取消'
        };
        return statusMap[statusKey] || statusKey; // 如果没有匹配项，返回原始键
    }

    // --- 事件监听器 ---

    // 模型文件上传按钮点击事件
    uploadModelButton.addEventListener('click', () => modelFileInput.click());
    // 模型文件输入框文件选择事件
    modelFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedModelFile = file;
            // 显示文件名，过长则截断
            uploadModelButtonText.textContent = `已选: ${file.name.length > 20 ? file.name.substring(0,17)+'...' : file.name}`;
            uploadModelButton.classList.add('file-selected');
            clearModelButton.classList.remove('hidden');
            uploadModelButton.title = file.name; // 完整文件名作为title
        } else {
            // 如果用户取消选择，且之前没有文件，则重置
            if (!selectedModelFile) {
                resetFileInput(modelFileInput, uploadModelButtonText, originalUploadModelBtnText, clearModelButton, null, null, (val) => selectedModelFile = val);
                uploadModelButton.title = '';
            }
        }
    });
    // 清除模型文件按钮点击事件
    clearModelButton.addEventListener('click', () => {
        resetFileInput(modelFileInput, uploadModelButtonText, originalUploadModelBtnText, clearModelButton, null, null, (val) => selectedModelFile = val);
        uploadModelButton.title = '';
    });

    // 数据集文件上传按钮点击事件
    uploadDatasetButton.addEventListener('click', () => datasetFileInput.click());
    // 数据集文件输入框文件选择事件
    datasetFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedDatasetZipFile = file;
            // 显示文件名，过长则截断
            uploadDatasetButtonText.textContent = `已选: ${file.name.length > 20 ? file.name.substring(0,17)+'...' : file.name}`;
            uploadDatasetDefaultIcon.classList.add('hidden');
            uploadDatasetUploadedIcon.classList.remove('hidden');
            clearDatasetButton.classList.remove('hidden');
            uploadDatasetButton.classList.add('file-selected');
            uploadDatasetButton.title = file.name; // 完整文件名作为title
        } else {
             // 如果用户取消选择，且之前没有文件，则重置
            if (!selectedDatasetZipFile) {
                resetFileInput(datasetFileInput, uploadDatasetButtonText, originalUploadDatasetBtnText, clearDatasetButton, uploadDatasetDefaultIcon, uploadDatasetUploadedIcon, (val) => selectedDatasetZipFile = val);
                uploadDatasetButton.title = '';
            }
        }
    });
    // 清除数据集文件按钮点击事件
    clearDatasetButton.addEventListener('click', () => {
        resetFileInput(datasetFileInput, uploadDatasetButtonText, originalUploadDatasetBtnText, clearDatasetButton, uploadDatasetDefaultIcon, uploadDatasetUploadedIcon, (val) => selectedDatasetZipFile = val);
        uploadDatasetButton.title = '';
    });

    // YAML文件上传按钮点击事件
    uploadYamlButton.addEventListener('click', () => yamlFileInput.click());
    // YAML文件输入框文件选择事件
    yamlFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedYamlFile = file;
            yamlFileNameDisplay.textContent = `已配置: ${file.name}`;
            uploadYamlButtonText.textContent = '重选 data.yaml';
            uploadYamlButton.title = file.name; // 完整文件名作为title
        } else {
            // 如果用户取消选择，且之前没有文件，则重置
            if (!selectedYamlFile) {
                selectedYamlFile = null;
                yamlFileNameDisplay.textContent = '';
                uploadYamlButtonText.textContent = originalUploadYamlBtnText;
                uploadYamlButton.title = '';
            }
        }
    });

    // 开始验证按钮点击事件
    startValidateButton.addEventListener('click', async () => {
        const taskName = taskNameInput.value.trim();

        // 客户端输入校验
        if (!taskName) {
            showNotification(1, '请输入任务名称。');
            taskNameInput.focus();
            return;
        }
        if (!selectedModelFile) {
            showNotification(1, '请上传一个待验证的模型文件 (.pt)。');
            return;
        }
        if (!selectedDatasetZipFile) {
            showNotification(1, '请上传验证数据集文件 (.zip)。');
            return;
        }
        if (!selectedYamlFile) {
            showNotification(1, '请上传 data.yaml 配置文件。');
            return;
        }

        const validationParameters = getParamsFromForm(validationParamsMap);

        // 构建FormData对象用于文件上传和参数传递
        const formData = new FormData();
        formData.append('task_name', taskName);
        formData.append('model_source_type', 'upload'); // 模型来源类型
        formData.append('model_file_upload', selectedModelFile); // 模型文件
        formData.append('dataset_source_type', 'upload'); // 数据集来源类型
        formData.append('dataset_zip_upload', selectedDatasetZipFile); // 数据集zip文件
        formData.append('dataset_yaml_upload', selectedYamlFile); // 数据集yaml文件
        formData.append('validation_params', JSON.stringify(validationParameters)); // 验证参数

        console.log("--- 验证任务提交数据 (文件内容未打印) ---");
        for (var pair of formData.entries()) {
           console.log(pair[0]+ ': ' + (pair[1] instanceof File ? pair[1].name : pair[1]));
        }

        startValidateButton.disabled = true; // 禁用按钮防止重复提交
        try {
            // 调用后端API创建验证任务
            const result = await createValidateTask(formData);
            showNotification(2, result.message || `验证任务 "${taskName}" (ID: ${result.task_id || result.id}) 已成功创建。`);
            // 刷新任务列表
            fetchValidateTasksAndUpdateList();
        } catch (error) {
            console.error("创建验证任务时出错:", error);
            showNotification(0, `创建验证任务失败: ${error.message}`);
        } finally {
            startValidateButton.disabled = false; // 恢复按钮可用状态
        }
    });

    // --- UI 初始化 ---
    // 初始化时隐藏清除按钮和数据集上传图标
    if (clearModelButton) clearModelButton.classList.add('hidden');
    if (clearDatasetButton) clearDatasetButton.classList.add('hidden');
    if (uploadDatasetUploadedIcon) uploadDatasetUploadedIcon.classList.add('hidden');
    if (uploadDatasetDefaultIcon) uploadDatasetDefaultIcon.classList.remove('hidden');

    // --- 任务列表与详情轮询状态变量 ---
    let validateListPollingIntervalId = null; // 列表轮询定时器ID
    const POLLING_INTERVAL_MS_VALIDATE_LIST = 10000; // 列表轮询间隔 (10秒)
    let currentDetailTaskId_Validate = null; // 当前正在查看详情的任务ID
    let taskDetailPollingIntervalId_Validate = null; // 详情轮询定时器ID
    const TASK_DETAIL_POLLING_INTERVAL_MS_VALIDATE = 5000; // 详情轮询间隔 (5秒)

    /**
     * @function createValidateTaskListItem
     * @description 创建验证任务列表项的 DOM 元素。
     * @param {object} task - 任务对象。
     * @returns {HTMLElement} 列表项 DOM 元素。
     */
    function createValidateTaskListItem(task) {
        const listItem = document.createElement('div');
        listItem.classList.add('task-list-item');
        listItem.dataset.taskId = task.task_id; // 存储任务ID

        const nameSpan = document.createElement('span');
        nameSpan.classList.add('validate-col-name');
        nameSpan.textContent = task.task_name;
        nameSpan.title = task.task_name; // 完整名称作为title

        const pidSpan = document.createElement('span');
        pidSpan.classList.add('validate-col-pid');
        pidSpan.textContent = task.task_id;

        const statusSpan = document.createElement('span');
        statusSpan.classList.add('validate-col-status', `status-${task.status}`); // 添加状态对应的类名
        statusSpan.textContent = getDisplayStatus(task.status);

        const actionsSpan = document.createElement('span');
        actionsSpan.classList.add('validate-col-actions');

        const detailsButton = document.createElement('button');
        detailsButton.classList.add('task-action-button', 'details-task-button');
        detailsButton.textContent = '详情';
        // 点击详情按钮显示弹窗
        detailsButton.addEventListener('click', (event) => {
            event.stopPropagation(); // 阻止事件冒泡到列表项本身
            showValidateTaskDetailsPopup(task);
        });

        const deleteButton = document.createElement('button');
        deleteButton.classList.add('task-action-button', 'delete-task-button');
        deleteButton.textContent = '删除';
        // 删除按钮事件通过事件委托处理 (见下方)

        actionsSpan.appendChild(detailsButton);
        actionsSpan.appendChild(deleteButton);

        listItem.appendChild(nameSpan);
        listItem.appendChild(pidSpan);
        listItem.appendChild(statusSpan);
        listItem.appendChild(actionsSpan);

        return listItem;
    }

    /**
     * @function populateValidateTaskList
     * @description 填充验证任务列表。
     * @param {Array|null} tasks - 任务对象数组，或在出错时为 null。
     */
    function populateValidateTaskList(tasks) {
        const listContainer = document.getElementById('validate-task-list-container');
        const noTasksMessage = document.getElementById('no-validate-tasks-message');
        const validateTasksContentElement = document.getElementById('validate-tasks-content');
        let header = null;

        // 获取列表头部元素
        if (validateTasksContentElement) {
            header = validateTasksContentElement.querySelector('.task-list-header.validate-header');
        }

        // 检查必要的UI元素是否存在
        if (!listContainer || !noTasksMessage || !header) {
            console.error('验证任务列表UI元素未找到。');
            return;
        }

        listContainer.innerHTML = ''; // 清空当前列表

        if (tasks && tasks.length === 0) {
            // 没有任务时显示消息
            noTasksMessage.classList.remove('hidden');
            noTasksMessage.textContent = "当前没有验证任务。";
            listContainer.classList.add('hidden');
            header.classList.add('hidden');
        } else if (tasks && tasks.length > 0) {
            // 有任务时隐藏消息，显示列表和头部
            noTasksMessage.classList.add('hidden');
            listContainer.classList.remove('hidden');
            header.classList.remove('hidden');
            // 遍历任务数组，创建并添加列表项
            tasks.forEach(task => {
                const listItem = createValidateTaskListItem(task);
                listContainer.appendChild(listItem);
            });
        } else if (tasks === null) {
            // 获取任务失败时显示错误消息
            noTasksMessage.classList.remove('hidden');
            noTasksMessage.textContent = "无法加载验证任务列表。";
            listContainer.classList.add('hidden');
            header.classList.add('hidden');
        } else {
            // 数据格式异常时显示错误消息
            noTasksMessage.classList.remove('hidden');
            noTasksMessage.textContent = "验证任务列表数据异常。";
            listContainer.classList.add('hidden');
            header.classList.add('hidden');
        }
    }

    /**
     * @function populateValidateTaskDetailsModalContent
     * @description 填充验证任务详情弹窗的内容。
     * @param {object} task - 任务对象。
     * @param {HTMLElement} taskDetailsBody - 弹窗内容主体区域。
     * @param {HTMLElement} taskDetailsFooter - 弹窗底部操作区域。
     */
    function populateValidateTaskDetailsModalContent(task, taskDetailsBody, taskDetailsFooter) {
        taskDetailsBody.innerHTML = ''; // 清空主体内容
        taskDetailsFooter.innerHTML = ''; // 清空底部操作

        // 辅助函数：创建详情项
        function createDetailItem(label, value, allowNewline = false) {
            const item = document.createElement('div');
            item.classList.add('detail-item');
            const labelSpan = document.createElement('span');
            labelSpan.classList.add('detail-label');
            labelSpan.textContent = label;
            const valueSpan = document.createElement('span');
            valueSpan.classList.add('detail-value');
            if (allowNewline) valueSpan.classList.add('allow-newline');
            valueSpan.textContent = value;
            item.appendChild(labelSpan);
            item.appendChild(valueSpan);
            return item;
        }

        // 辅助函数：创建带进度条的详情项
        function createProgressDetailItem(label, currentValue, maxValue, displayText) {
            const item = document.createElement('div');
            item.classList.add('progress-detail-item');
            const labelSpan = document.createElement('span');
            labelSpan.classList.add('detail-label');
            labelSpan.textContent = label;
            item.appendChild(labelSpan);

            const contentDiv = document.createElement('div');
            contentDiv.classList.add('progress-detail-content');
            const progressBarDiv = document.createElement('div');
            progressBarDiv.classList.add('detail-progress-bar');
            const progressBarInnerDiv = document.createElement('div');
            progressBarInnerDiv.classList.add('detail-progress-bar-inner');
            // 计算进度百分比，并限制在0-100之间
            const percentage = maxValue > 0 && currentValue >= 0 ? (currentValue / maxValue) * 100 : 0;
            progressBarInnerDiv.style.width = `${Math.min(100, Math.max(0, percentage))}%`;
            progressBarDiv.appendChild(progressBarInnerDiv);
            contentDiv.appendChild(progressBarDiv);

            const textSpan = document.createElement('span');
            textSpan.classList.add('progress-text');
            textSpan.textContent = displayText;
            contentDiv.appendChild(textSpan);
            item.appendChild(contentDiv);
            return item;
        }

        // 填充基本详情
        taskDetailsBody.appendChild(createDetailItem('任务名称:', task.task_name));
        taskDetailsBody.appendChild(createDetailItem('任务ID:', task.task_id));
        const statusDisplay = getDisplayStatus(task.status);
        const statusItem = createDetailItem('任务状态:', statusDisplay);
        const statusValueSpan = statusItem.querySelector('.detail-value');
        if (statusValueSpan) statusValueSpan.classList.add(`status-${task.status}`); // 添加状态对应的类名
        taskDetailsBody.appendChild(statusItem);

        // 根据任务状态填充特定内容
        switch (task.status) {
            case 'running':
                // task.progress 对应后端返回的 details.progress 对象
                if (task.progress) {
                    let currentProgValue = 0;
                    let totalProgValue = 0;
                    let progressDisplayMessage = '进行中...'; // 默认显示文本

                    // 后端字段
                    const backendCurrent = task.progress.current_progress;
                    const backendTotal = task.progress.total_progress;
                    const backendText = task.progress.progress_text;
                    const backendSpeed = task.progress.speed;

                    // 如果后端提供了文本，优先使用
                    if (backendText && backendText.trim() !== '') {
                        progressDisplayMessage = backendText;
                    }

                    let canShowProgressBar = false;

                    // 优先级 1: 优先使用后端直接提供的数值进度
                    if (typeof backendCurrent === 'number' &&
                        typeof backendTotal === 'number' &&
                        backendTotal > 0) {

                        currentProgValue = Math.min(backendCurrent, backendTotal); // 确保当前值不超过总值
                        totalProgValue = backendTotal;
                        canShowProgressBar = true;

                        const percentage = (currentProgValue / totalProgValue) * 100;
                        const numericProgressStr = `${currentProgValue}/${totalProgValue}`;
                        const percentageStr = `${percentage.toFixed(1)}%`;

                        // 如果默认文本或后端文本不包含进度信息，则补充
                        if (progressDisplayMessage === '进行中...' || !/[\d%]/g.test(progressDisplayMessage)) {
                            progressDisplayMessage = `${percentageStr} (${numericProgressStr})`;
                        } else {
                             // 如果后端文本已有进度信息，尝试合并或保持
                            const hasPercentageInText = progressDisplayMessage.includes('%');
                            const hasNumericStepsInText = /\d+\/\d+/.test(progressDisplayMessage);

                            if (hasNumericStepsInText && !hasPercentageInText) {
                                progressDisplayMessage = `${percentageStr} (${progressDisplayMessage})`;
                            } else if (hasPercentageInText && !hasNumericStepsInText && !progressDisplayMessage.includes('(') && !progressDisplayMessage.includes(')')) {
                                progressDisplayMessage = `${progressDisplayMessage} (${numericProgressStr})`;
                            }
                            // 如果后端文本已经很完整，则保持原样
                        }
                    }
                    // 优先级 2: 如果数值进度缺失或无效，尝试从 progress_text 中解析
                    else if (backendText) {
                        const matchSteps = backendText.match(/(\d+)\s*\/\s*(\d+)/);
                        const matchPercentage = backendText.match(/([\d.]+)\s*%/);

                        if (matchSteps && parseInt(matchSteps[2], 10) > 0) {
                            currentProgValue = parseInt(matchSteps[1], 10);
                            totalProgValue = parseInt(matchSteps[2], 10);
                            currentProgValue = Math.min(currentProgValue, totalProgValue);
                            canShowProgressBar = true;
                        } else if (matchPercentage) {
                            currentProgValue = parseFloat(matchPercentage[1]);
                            totalProgValue = 100; // 按百分比计算时总进度为100
                            currentProgValue = Math.min(currentProgValue, totalProgValue);
                            canShowProgressBar = true;
                        }
                    }

                    // 如果能显示进度条，则创建进度条详情项，否则创建普通详情项
                    if (canShowProgressBar) {
                        taskDetailsBody.appendChild(createProgressDetailItem('验证进度:', currentProgValue, totalProgValue, progressDisplayMessage));
                    } else {
                        taskDetailsBody.appendChild(createDetailItem('验证进度:', progressDisplayMessage));
                    }

                    // 显示速度信息
                    if (backendSpeed) {
                        taskDetailsBody.appendChild(createDetailItem('验证速度:', backendSpeed));
                    }

                } else {
                    taskDetailsBody.appendChild(createDetailItem('进度:', '正在获取进度...'));
                }
                break;
            case 'queued':
                // 显示排队位置
                if (task.queue_position && typeof task.queue_position.position === 'number' && typeof task.queue_position.total === 'number') {
                    taskDetailsBody.appendChild(createDetailItem('当前排队:', `${task.queue_position.position} / ${task.queue_position.total}`));
                } else {
                    taskDetailsBody.appendChild(createDetailItem('排队位置:', '正在获取...'));
                }
                break;
            case 'failed':
                // 显示错误信息
                taskDetailsBody.appendChild(createDetailItem('错误代码:', task.error_code || '未知错误'));
                if (task.error_message) {
                    taskDetailsBody.appendChild(createDetailItem('详细信息:', task.error_message, true)); // 允许换行显示详细信息
                }
                break;
            case 'completed':
                // 显示完成信息和结果
                taskDetailsBody.appendChild(createDetailItem('信息:', '验证已成功完成。'));

                if (task.results_json && typeof task.results_json === 'object') {
                    const results = task.results_json;

                    // --- 性能指标 ---
                    taskDetailsBody.appendChild(createDetailItem('性能指标:'));

                    const performanceMetrics = [
                        { label: ' - mAP50-95', key: 'mAP50-95(B)', unit: '%', multiplier: 100, fixed: 2 },
                        { label: ' - mAP50', key: 'mAP50(B)', unit: '%', multiplier: 100, fixed: 2 },
                        { label: ' - 精确率 (P)', key: 'Precision(B)', unit: '%', multiplier: 100, fixed: 2 },
                        { label: ' - 召回率 (R)', key: 'Recall(B)', unit: '%', multiplier: 100, fixed: 2 },
                        { label: ' - 适应度 (Fitness)', key: 'Fitness', unit: '', multiplier: 1, fixed: 5 }
                    ];

                    performanceMetrics.forEach(metric => {
                        if (results[metric.key] !== undefined && results[metric.key] !== null) {
                            let value = parseFloat(results[metric.key]);
                            if (isNaN(value)) {
                                 taskDetailsBody.appendChild(createDetailItem(metric.label + ':', 'N/A (数据无效)'));
                            } else {
                                value = value * metric.multiplier;
                                taskDetailsBody.appendChild(createDetailItem(metric.label + ':', `${value.toFixed(metric.fixed)}${metric.unit}`));
                            }
                        } else {
                            taskDetailsBody.appendChild(createDetailItem(metric.label + ':', 'N/A'));
                        }
                    });

                    // --- 速度指标 (每张图片) ---
                    taskDetailsBody.appendChild(createDetailItem('速度指标:'));

                    const speedKeys = {
                        preprocess: 'Speed_preprocess_ms',
                        inference: 'Speed_inference_ms',
                        postprocess: 'Speed_postprocess_ms'
                    };

                    let totalSpeed = 0;
                    let allSpeedsAvailable = true;

                    const speedMetricsDisplay = [
                        { label: ' - 预处理时间', key: speedKeys.preprocess },
                        { label: ' - 推理时间', key: speedKeys.inference },
                        { label: ' - 后处理时间', key: speedKeys.postprocess }
                    ];

                    speedMetricsDisplay.forEach(metric => {
                        if (results[metric.key] !== undefined && results[metric.key] !== null) {
                            let value = parseFloat(results[metric.key]);
                            if (isNaN(value)) {
                                taskDetailsBody.appendChild(createDetailItem(metric.label + ':', 'N/A (数据无效)'));
                                allSpeedsAvailable = false;
                            } else {
                                totalSpeed += value;
                                taskDetailsBody.appendChild(createDetailItem(metric.label + ':', `${value.toFixed(2)} ms`));
                            }
                        } else {
                            taskDetailsBody.appendChild(createDetailItem(metric.label + ':', 'N/A'));
                            allSpeedsAvailable = false;
                        }
                    });

                    // 如果单个速度不可用，总速度也标记为不可用或部分数据缺失
                    if (allSpeedsAvailable) {
                        taskDetailsBody.appendChild(createDetailItem('-总处理时间:', `${totalSpeed.toFixed(2)} ms`));
                    } else {
                        taskDetailsBody.appendChild(createDetailItem('-总处理时间:', 'N/A (部分数据缺失)'));
                    }

                } else {
                    const noResultsText = document.createElement('p');
                    noResultsText.textContent = '详细的验证结果数据不可用。';
                    noResultsText.style.marginTop = '10px';
                    taskDetailsBody.appendChild(noResultsText);
                }
                break;
            case 'cancelled':
                taskDetailsBody.appendChild(createDetailItem('信息:', '任务已被用户取消。'));
                break;
            default:
                // 处理未知状态
                taskDetailsBody.appendChild(createDetailItem('状态:', (task.status || '未知状态').toString()));
                break;
        }

        // 添加下载日志按钮
        const downloadLogButton = document.createElement('button');
        downloadLogButton.classList.add('task-action-button', 'download-log-button');
        downloadLogButton.textContent = '下载日志';
        downloadLogButton.addEventListener('click', async () => {
            try {
                const logData = await getValidateTaskLogs(task.task_id);
                if (logData && typeof logData.logs === 'string') {
                    if (logData.logs.trim() === "") {
                         showNotification(1, `任务 ${task.task_id} 的日志为空。`);
                         return;
                    }
                    // 创建Blob并下载
                    const blob = new Blob([logData.logs], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${task.task_name || 'validate_task'}_${task.task_id}_logs.txt`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url); // 释放URL对象
                } else {
                    showNotification(0, `任务 ${task.task_id} 的日志为空或不可用。`);
                }
            } catch (error) {
                console.error(`下载/获取验证任务 ${task.task_id} 日志时出错:`, error);
                showNotification(0, `获取/下载日志失败: ${error.message}`);
            }
        });

        // 添加主要操作按钮 (取消或下载结果)
        const mainActionButton = document.createElement('button');
        mainActionButton.classList.add('task-action-button', 'main-action-button');

        if (task.status === 'running' || task.status === 'pending' || task.status === 'queued') {
            // 任务进行中、待处理或排队中时显示取消按钮
            mainActionButton.textContent = '取消任务';
            mainActionButton.classList.add('cancel-task');
            mainActionButton.addEventListener('click', async () => {
                const userConfirmed = await showConfirmation(
                    `确定要取消验证任务 "${task.task_name}" (ID: ${task.task_id}) 吗？`
                );
                if (userConfirmed) {
                    try {
                        // 调用后端API取消任务
                        const result = await cancelValidateTask(task.task_id);
                        showNotification(2, result.message || `验证任务 ${task.task_id} 已成功请求取消。`);
                        closeValidateTaskDetailsPopup(); // 取消后关闭弹窗
                        fetchValidateTasksAndUpdateList(); // 刷新列表
                    } catch (error) {
                        console.error(`取消验证任务 ${task.task_id} 时出错:`, error);
                        showNotification(0, `取消验证任务失败: ${error.message}`);
                    }
                }
            });
        } else if (task.status === 'completed') {
            // 任务完成时显示下载结果按钮
            mainActionButton.textContent = '下载结果';
            mainActionButton.classList.add('download-model'); // 使用download-model类名，虽然下载的是zip
            mainActionButton.addEventListener('click', async () => {
                try {
                    // 调用后端API下载结果
                    const response = await downloadValidateTaskOutput(task.task_id);
                    // 从响应头获取文件名
                    const contentDisposition = response.headers.get('content-disposition');
                    let filename = `validate_output_${task.task_id}.zip`; // 默认文件名
                    if (contentDisposition) {
                        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/i);
                        if (filenameMatch && filenameMatch.length > 1) {
                            filename = filenameMatch[1];
                        }
                    }
                    // 创建Blob并下载
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url); // 释放URL对象
                    showNotification(2, `验证任务 ${task.task_id} 的结果 (${filename}) 已开始下载。`);
                } catch (error) {
                    console.error(`下载验证任务 ${task.task_id} 结果时出错:`, error);
                    showNotification(0, `下载验证结果失败: ${error.message}`);
                }
            });
        } else {
            // 其他状态下按钮不可用
            mainActionButton.textContent = '操作不可用';
            mainActionButton.disabled = true;
        }

        // 将按钮添加到弹窗底部
        taskDetailsFooter.appendChild(downloadLogButton);
        taskDetailsFooter.appendChild(mainActionButton);
    }

    /**
     * @function fetchAndRepopulateValidateTaskDetails
     * @description 获取并重新填充验证任务详情 (用于弹窗内轮询)。
     * @param {string} taskId - 任务ID。
     */
    async function fetchAndRepopulateValidateTaskDetails(taskId) {
        const taskDetailsModal = document.getElementById('task-details-modal');
        // 如果弹窗不存在、已隐藏或当前查看的不是此任务，则停止
        if (!taskDetailsModal || taskDetailsModal.classList.contains('hidden') || currentDetailTaskId_Validate !== taskId) {
            return;
        }

        console.log(`验证任务详情轮询: 正在获取任务 ${taskId} 的详情...`);
        try {
            // 调用后端API获取任务详情
            const updatedTask = await getValidateTaskDetails(taskId);

            // 如果成功获取详情，且弹窗仍然打开并显示的是当前任务
            if (updatedTask && currentDetailTaskId_Validate === taskId && !taskDetailsModal.classList.contains('hidden')) {
                const taskDetailsBody = document.getElementById('task-details-body');
                const taskDetailsFooter = document.getElementById('task-details-footer');
                if (taskDetailsBody && taskDetailsFooter) {
                    // 重新填充弹窗内容
                    populateValidateTaskDetailsModalContent(updatedTask, taskDetailsBody, taskDetailsFooter);
                    // 如果任务已完成、失败或取消，则停止轮询
                    if (['completed', 'failed', 'cancelled'].includes(updatedTask.status)) {
                        if (taskDetailPollingIntervalId_Validate) {
                            clearInterval(taskDetailPollingIntervalId_Validate);
                            taskDetailPollingIntervalId_Validate = null;
                            console.log(`验证任务详情轮询: 因任务 ${taskId} 状态为 ${updatedTask.status} 已停止。`);
                        }
                    }
                }
            } else if (!updatedTask && currentDetailTaskId_Validate === taskId) {
                // 如果API未返回数据，可能任务已被删除，关闭弹窗
                console.warn(`验证任务详情轮询: API 未返回任务 ${taskId} 的数据。正在关闭弹窗。`);
                closeValidateTaskDetailsPopup();
                showNotification(0, `无法获取验证任务 ${taskId} 的详情，可能已被删除。`);
            }
        } catch (error) {
            console.error(`验证任务详情轮询: 获取任务 ${taskId} 详情时出错:`, error);
            // 如果获取失败且弹窗显示的是当前任务，则关闭弹窗并提示
            if (currentDetailTaskId_Validate === taskId) {
                showNotification(0, `获取验证任务 ${taskId} 详情失败: ${error.message}`);
                closeValidateTaskDetailsPopup();
            }
        }
    }

    /**
     * @function showValidateTaskDetailsPopup
     * @description 显示验证任务详情弹窗，并启动该任务详情的轮询。
     * @param {object} task - 任务对象。
     */
    function showValidateTaskDetailsPopup(task) {
        const taskDetailsOverlay = document.getElementById('task-details-overlay');
        const taskDetailsModal = document.getElementById('task-details-modal');
        const taskDetailsBody = document.getElementById('task-details-body');
        const taskDetailsFooter = document.getElementById('task-details-footer');
        let modalCloseButton = document.getElementById('modal-close-button'); // 使用let以便重新绑定事件

        // 检查必要的UI元素是否存在
        if (!taskDetailsOverlay || !taskDetailsModal || !taskDetailsBody || !taskDetailsFooter || !modalCloseButton) {
            console.error('任务详情弹窗核心元素未找到!');
            return;
        }

        currentDetailTaskId_Validate = task.task_id; // 设置当前查看的任务ID
        populateValidateTaskDetailsModalContent(task, taskDetailsBody, taskDetailsFooter); // 填充内容

        // 显示弹窗
        taskDetailsOverlay.classList.remove('hidden');
        taskDetailsModal.classList.remove('hidden');

        // 重新绑定关闭按钮事件，防止重复绑定
        const newCloseButton = modalCloseButton.cloneNode(true);
        modalCloseButton.parentNode.replaceChild(newCloseButton, modalCloseButton);
        modalCloseButton = newCloseButton; // 更新引用
        modalCloseButton.addEventListener('click', closeValidateTaskDetailsPopup);

        // 点击弹窗外部区域关闭弹窗
        taskDetailsOverlay.onclick = function(event) {
            if (event.target === taskDetailsOverlay) {
                closeValidateTaskDetailsPopup();
            }
        };

        // 清除旧的详情轮询（如果存在）
        if (taskDetailPollingIntervalId_Validate) {
            clearInterval(taskDetailPollingIntervalId_Validate);
            taskDetailPollingIntervalId_Validate = null;
        }

        // 立即获取并显示一次详情
        fetchAndRepopulateValidateTaskDetails(task.task_id);

        // 如果任务状态是进行中、待处理或排队中，则启动详情轮询
        if (['pending', 'queued', 'running'].includes(task.status)) {
            taskDetailPollingIntervalId_Validate = setInterval(() => {
                fetchAndRepopulateValidateTaskDetails(task.task_id);
            }, TASK_DETAIL_POLLING_INTERVAL_MS_VALIDATE);
            console.log(`验证任务详情轮询: 已为任务 ${task.task_id} 启动。间隔: ${TASK_DETAIL_POLLING_INTERVAL_MS_VALIDATE}ms`);
        }
    }

    /**
     * @function closeValidateTaskDetailsPopup
     * @description 关闭验证任务详情弹窗，并停止其轮询。
     */
    function closeValidateTaskDetailsPopup() {
        const taskDetailsOverlay = document.getElementById('task-details-overlay');
        const taskDetailsModal = document.getElementById('task-details-modal');
        if (taskDetailsOverlay && taskDetailsModal) {
            // 隐藏弹窗
            taskDetailsOverlay.classList.add('hidden');
            taskDetailsModal.classList.add('hidden');
            // 移除点击外部关闭事件监听器
            if (taskDetailsOverlay.onclick) {
                taskDetailsOverlay.onclick = null;
            }
        }

        // 停止详情轮询
        if (taskDetailPollingIntervalId_Validate) {
            clearInterval(taskDetailPollingIntervalId_Validate);
            taskDetailPollingIntervalId_Validate = null;
            console.log(`验证任务详情轮询: 因弹窗关闭已为任务 ${currentDetailTaskId_Validate} 停止。`);
        }
        currentDetailTaskId_Validate = null; // 清空当前查看的任务ID
    }

    // --- 任务列表轮询与启停控制 ---

    /**
     * @function fetchValidateTasksAndUpdateList
     * @description 获取验证任务列表并更新UI。
     * 如果列表区域隐藏，则停止轮询。
     */
    async function fetchValidateTasksAndUpdateList() {
        const validateTasksContentDivForCheck = document.getElementById('validate-tasks-content');
        // 检查列表区域是否可见，如果隐藏则停止轮询并退出
        if (validateTasksContentDivForCheck && validateTasksContentDivForCheck.classList.contains('hidden')) {
            console.log("验证任务列表内容区域已隐藏，跳过本次列表刷新。");
            stopValidateListPolling();
            return;
        }

        console.log("正在获取验证任务列表以更新UI...");
        try {
            // 调用后端API获取任务列表
            const tasks = await getValidateTasks();
            populateValidateTaskList(tasks); // 填充列表UI
        } catch (error) {
            console.error('获取验证任务列表失败:', error);
            populateValidateTaskList(null); // 获取失败时显示错误状态
        }
    }

    /**
     * @function startValidateListPolling
     * @description 启动验证任务列表的轮询。
     * 仅在列表区域可见且轮询未启动时执行。
     */
    function startValidateListPolling() {
        if (validateListPollingIntervalId === null) {
            const validateTasksContentDivForStart = document.getElementById('validate-tasks-content');
            // 检查列表区域是否可见
            if (validateTasksContentDivForStart && !validateTasksContentDivForStart.classList.contains('hidden')) {
                console.log("启动验证任务列表轮询。");
                fetchValidateTasksAndUpdateList(); // 立即刷新一次
                // 设置定时器进行周期性刷新
                validateListPollingIntervalId = setInterval(fetchValidateTasksAndUpdateList, POLLING_INTERVAL_MS_VALIDATE_LIST);
            } else {
                console.log("尝试启动验证列表轮询，但内容区域不可见。");
            }
        }
    }

    /**
     * @function stopValidateListPolling
     * @description 停止验证任务列表的轮询。
     */
    function stopValidateListPolling() {
        if (validateListPollingIntervalId !== null) {
            console.log("停止验证任务列表轮询。");
            clearInterval(validateListPollingIntervalId);
            validateListPollingIntervalId = null;
        }
    }

    // 监听验证任务列表区域的可见性变化，以控制轮询启停
    const validateTasksContentDiv = document.getElementById('validate-tasks-content');
    if (validateTasksContentDiv) {
        // 使用 MutationObserver 监听 class 属性的变化
        const observer = new MutationObserver((mutationsList) => {
            for (const mutation of mutationsList) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    const targetElement = mutation.target;

                    // 如果区域变为可见，启动轮询
                    if (!targetElement.classList.contains('hidden')) {
                        startValidateListPolling();
                    } else {
                        // 如果区域变为隐藏，停止轮询并关闭详情弹窗
                        stopValidateListPolling();
                        closeValidateTaskDetailsPopup();
                    }
                    break; // 只关心 class 属性变化
                }
            }
        });
        observer.observe(validateTasksContentDiv, { attributes: true });

        // 初始检查：页面加载时如果区域可见，则启动轮询
        if (!validateTasksContentDiv.classList.contains('hidden')) {
            startValidateListPolling();
        }
    } else {
        console.warn("验证任务列表内容区域 ('validate-tasks-content') 未找到，列表轮询的可见性控制将无法工作。");
    }

    // 任务列表删除按钮事件委托
    const validateTaskListContainer = document.getElementById('validate-task-list-container');
    if (validateTaskListContainer) {
        // 在列表容器上监听点击事件
        validateTaskListContainer.addEventListener('click', async function(event) {
            const target = event.target;
            // 如果点击的是删除按钮
            if (target.classList.contains('delete-task-button')) {
                // 找到最近的任务列表项
                const listItem = target.closest('.task-list-item');
                if (listItem && listItem.dataset.taskId) {
                    const taskId = listItem.dataset.taskId;
                    const taskNameElement = listItem.querySelector('.validate-col-name');
                    const taskName = taskNameElement ? taskNameElement.textContent : taskId;

                    // 弹出确认框
                    const userConfirmed = await showConfirmation(
                        `确定要删除验证任务 "${taskName}" (ID: ${taskId})吗？此操作不可恢复！`
                    );

                    if (userConfirmed) {
                        console.log(`验证任务: 尝试删除任务: ${taskId}`);
                        try {
                            // 调用后端API删除任务
                            const result = await deleteValidateTask(taskId);
                            showNotification(2, result.message || `验证任务 ${taskId} 已成功删除。`);
                            fetchValidateTasksAndUpdateList(); // 刷新列表

                            // 如果当前详情弹窗显示的是被删除的任务，则关闭弹窗
                            if (currentDetailTaskId_Validate === taskId) {
                                closeValidateTaskDetailsPopup();
                            }
                        } catch (error) {
                            console.error(`删除验证任务 ${taskId} 失败:`, error);
                            showNotification(0, `删除验证任务失败: ${error.message}`);
                        }
                    }
                }
            }
        });
    } else {
        console.warn("验证任务列表容器 ('validate-task-list-container') 未找到，删除功能将无法工作。");
    }
});