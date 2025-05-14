document.addEventListener('DOMContentLoaded', () => {
    const finetuneSection = document.getElementById('finetune-content');
    if (!finetuneSection) return;

    // --- DOM 元素 ---
    // 左侧面板
    const taskNameInput = document.getElementById('finetune-task-name-input');
    const presetModelSelect = document.getElementById('finetune-preset-model-select');
    const uploadModelButton = document.getElementById('finetune-upload-model-button');
    const modelFileInput = document.getElementById('finetune-model-file-input');
    const clearModelButton = finetuneSection.querySelector('.model-selection-section .clear-model-button');
    const uploadModelButtonText = uploadModelButton.querySelector('.button-text');

    const uploadDatasetButton = document.getElementById('finetune-upload-dataset-button');
    const datasetFileInput = document.getElementById('finetune-dataset-file-input');
    const clearDatasetButton = finetuneSection.querySelector('.dataset-upload-section .clear-dataset-button');
    const uploadDatasetButtonText = uploadDatasetButton.querySelector('.button-text');
    const uploadDatasetDefaultIcon = uploadDatasetButton.querySelector('.default-icon');
    const uploadDatasetUploadedIcon = uploadDatasetButton.querySelector('.uploaded-icon');

    const uploadYamlButton = document.getElementById('finetune-upload-yaml-button');
    const yamlFileInput = document.getElementById('finetune-yaml-file-input');
    const yamlFileNameDisplay = document.getElementById('finetune-yaml-filename');
    const uploadYamlButtonText = uploadYamlButton.querySelector('.button-text');

    const startFinetuneButton = document.getElementById('finetune-start-button');

    // 右侧面板
    const importParamsButton = finetuneSection.querySelector('.action-buttons-panel .import-btn');
    const exportParamsButton = finetuneSection.querySelector('.action-buttons-panel .export-btn');
    const hiddenConfigImportInput = document.createElement('input');
    hiddenConfigImportInput.type = 'file';
    hiddenConfigImportInput.accept = '.yaml, .yml';
    hiddenConfigImportInput.style.display = 'none';
    finetuneSection.appendChild(hiddenConfigImportInput);

    // 训练参数映射 (YAML键 -> HTML元素ID)
    const trainingParamsMap = {
        epochs: 'finetune-epochs',
        batch: 'finetune-batch-size',
        imgsz: 'finetune-imgsz',
        lr0: 'finetune-lr0',
        lrf: 'finetune-lrf',
        momentum: 'finetune-momentum',
        weight_decay: 'finetune-weight-decay',
        warmup_epochs: 'finetune-warmup-epochs',
        box: 'finetune-box',
        cls: 'finetune-cls',
        dfl: 'finetune-dfl',
        patience: 'finetune-patience',
        optimizer: 'finetune-optimizer',
        seed: 'finetune-seed',
        workers: 'finetune-workers',
        amp: 'finetune-amp',
        save_period: 'finetune-save-period',
        warmup_momentum: 'finetune-warmup-momentum',
        warmup_bias_lr: 'finetune-warmup-bias-lr',
        cos_lr: 'finetune-cos-lr',
        rect: 'finetune-rect',
        cache: 'finetune-cache-images',
        deterministic: 'finetune-deterministic'
    };

    // 数据增强参数映射 (YAML键 -> HTML元素ID)
    const augmentationParamsMap = {
        degrees: 'finetune-degrees',
        translate: 'finetune-translate',
        scale: 'finetune-scale',
        shear: 'finetune-shear',
        perspective: 'finetune-perspective',
        flipud: 'finetune-flipud',
        fliplr: 'finetune-fliplr',
        mosaic: 'finetune-mosaic',
        mixup: 'finetune-mixup',
        copy_paste: 'finetune-copy-paste',
        hsv_h: 'finetune-hsv-h',
        hsv_s: 'finetune-hsv-s',
        hsv_v: 'finetune-hsv-v',
        erasing: 'finetune-erasing',
        crop_fraction: 'finetune-crop-fraction',
        multi_scale: 'finetune-multi-scale'
    };

    // --- 状态变量 ---
    let selectedModelFile = null;
    let selectedDatasetFile = null;
    let selectedYamlFile = null;

    const originalUploadModelBtnText = "上传模型";
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
                    params[key] = isNaN(val) ? element.value : val; // 保留非数字字符串
                } else if (element.tagName === 'SELECT') {
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
     * @function applyParamsToForm
     * @description 将导入的参数应用到表单元素上。
     * @param {object} importedData - 包含参数的对象。
     * @param {object} paramsMap - 参数键与HTML元素ID的映射。
     */
    function applyParamsToForm(importedData, paramsMap) {
        if (!importedData) return;
        for (const key in paramsMap) {
            const elementId = paramsMap[key];
            const element = document.getElementById(elementId);
            if (element && importedData.hasOwnProperty(key)) {
                const valueToApply = importedData[key];
                if (element.type === 'checkbox') {
                    element.checked = !!valueToApply;
                } else if (element.tagName === 'SELECT') {
                    if (typeof valueToApply === 'boolean') {
                        element.value = valueToApply ? 'true' : 'false';
                    } else {
                        element.value = valueToApply;
                    }
                } else {
                    element.value = valueToApply;
                }
            }
        }
    }

    /**
     * @function resetFileInput
     * @description 重置文件输入框及其相关的UI元素（按钮文本、图标、清除按钮状态）。
     * @param {HTMLInputElement} fileInput - 文件输入框元素。
     * @param {HTMLElement} buttonTextElement - 显示文件名的按钮内文本元素。
     * @param {string} originalText - 按钮的原始文本。
     * @param {HTMLElement} clearButton - 清除按钮元素。
     * @param {HTMLElement} [iconDefault] - (可选) 默认状态图标。
     * @param {HTMLElement} [iconUploaded] - (可选) 已上传状态图标。
     * @returns {null} 总是返回null，用于重置状态变量。
     */
    function resetFileInput(fileInput, buttonTextElement, originalText, clearButton, iconDefault, iconUploaded) {
        fileInput.value = null;
        if (buttonTextElement) buttonTextElement.textContent = originalText;
        if (clearButton) clearButton.classList.add('hidden');
        if (iconDefault) iconDefault.classList.remove('hidden');
        if (iconUploaded) iconUploaded.classList.add('hidden');
        if (buttonTextElement && buttonTextElement.parentElement.classList.contains('upload-button-styled')) {
            buttonTextElement.parentElement.classList.remove('file-selected');
        }
        return null;
    }

    // --- 事件监听器 ---

    // 模型上传
    uploadModelButton.addEventListener('click', () => modelFileInput.click());
    modelFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedModelFile = file;
            uploadModelButtonText.textContent = `已选: ${file.name.length > 20 ? file.name.substring(0, 17) + '...' : file.name}`;
            uploadModelButton.classList.add('file-selected');
            clearModelButton.classList.remove('hidden');
            presetModelSelect.value = "";
            presetModelSelect.disabled = true;
            uploadModelButton.title = file.name;
        } else {
            if (!selectedModelFile) { // 仅当之前未选择文件时才重置
                selectedModelFile = resetFileInput(modelFileInput, uploadModelButtonText, originalUploadModelBtnText, clearModelButton);
                presetModelSelect.disabled = false;
                uploadModelButton.title = '';
            }
        }
    });
    clearModelButton.addEventListener('click', () => {
        selectedModelFile = resetFileInput(modelFileInput, uploadModelButtonText, originalUploadModelBtnText, clearModelButton);
        presetModelSelect.disabled = false;
        uploadModelButton.title = '';
    });

    // 数据集上传
    uploadDatasetButton.addEventListener('click', () => datasetFileInput.click());
    datasetFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedDatasetFile = file;
            uploadDatasetButtonText.textContent = `已选: ${file.name.length > 20 ? file.name.substring(0, 17) + '...' : file.name}`;
            uploadDatasetDefaultIcon.classList.add('hidden');
            uploadDatasetUploadedIcon.classList.remove('hidden');
            clearDatasetButton.classList.remove('hidden');
            uploadDatasetButton.classList.add('file-selected');
            uploadDatasetButton.title = file.name;
        } else {
            if (!selectedDatasetFile) {
                selectedDatasetFile = resetFileInput(datasetFileInput, uploadDatasetButtonText, originalUploadDatasetBtnText, clearDatasetButton, uploadDatasetDefaultIcon, uploadDatasetUploadedIcon);
                uploadDatasetButton.title = '';
            }
        }
    });
    clearDatasetButton.addEventListener('click', () => {
        selectedDatasetFile = resetFileInput(datasetFileInput, uploadDatasetButtonText, originalUploadDatasetBtnText, clearDatasetButton, uploadDatasetDefaultIcon, uploadDatasetUploadedIcon);
        uploadDatasetButton.title = '';
    });

    // data.yaml 文件上传
    uploadYamlButton.addEventListener('click', () => yamlFileInput.click());
    yamlFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedYamlFile = file;
            yamlFileNameDisplay.textContent = `已配置: ${file.name}`;
            uploadYamlButtonText.textContent = '重选 data.yaml';
            uploadYamlButton.title = file.name;
        } else {
            selectedYamlFile = null;
            yamlFileNameDisplay.textContent = '';
            uploadYamlButtonText.textContent = originalUploadYamlBtnText;
            uploadYamlButton.title = '';
        }
    });

    // 参数管理 (YAML 导入/导出)
    importParamsButton.addEventListener('click', () => {
        hiddenConfigImportInput.click();
    });

    hiddenConfigImportInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    if (!window.jsyaml) {
                        showNotification(0, '导入参数失败：js-yaml 库未加载。');
                        console.error("js-yaml library is not loaded.");
                        return;
                    }
                    const importedData = window.jsyaml.load(e.target.result);
                    applyParamsToForm(importedData, trainingParamsMap);
                    applyParamsToForm(importedData, augmentationParamsMap);
                    showNotification(2, '参数配置已成功从 YAML 导入。');
                } catch (error) {
                    showNotification(0, '导入参数失败：无效的 YAML 文件或解析错误。');
                    console.error("Error parsing YAML config for finetune:", error);
                }
            };
            reader.onerror = () => {
                showNotification(0, '导入参数失败：无法读取文件。');
            };
            reader.readAsText(file);
        }
        hiddenConfigImportInput.value = null; // 重置文件输入，以便再次选择相同文件
    });

    exportParamsButton.addEventListener('click', () => {
        if (!window.jsyaml) {
            showNotification(0, '导出参数失败：js-yaml 库未加载。');
            console.error("js-yaml library is not loaded.");
            return;
        }

        const trainingParams = getParamsFromForm(trainingParamsMap);
        const augmentationParams = getParamsFromForm(augmentationParamsMap);
        const allParamsForYaml = { ...trainingParams, ...augmentationParams };

        try {
            const paramsYaml = window.jsyaml.dump(allParamsForYaml);
            const blob = new Blob([paramsYaml], { type: 'application/x-yaml' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${taskNameInput.value.trim() || 'finetune_params'}.yaml`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showNotification(2, '参数配置已导出为 YAML 文件。');
        } catch (error) {
            showNotification(0, '导出参数失败：YAML 生成错误。');
            console.error("Error generating YAML for finetune params:", error);
        }
    });

    // 开始微调按钮
    startFinetuneButton.addEventListener('click', async () => {
        const taskName = taskNameInput.value.trim();
        const presetModel = presetModelSelect.value;

        if (!taskName) {
            showNotification(1, '请输入任务名称。');
            taskNameInput.focus();
            return;
        }
        if (!presetModel && !selectedModelFile) {
            showNotification(1, '请选择一个预设模型或上传一个模型文件。');
            return;
        }
        if (!selectedDatasetFile) {
            showNotification(1, '请上传数据集文件 (.zip)。');
            return;
        }
        if (!selectedYamlFile) {
            showNotification(1, '请上传 data.yaml 配置文件。');
            return;
        }

        const currentTrainingParams = getParamsFromForm(trainingParamsMap);
        const currentAugmentationParams = getParamsFromForm(augmentationParamsMap);
        const combinedHyperparameters = { ...currentTrainingParams, ...currentAugmentationParams };

        const formData = new FormData();
        formData.append('task_name', taskName);

        if (selectedModelFile) {
            formData.append('base_model_pt', selectedModelFile);
        } else if (presetModel) {
            formData.append('preset_model_name', presetModel);
        }

        formData.append('dataset_zip', selectedDatasetFile);
        formData.append('dataset_yaml', selectedYamlFile);
        formData.append('training_params', JSON.stringify(combinedHyperparameters));

        console.log("--- FormData for submission (actual files not shown here) ---");
        for (var pair of formData.entries()) {
            console.log(pair[0] + ': ' + (pair[1] instanceof File ? pair[1].name : pair[1]));
        }

        startFinetuneButton.disabled = true;

        try {
            const result = await createFinetuneTask(formData); // 假设 createFinetuneTask 是已定义的API调用函数
            showNotification(2, result.message || `微调任务 "${taskName}" (ID: ${result.task_id}) 已成功创建。`);
            fetchFinetuneTasksAndUpdateList();
        } catch (error) {
            console.error("Error creating finetune task:", error);
            showNotification(0, `创建任务失败: ${error.message}`);
        } finally {
            startFinetuneButton.disabled = false;
        }
    });

    // --- 任务列表与详情轮询 ---
    let finetunePollingIntervalId = null;
    const POLLING_INTERVAL_MS = 10000; // 列表轮询间隔
    let currentDetailTaskId_Finetune = null; // 当前详情弹窗展示的任务ID
    let taskDetailPollingIntervalId_Finetune = null; // 任务详情弹窗轮询ID
    const TASK_DETAIL_POLLING_INTERVAL_MS = 5000; // 任务详情轮询间隔

    // --- UI 初始化 ---
    if (clearModelButton) clearModelButton.classList.add('hidden');
    if (uploadModelButton && presetModelSelect.value) uploadModelButton.disabled = true; // 如果有预设模型，则禁用上传按钮

    if (clearDatasetButton) clearDatasetButton.classList.add('hidden');
    if (uploadDatasetUploadedIcon) uploadDatasetUploadedIcon.classList.add('hidden');
    if (uploadDatasetDefaultIcon) uploadDatasetDefaultIcon.classList.remove('hidden');

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
        return statusMap[statusKey] || statusKey;
    }

    /**
     * @function createFinetuneTaskListItem
     * @description 创建微调任务列表项的 DOM 元素。
     * @param {object} task - 任务对象。
     * @returns {HTMLElement} 列表项 DOM 元素。
     */
    function createFinetuneTaskListItem(task) {
        const listItem = document.createElement('div');
        listItem.classList.add('task-list-item');
        listItem.dataset.taskId = task.task_id;

        const nameSpan = document.createElement('span');
        nameSpan.classList.add('finetune-col-name');
        nameSpan.textContent = task.task_name;
        nameSpan.title = task.task_name;

        const pidSpan = document.createElement('span');
        pidSpan.classList.add('finetune-col-pid');
        pidSpan.textContent = task.task_id;

        const statusSpan = document.createElement('span');
        statusSpan.classList.add('finetune-col-status', `status-${task.status}`);
        statusSpan.textContent = getDisplayStatus(task.status);

        const actionsSpan = document.createElement('span');
        actionsSpan.classList.add('finetune-col-actions');

        const detailsButton = document.createElement('button');
        detailsButton.classList.add('task-action-button', 'details-task-button');
        detailsButton.textContent = '详情';
        detailsButton.addEventListener('click', () => showFinetuneTaskDetailsPopup(task));

        const deleteButton = document.createElement('button');
        deleteButton.classList.add('task-action-button', 'delete-task-button');
        deleteButton.textContent = '删除';

        actionsSpan.appendChild(detailsButton);
        actionsSpan.appendChild(deleteButton);

        listItem.appendChild(nameSpan);
        listItem.appendChild(pidSpan);
        listItem.appendChild(statusSpan);
        listItem.appendChild(actionsSpan);

        return listItem;
    }

    /**
     * @function populateFinetuneTaskList
     * @description 填充微调任务列表。
     * @param {Array|null} tasks - 任务对象数组，或在出错时为 null。
     */
    function populateFinetuneTaskList(tasks) {
        const listContainer = document.getElementById('finetune-task-list-container');
        const noTasksMessage = document.getElementById('no-finetune-tasks-message');
        const finetuneTasksContentElement = document.getElementById('finetune-tasks-content');
        let header = null;

        if (finetuneTasksContentElement) {
            header = finetuneTasksContentElement.querySelector('.task-list-header.finetune-header');
        }

        if (!listContainer || !noTasksMessage || !header) {
            return;
        }

        listContainer.innerHTML = '';

        if (tasks && tasks.length === 0) {
            noTasksMessage.classList.remove('hidden');
            noTasksMessage.textContent = "当前没有微调任务。";
            listContainer.classList.add('hidden');
            header.classList.add('hidden');
        } else if (tasks) {
            noTasksMessage.classList.add('hidden');
            listContainer.classList.remove('hidden');
            header.classList.remove('hidden');
            tasks.forEach(task => {
                const listItem = createFinetuneTaskListItem(task);
                listContainer.appendChild(listItem);
            });
        } else {
            noTasksMessage.classList.remove('hidden');
            noTasksMessage.textContent = "无法加载任务列表。";
            listContainer.classList.add('hidden');
            header.classList.add('hidden');
        }
    }

    /**
     * @function populateFinetuneTaskDetailsModalContent
     * @description 填充微调任务详情弹窗的内容。
     * @param {object} task - 任务对象。
     * @param {HTMLElement} taskDetailsBody - 弹窗内容主体区域。
     * @param {HTMLElement} taskDetailsFooter - 弹窗底部操作区域。
     */
    function populateFinetuneTaskDetailsModalContent(task, taskDetailsBody, taskDetailsFooter) {
        taskDetailsBody.innerHTML = '';
        taskDetailsFooter.innerHTML = '';

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

        taskDetailsBody.appendChild(createDetailItem('任务名称:', task.task_name)); 
        taskDetailsBody.appendChild(createDetailItem('任务ID:', task.task_id)); 
        const statusDisplay = getDisplayStatus(task.status);
        const statusItem = createDetailItem('任务状态:', statusDisplay);
        const statusValueSpan = statusItem.querySelector('.detail-value');
        if (statusValueSpan) statusValueSpan.classList.add(`status-${task.status}`);
        taskDetailsBody.appendChild(statusItem);

        switch (task.status) {
            case 'running':
                if (task.progress) {
                    taskDetailsBody.appendChild(createProgressDetailItem('训练轮次:', task.progress.current_epoch, task.progress.total_epochs, `${task.progress.current_epoch}/${task.progress.total_epochs}`));
                    taskDetailsBody.appendChild(createDetailItem('训练速度:', task.progress.speed || 'N/A'));
                } else {
                    taskDetailsBody.appendChild(createDetailItem('进度:', '正在获取进度...'));
                }
                break;
            case 'queued':
                if (task.queue_position) {
                    taskDetailsBody.appendChild(createDetailItem('当前排队:', `${task.queue_position.position} / ${task.queue_position.total}`));
                } else {
                }
                break;
            case 'failed':
                taskDetailsBody.appendChild(createDetailItem('错误代码:', task.error_code || '未知错误'));
                if (task.error_message) {
                    taskDetailsBody.appendChild(createDetailItem('详细信息:', task.error_message, true));
                }
                break;
            case 'completed':
                taskDetailsBody.appendChild(createDetailItem('最佳轮次:', task.best_epoch ? `Epoch ${task.best_epoch}` : 'N/A'));
                break;
            case 'cancelled':
                taskDetailsBody.appendChild(createDetailItem('信息:', '任务已被用户取消。'));
                break;
        }

        const downloadLogButton = document.createElement('button');
        downloadLogButton.classList.add('task-action-button', 'download-log-button');
        downloadLogButton.textContent = '下载日志';
        downloadLogButton.addEventListener('click', async () => {
            try {
                const logData = await getFinetuneTaskLogs(task.task_id);
                if (logData && logData.logs) {
                    const blob = new Blob([logData.logs], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${task.task_name || 'task'}_${task.task_id}_logs.txt`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                } else {
                    showNotification(0, `任务 ${task.task_id} 的日志为空或不可用。`);
                }
            } catch (error) {
                console.error(`Error downloading logs for task ${task.task_id}:`, error);
                showNotification(0, `下载日志失败: ${error.message}`);
            }
        });

        const mainActionButton = document.createElement('button');
        mainActionButton.classList.add('task-action-button', 'main-action-button');

        if (task.status === 'running' || task.status === 'pending' || task.status === 'queued') {
            mainActionButton.textContent = '取消任务';
            mainActionButton.classList.add('cancel-task');
            mainActionButton.addEventListener('click', async () => {
                const userConfirmed = await showConfirmation(
                    `确定要取消任务 "${task.task_name}" (ID: ${task.task_id}) 吗？`
                );
                if (userConfirmed) {
                    try {
                        const result = await cancelFinetuneTask(task.task_id);
                        showNotification(2, result.message || `任务 ${task.task_id} 已成功请求取消。`);
                        closeFinetuneTaskDetailsPopup();
                        fetchFinetuneTasksAndUpdateList();
                    } catch (error) {
                        console.error(`Error cancelling task ${task.task_id}:`, error);
                        showNotification(0, `取消任务失败: ${error.message}`);
                    }
                }
            });
        } else if (task.status === 'completed') {
            mainActionButton.textContent = '下载模型';
            mainActionButton.classList.add('download-model');
            mainActionButton.addEventListener('click', async () => {
                try {
                    const response = await downloadFinetuneTaskOutput(task.task_id);
                    const contentDisposition = response.headers.get('content-disposition');
                    let filename = `finetune_output_${task.task_id}.zip`;
                    if (contentDisposition) {
                        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/i);
                        if (filenameMatch && filenameMatch.length > 1) {
                            filename = filenameMatch[1];
                        }
                    }
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                    showNotification(2, `任务 ${task.task_id} 的模型 (${filename}) 已开始下载。`);
                } catch (error) {
                    console.error(`Error downloading model for task ${task.task_id}:`, error);
                    showNotification(0, `下载模型失败: ${error.message}`);
                }
            });
        } else {
            mainActionButton.textContent = '操作不可用';
            mainActionButton.disabled = true;
        }
        taskDetailsFooter.appendChild(downloadLogButton);
        taskDetailsFooter.appendChild(mainActionButton);
    }

    /**
     * @function fetchAndRepopulateFinetuneTaskDetails
     * @description 获取并重新填充微调任务详情 (用于弹窗内轮询)。
     * @param {string} taskId - 任务ID。
     */
    async function fetchAndRepopulateFinetuneTaskDetails(taskId) {
        const taskDetailsModal = document.getElementById('task-details-modal');
        if (!taskDetailsModal || taskDetailsModal.classList.contains('hidden') || currentDetailTaskId_Finetune !== taskId) {
            return; // 弹窗未打开或已切换到其他任务
        }
        try {
            const updatedTask = await getFinetuneTaskDetails(taskId);

            if (updatedTask && currentDetailTaskId_Finetune === taskId && !taskDetailsModal.classList.contains('hidden')) {
                const taskDetailsBody = document.getElementById('task-details-body');
                const taskDetailsFooter = document.getElementById('task-details-footer');
                if (taskDetailsBody && taskDetailsFooter) {
                    populateFinetuneTaskDetailsModalContent(updatedTask, taskDetailsBody, taskDetailsFooter);
                }
            } else if (!updatedTask) {
                closeFinetuneTaskDetailsPopup();
                showNotification(0, `无法获取任务 ${taskId} 的详情，可能已被删除。`);
            }
        } catch (error) {
            showNotification(0, `获取任务 ${taskId} 详情失败: ${error.message}`);
            closeFinetuneTaskDetailsPopup();
        }
    }

    /**
     * @function showFinetuneTaskDetailsPopup
     * @description 显示微调任务详情弹窗，并启动该任务详情的轮询。
     * @param {object} task - 任务对象。
     */
    function showFinetuneTaskDetailsPopup(task) {
        const taskDetailsOverlay = document.getElementById('task-details-overlay');
        const taskDetailsModal = document.getElementById('task-details-modal');
        const taskDetailsBody = document.getElementById('task-details-body');
        const taskDetailsFooter = document.getElementById('task-details-footer');
        const modalCloseButton = document.getElementById('modal-close-button');

        if (!taskDetailsOverlay || !taskDetailsModal || !taskDetailsBody || !taskDetailsFooter || !modalCloseButton) {
            console.error('任务详情弹窗元素未找到!');
            return;
        }

        currentDetailTaskId_Finetune = task.task_id;
        populateFinetuneTaskDetailsModalContent(task, taskDetailsBody, taskDetailsFooter); // 初始填充

        taskDetailsOverlay.classList.remove('hidden');
        taskDetailsModal.classList.remove('hidden');

        // 重新绑定关闭按钮事件，避免重复监听
        const newCloseButton = modalCloseButton.cloneNode(true);
        modalCloseButton.parentNode.replaceChild(newCloseButton, modalCloseButton);
        newCloseButton.addEventListener('click', closeFinetuneTaskDetailsPopup);

        taskDetailsOverlay.onclick = function(event) {
            if (event.target === taskDetailsOverlay) { // 点击遮罩层关闭
                closeFinetuneTaskDetailsPopup();
            }
        };

        if (taskDetailPollingIntervalId_Finetune) {
            clearInterval(taskDetailPollingIntervalId_Finetune); // 清除上一个任务的详情轮询
        }

        fetchAndRepopulateFinetuneTaskDetails(task.task_id); // 立即获取一次
        if (['pending', 'queued', 'running'].includes(task.status))  {
            taskDetailPollingIntervalId_Finetune = setInterval(() => {
            fetchAndRepopulateFinetuneTaskDetails(task.task_id);
            }, TASK_DETAIL_POLLING_INTERVAL_MS);
        }
    }

    /**
     * @function closeFinetuneTaskDetailsPopup
     * @description 关闭微调任务详情弹窗，并停止其轮询。
     */
    function closeFinetuneTaskDetailsPopup() {
        const taskDetailsOverlay = document.getElementById('task-details-overlay');
        const taskDetailsModal = document.getElementById('task-details-modal');
        if (taskDetailsOverlay && taskDetailsModal) {
            taskDetailsOverlay.classList.add('hidden');
            taskDetailsModal.classList.add('hidden');
            if (taskDetailsOverlay.onclick) {
                taskDetailsOverlay.onclick = null; // 移除遮罩层点击事件
            }
        }

        if (taskDetailPollingIntervalId_Finetune) {
            clearInterval(taskDetailPollingIntervalId_Finetune);
            taskDetailPollingIntervalId_Finetune = null;
        }
        currentDetailTaskId_Finetune = null;
    }

    /**
     * @function fetchFinetuneTasksAndUpdateList
     * @description 获取微调任务列表并更新UI。
     */
    async function fetchFinetuneTasksAndUpdateList() {
        console.log("正在获取微调任务列表以更新UI...");
        try {
            const tasks = await getFinetuneTasks(); // 假设API函数
            populateFinetuneTaskList(tasks);
        } catch (error) {
            populateFinetuneTaskList(null); // 传递 null 以显示错误或无任务消息
        }
    }

    /**
     * @function startFinetunePolling
     * @description 启动微调任务列表的轮询。
     */
    function startFinetunePolling() {
        if (finetunePollingIntervalId === null) {
            console.log("启动微调任务列表轮询。");
            fetchFinetuneTasksAndUpdateList(); // 立即获取一次
            finetunePollingIntervalId = setInterval(fetchFinetuneTasksAndUpdateList, POLLING_INTERVAL_MS);
        }
    }

    /**
     * @function stopFinetunePolling
     * @description 停止微调任务列表的轮询。
     */
    function stopFinetunePolling() {
        if (finetunePollingIntervalId !== null) {
            clearInterval(finetunePollingIntervalId);
            finetunePollingIntervalId = null;
        }
    }

    // 监听微调任务列表区域的可见性变化，以控制轮询启停
    const finetuneTasksContentDiv = document.getElementById('finetune-tasks-content');
    if (finetuneTasksContentDiv) {
        const observer = new MutationObserver((mutationsList) => {
            for (const mutation of mutationsList) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    const targetElement = mutation.target;
                    if (!targetElement.classList.contains('hidden')) {
                        startFinetunePolling();
                    } else {
                        stopFinetunePolling();
                        closeFinetuneTaskDetailsPopup(); // 列表隐藏时也关闭详情弹窗
                    }
                    break;
                }
            }
        });
        observer.observe(finetuneTasksContentDiv, { attributes: true });

        // 初始检查
        if (!finetuneTasksContentDiv.classList.contains('hidden')) {
            startFinetunePolling();
        }
    } else {
        console.warn("微调任务内容区域 ('finetune-tasks-content') 未找到，轮询将无法工作。");
    }

    // 任务列表删除按钮事件委托
    const finetuneTaskListContainer = document.getElementById('finetune-task-list-container');
    if (finetuneTaskListContainer) {
        finetuneTaskListContainer.addEventListener('click', async function(event) {
            const target = event.target;
            if (target.classList.contains('delete-task-button')) {
                const listItem = target.closest('.task-list-item');
                if (listItem && listItem.dataset.taskId) {
                    const taskId = listItem.dataset.taskId;
                    const taskName = listItem.querySelector('.finetune-col-name')?.textContent || taskId;
                    const userConfirmed = await showConfirmation(
                    `确定要删除微调任务 "${taskName}" (ID: ${taskId})吗？此操作不可恢复！`
                );
                    if (userConfirmed) {
                        try {
                            const result = await deleteFinetuneTask(taskId); // 假设API函数
                            showNotification(2, result.message || `任务 ${taskId} 已成功删除。`);
                            fetchFinetuneTasksAndUpdateList(); // 刷新列表
                            if (currentDetailTaskId_Finetune === taskId) { // 如果删除的是当前详情弹窗的任务
                                closeFinetuneTaskDetailsPopup();
                            }
                        } catch (error) {
                            console.error(`删除微调任务 ${taskId} 失败:`, error);
                            showNotification(0, `删除任务失败: ${error.message}`);
                        }
                    }
                }
            }
        });
    }
});