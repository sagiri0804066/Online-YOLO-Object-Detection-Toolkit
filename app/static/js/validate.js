document.addEventListener('DOMContentLoaded', () => {
    const validateSection = document.getElementById('validate-content');
    if (!validateSection) return;

    // --- DOM 元素 ---
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

    const validationParamsMap = {
        batch: 'validate-batch-size', imgsz: 'validate-imgsz',
        conf: 'validate-conf-thres', iou: 'validate-iou-thres',
        split: 'validate-split', max_det: 'validate-max-det',
        half: 'validate-half', save_json: 'validate-save-json',
        plots: 'validate-plots', save_txt: 'validate-save-txt',
        augment: 'validate-augment', rect: 'validate-rect'
    };

    // --- 状态变量 ---
    let selectedModelFile = null;
    let selectedDatasetZipFile = null;
    let selectedYamlFile = null;

    const originalUploadModelBtnText = "上传待验证模型";
    const originalUploadDatasetBtnText = "上传数据集";
    const originalUploadYamlBtnText = "配置 data.yaml";

    // --- 辅助函数 ---
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
        fileInput.value = null;
        if (buttonTextElement) buttonTextElement.textContent = originalText;
        if (clearButton) clearButton.classList.add('hidden');
        if (iconDefault) iconDefault.classList.remove('hidden');
        if (iconUploaded) iconUploaded.classList.add('hidden');
        if (buttonTextElement && buttonTextElement.parentElement.classList.contains('upload-button-styled')) {
            buttonTextElement.parentElement.classList.remove('file-selected');
        }
        stateVariableSetter(null);
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
        return statusMap[statusKey] || statusKey;
    }

    // --- 事件监听器 ---
    uploadModelButton.addEventListener('click', () => modelFileInput.click());
    modelFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedModelFile = file;
            uploadModelButtonText.textContent = `已选: ${file.name.length > 20 ? file.name.substring(0,17)+'...' : file.name}`;
            uploadModelButton.classList.add('file-selected');
            clearModelButton.classList.remove('hidden');
            uploadModelButton.title = file.name;
        } else {
            if (!selectedModelFile) {
                resetFileInput(modelFileInput, uploadModelButtonText, originalUploadModelBtnText, clearModelButton, null, null, (val) => selectedModelFile = val);
                uploadModelButton.title = '';
            }
        }
    });
    clearModelButton.addEventListener('click', () => {
        resetFileInput(modelFileInput, uploadModelButtonText, originalUploadModelBtnText, clearModelButton, null, null, (val) => selectedModelFile = val);
        uploadModelButton.title = '';
    });

    uploadDatasetButton.addEventListener('click', () => datasetFileInput.click());
    datasetFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedDatasetZipFile = file;
            uploadDatasetButtonText.textContent = `已选: ${file.name.length > 20 ? file.name.substring(0,17)+'...' : file.name}`;
            uploadDatasetDefaultIcon.classList.add('hidden');
            uploadDatasetUploadedIcon.classList.remove('hidden');
            clearDatasetButton.classList.remove('hidden');
            uploadDatasetButton.classList.add('file-selected');
            uploadDatasetButton.title = file.name;
        } else {
            if (!selectedDatasetZipFile) {
                resetFileInput(datasetFileInput, uploadDatasetButtonText, originalUploadDatasetBtnText, clearDatasetButton, uploadDatasetDefaultIcon, uploadDatasetUploadedIcon, (val) => selectedDatasetZipFile = val);
                uploadDatasetButton.title = '';
            }
        }
    });
    clearDatasetButton.addEventListener('click', () => {
        resetFileInput(datasetFileInput, uploadDatasetButtonText, originalUploadDatasetBtnText, clearDatasetButton, uploadDatasetDefaultIcon, uploadDatasetUploadedIcon, (val) => selectedDatasetZipFile = val);
        uploadDatasetButton.title = '';
    });

    uploadYamlButton.addEventListener('click', () => yamlFileInput.click());
    yamlFileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            selectedYamlFile = file;
            yamlFileNameDisplay.textContent = `已配置: ${file.name}`;
            uploadYamlButtonText.textContent = '重选 data.yaml';
            uploadYamlButton.title = file.name;
        } else {
            if (!selectedYamlFile) {
                selectedYamlFile = null;
                yamlFileNameDisplay.textContent = '';
                uploadYamlButtonText.textContent = originalUploadYamlBtnText;
                uploadYamlButton.title = '';
            }
        }
    });

    startValidateButton.addEventListener('click', async () => {
        const taskName = taskNameInput.value.trim();

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

        const formData = new FormData();
        formData.append('task_name', taskName);
        formData.append('model_source_type', 'upload');
        formData.append('model_file_upload', selectedModelFile);
        formData.append('dataset_source_type', 'upload');
        formData.append('dataset_zip_upload', selectedDatasetZipFile);
        formData.append('dataset_yaml_upload', selectedYamlFile);
        formData.append('validation_params', JSON.stringify(validationParameters));

        console.log("--- 验证任务提交数据 (文件本身未显示) ---");
        for (var pair of formData.entries()) {
           console.log(pair[0]+ ': ' + (pair[1] instanceof File ? pair[1].name : pair[1]));
        }

        startValidateButton.disabled = true;
        try {
            const result = await createValidateTask(formData);
            showNotification(2, result.message || `验证任务 "${taskName}" (ID: ${result.task_id || result.id}) 已成功创建。`);
            fetchValidateTasksAndUpdateList();
        } catch (error) {
            console.error("创建验证任务时出错:", error);
            showNotification(0, `创建验证任务失败: ${error.message}`);
        } finally {
            startValidateButton.disabled = false;
        }
    });

    // --- UI 初始化 ---
    if (clearModelButton) clearModelButton.classList.add('hidden');
    if (clearDatasetButton) clearDatasetButton.classList.add('hidden');
    if (uploadDatasetUploadedIcon) uploadDatasetUploadedIcon.classList.add('hidden');
    if (uploadDatasetDefaultIcon) uploadDatasetDefaultIcon.classList.remove('hidden');

    // --- 任务列表与详情轮询状态变量 ---
    let validateListPollingIntervalId = null;
    const POLLING_INTERVAL_MS_VALIDATE_LIST = 10000;
    let currentDetailTaskId_Validate = null;
    let taskDetailPollingIntervalId_Validate = null;
    const TASK_DETAIL_POLLING_INTERVAL_MS_VALIDATE = 5000;

    /**
     * @function createValidateTaskListItem
     * @description 创建验证任务列表项的 DOM 元素。
     * @param {object} task - 任务对象。
     * @returns {HTMLElement} 列表项 DOM 元素。
     */
    function createValidateTaskListItem(task) {
        const listItem = document.createElement('div');
        listItem.classList.add('task-list-item');
        listItem.dataset.taskId = task.task_id;

        const nameSpan = document.createElement('span');
        nameSpan.classList.add('validate-col-name');
        nameSpan.textContent = task.task_name;
        nameSpan.title = task.name;

        const pidSpan = document.createElement('span');
        pidSpan.classList.add('validate-col-pid');
        pidSpan.textContent = task.task_id;

        const statusSpan = document.createElement('span');
        statusSpan.classList.add('validate-col-status', `status-${task.status}`);
        statusSpan.textContent = getDisplayStatus(task.status);

        const actionsSpan = document.createElement('span');
        actionsSpan.classList.add('validate-col-actions');

        const detailsButton = document.createElement('button');
        detailsButton.classList.add('task-action-button', 'details-task-button');
        detailsButton.textContent = '详情';
        detailsButton.addEventListener('click', (event) => {
            event.stopPropagation();
            showValidateTaskDetailsPopup(task);
        });

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
     * @function populateValidateTaskList
     * @description 填充验证任务列表。
     * @param {Array|null} tasks - 任务对象数组，或在出错时为 null。
     */
    function populateValidateTaskList(tasks) {
        const listContainer = document.getElementById('validate-task-list-container');
        const noTasksMessage = document.getElementById('no-validate-tasks-message');
        const validateTasksContentElement = document.getElementById('validate-tasks-content');
        let header = null;

        if (validateTasksContentElement) {
            header = validateTasksContentElement.querySelector('.task-list-header.validate-header');
        }

        if (!listContainer || !noTasksMessage || !header) {
            console.error('验证任务列表UI元素未找到。');
            return;
        }

        listContainer.innerHTML = '';

        if (tasks && tasks.length === 0) {
            noTasksMessage.classList.remove('hidden');
            noTasksMessage.textContent = "当前没有验证任务。";
            listContainer.classList.add('hidden');
            header.classList.add('hidden');
        } else if (tasks && tasks.length > 0) {
            noTasksMessage.classList.add('hidden');
            listContainer.classList.remove('hidden');
            header.classList.remove('hidden');
            tasks.forEach(task => {
                const listItem = createValidateTaskListItem(task);
                listContainer.appendChild(listItem);
            });
        } else if (tasks === null) {
            noTasksMessage.classList.remove('hidden');
            noTasksMessage.textContent = "无法加载验证任务列表。";
            listContainer.classList.add('hidden');
            header.classList.add('hidden');
        } else {
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
                    let currentProg = 0;
                    let totalProg = 0;
                    let progressText = '进行中...';

                    if (typeof task.progress.percentage === 'number') {
                        currentProg = task.progress.percentage;
                        totalProg = 100;
                        progressText = `${task.progress.percentage.toFixed(1)}%`;
                    } else if (typeof task.progress.current_step === 'number' && typeof task.progress.total_steps === 'number' && task.progress.total_steps > 0) {
                        currentProg = task.progress.current_step;
                        totalProg = task.progress.total_steps;
                        progressText = `${task.progress.current_step}/${task.progress.total_steps}`;
                    } else if (task.progress.message) {
                        progressText = task.progress.message;
                    }
                    
                    if (totalProg > 0) {
                         taskDetailsBody.appendChild(createProgressDetailItem('验证进度:', currentProg, totalProg, progressText));
                    } else {
                         taskDetailsBody.appendChild(createDetailItem('验证进度:', progressText));
                    }
                    if (task.progress.speed) {
                        taskDetailsBody.appendChild(createDetailItem('验证速度:', task.progress.speed));
                    }
                } else {
                    taskDetailsBody.appendChild(createDetailItem('进度:', '正在获取进度...'));
                }
                break;
            case 'queued':
                if (task.queue_position && typeof task.queue_position.position === 'number' && typeof task.queue_position.total === 'number') {
                    taskDetailsBody.appendChild(createDetailItem('当前排队:', `${task.queue_position.position} / ${task.queue_position.total}`));
                } else {
                    taskDetailsBody.appendChild(createDetailItem('排队位置:', '正在获取...'));
                }
                break;
            case 'failed':
                taskDetailsBody.appendChild(createDetailItem('错误代码:', task.error_code || '未知错误'));
                if (task.error_message) {
                    taskDetailsBody.appendChild(createDetailItem('详细信息:', task.error_message, true));
                }
                break;
            case 'completed':
                taskDetailsBody.appendChild(createDetailItem('信息:', '验证已成功完成。'));
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
                const logData = await getValidateTaskLogs(task.task_id);
                if (logData && typeof logData.logs === 'string') {
                    if (logData.logs.trim() === "") {
                         showNotification(1, `任务 ${task.task_id} 的日志为空。`);
                         return;
                    }
                    const blob = new Blob([logData.logs], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${task.task_name || 'validate_task'}_${task.task_id}_logs.txt`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                } else {
                    showNotification(0, `任务 ${task.task_id} 的日志为空或不可用。`);
                }
            } catch (error) {
                console.error(`下载/获取验证任务 ${task.task_id} 日志时出错:`, error);
                showNotification(0, `获取/下载日志失败: ${error.message}`);
            }
        });

        const mainActionButton = document.createElement('button');
        mainActionButton.classList.add('task-action-button', 'main-action-button');

        if (task.status === 'running' || task.status === 'pending' || task.status === 'queued') {
            mainActionButton.textContent = '取消任务';
            mainActionButton.classList.add('cancel-task');
            mainActionButton.addEventListener('click', async () => {
                const userConfirmed = await showConfirmation(
                    `确定要取消验证任务 "${task.task_name}" (ID: ${task.task_id}) 吗？`
                );
                if (userConfirmed) {
                    try {
                        const result = await cancelValidateTask(task.task_id);
                        showNotification(2, result.message || `验证任务 ${task.task_id} 已成功请求取消。`);
                        closeValidateTaskDetailsPopup();
                        fetchValidateTasksAndUpdateList();
                    } catch (error) {
                        console.error(`取消验证任务 ${task.task_id} 时出错:`, error);
                        showNotification(0, `取消验证任务失败: ${error.message}`);
                    }
                }
            });
        } else if (task.status === 'completed') {
            mainActionButton.textContent = '下载结果';
            mainActionButton.classList.add('download-model');
            mainActionButton.addEventListener('click', async () => {
                try {
                    const response = await downloadValidateTaskOutput(task.task_id);
                    const contentDisposition = response.headers.get('content-disposition');
                    let filename = `validate_output_${task.task_id}.zip`;
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
                    showNotification(2, `验证任务 ${task.task_id} 的结果 (${filename}) 已开始下载。`);
                } catch (error) {
                    console.error(`下载验证任务 ${task.task_id} 结果时出错:`, error);
                    showNotification(0, `下载验证结果失败: ${error.message}`);
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
     * @function fetchAndRepopulateValidateTaskDetails
     * @description 获取并重新填充验证任务详情 (用于弹窗内轮询)。
     * @param {string} taskId - 任务ID。
     */
    async function fetchAndRepopulateValidateTaskDetails(taskId) {
        const taskDetailsModal = document.getElementById('task-details-modal');
        if (!taskDetailsModal || taskDetailsModal.classList.contains('hidden') || currentDetailTaskId_Validate !== taskId) {
            return;
        }

        console.log(`验证任务详情轮询: 正在获取任务 ${taskId} 的详情...`);
        try {
            const updatedTask = await getValidateTaskDetails(taskId);

            if (updatedTask && currentDetailTaskId_Validate === taskId && !taskDetailsModal.classList.contains('hidden')) {
                const taskDetailsBody = document.getElementById('task-details-body');
                const taskDetailsFooter = document.getElementById('task-details-footer');
                if (taskDetailsBody && taskDetailsFooter) {
                    populateValidateTaskDetailsModalContent(updatedTask, taskDetailsBody, taskDetailsFooter);
                    if (['completed', 'failed', 'cancelled'].includes(updatedTask.status)) {
                        if (taskDetailPollingIntervalId_Validate) {
                            clearInterval(taskDetailPollingIntervalId_Validate);
                            taskDetailPollingIntervalId_Validate = null;
                            console.log(`验证任务详情轮询: 因任务 ${taskId} 状态为 ${updatedTask.status} 已停止。`);
                        }
                    }
                }
            } else if (!updatedTask && currentDetailTaskId_Validate === taskId) {
                console.warn(`验证任务详情轮询: API 未返回任务 ${taskId} 的数据。正在关闭弹窗。`);
                closeValidateTaskDetailsPopup();
                showNotification(0, `无法获取验证任务 ${taskId} 的详情，可能已被删除。`);
            }
        } catch (error) {
            console.error(`验证任务详情轮询: 获取任务 ${taskId} 详情时出错:`, error);
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
        const modalCloseButton = document.getElementById('modal-close-button');

        if (!taskDetailsOverlay || !taskDetailsModal || !taskDetailsBody || !taskDetailsFooter || !modalCloseButton) {
            console.error('任务详情弹窗核心元素未找到!');
            return;
        }

        currentDetailTaskId_Validate = task.task_id;
        populateValidateTaskDetailsModalContent(task, taskDetailsBody, taskDetailsFooter);

        taskDetailsOverlay.classList.remove('hidden');
        taskDetailsModal.classList.remove('hidden');

        const newCloseButton = modalCloseButton.cloneNode(true);
        modalCloseButton.parentNode.replaceChild(newCloseButton, modalCloseButton);
        newCloseButton.addEventListener('click', closeValidateTaskDetailsPopup);

        taskDetailsOverlay.onclick = function(event) {
            if (event.target === taskDetailsOverlay) {
                closeValidateTaskDetailsPopup();
            }
        };

        if (taskDetailPollingIntervalId_Validate) {
            clearInterval(taskDetailPollingIntervalId_Validate);
            taskDetailPollingIntervalId_Validate = null;
        }

        fetchAndRepopulateValidateTaskDetails(task.task_id);

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
            taskDetailsOverlay.classList.add('hidden');
            taskDetailsModal.classList.add('hidden');
            if (taskDetailsOverlay.onclick) {
                taskDetailsOverlay.onclick = null;
            }
        }

        if (taskDetailPollingIntervalId_Validate) {
            clearInterval(taskDetailPollingIntervalId_Validate);
            taskDetailPollingIntervalId_Validate = null;
            console.log(`验证任务详情轮询: 因弹窗关闭已为任务 ${currentDetailTaskId_Validate} 停止。`);
        }
        currentDetailTaskId_Validate = null;
    }

    // --- 任务列表轮询与启停控制 ---
    /**
     * @function fetchValidateTasksAndUpdateList
     * @description 获取验证任务列表并更新UI。
     */
    async function fetchValidateTasksAndUpdateList() {
        const validateTasksContentDivForCheck = document.getElementById('validate-tasks-content');
        if (validateTasksContentDivForCheck && validateTasksContentDivForCheck.classList.contains('hidden')) {
            console.log("验证任务列表内容区域已隐藏，跳过本次列表刷新。");
            stopValidateListPolling();
            return;
        }

        console.log("正在获取验证任务列表以更新UI...");
        try {
            const tasks = await getValidateTasks();
            populateValidateTaskList(tasks);
        } catch (error) {
            console.error('获取验证任务列表失败:', error);
            populateValidateTaskList(null);
        }
    }

    /**
     * @function startValidateListPolling
     * @description 启动验证任务列表的轮询。
     */
    function startValidateListPolling() {
        if (validateListPollingIntervalId === null) {
            const validateTasksContentDivForStart = document.getElementById('validate-tasks-content');
            if (validateTasksContentDivForStart && !validateTasksContentDivForStart.classList.contains('hidden')) {
                console.log("启动验证任务列表轮询。");
                fetchValidateTasksAndUpdateList();
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
        const observer = new MutationObserver((mutationsList) => {
            for (const mutation of mutationsList) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    const targetElement = mutation.target;

                    if (!targetElement.classList.contains('hidden')) {
                        startValidateListPolling();
                    } else {
                        stopValidateListPolling();
                        closeValidateTaskDetailsPopup();
                    }
                    break;
                }
            }
        });
        observer.observe(validateTasksContentDiv, { attributes: true });

        // 初始检查
        if (!validateTasksContentDiv.classList.contains('hidden')) {
            startValidateListPolling();
        }
    } else {
        console.warn("验证任务列表内容区域 ('validate-tasks-content') 未找到，列表轮询的可见性控制将无法工作。");
    }

    // 任务列表删除按钮事件委托
    const validateTaskListContainer = document.getElementById('validate-task-list-container');
    if (validateTaskListContainer) {
        validateTaskListContainer.addEventListener('click', async function(event) {
            const target = event.target;
            if (target.classList.contains('delete-task-button')) {
                const listItem = target.closest('.task-list-item');
                if (listItem && listItem.dataset.taskId) {
                    const taskId = listItem.dataset.taskId;
                    const taskNameElement = listItem.querySelector('.validate-col-name');
                    const taskName = taskNameElement ? taskNameElement.textContent : taskId;

                    const userConfirmed = await showConfirmation(
                        `确定要删除验证任务 "${taskName}" (ID: ${taskId})吗？此操作不可恢复！`
                    );

                    if (userConfirmed) {
                        console.log(`验证任务: 尝试删除任务: ${taskId}`);
                        try {
                            const result = await deleteValidateTask(taskId);
                            showNotification(2, result.message || `验证任务 ${taskId} 已成功删除。`);
                            fetchValidateTasksAndUpdateList();

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