// --- js/model-management.js ---
console.log("model-management.js 文件已加载");

document.addEventListener('DOMContentLoaded', () => {
    const modelListContainer = document.getElementById('model-list-container');
    const uploadButton = document.getElementById('upload-model-trigger');
    const fileInput = document.getElementById('model-file-input');
    const noModelsMessage = document.getElementById('no-models-message');

    // --- 渲染模型列表 ---
    function renderModelList(models) {
        console.log("RenderModelList received models:", models);

        if (!modelListContainer || !noModelsMessage) {
            console.error("Model list container or no-models message element not found!");
            return;
        }

        modelListContainer.innerHTML = '';

        if (!models || models.length === 0) {
            console.log("No models to render, showing 'no models' message.");
            noModelsMessage.classList.remove('hidden');
            modelListContainer.innerHTML = '';
            return;
        }

        noModelsMessage.classList.add('hidden');

        models.forEach(modelObject => {
            if (modelObject && modelObject.modelname) {
                const item = document.createElement('div');
                item.classList.add('model-list-item');
                item.dataset.modelName = modelObject.modelname;

                item.innerHTML = `
                    <span class="model-name" title="${modelObject.modelname}">${modelObject.modelname}</span>
                    <span class="model-date">${modelObject.datemodified || '-'}</span>
                    <span class="model-size">${modelObject.bytesize || '-'}</span>
                    <div class="model-item-actions">
                        <button class="model-action-button delete-model-button">删除</button>
                        <button class="model-action-button download-model-button">下载</button>
                    </div>
                `;
                modelListContainer.appendChild(item);
            } else {
                console.warn("Skipping invalid model object in list:", modelObject);
            }
        });
    }

    // --- 加载并显示模型 ---
    async function loadAndDisplayModels() {
        console.log("loadAndDisplayModels 函数开始执行");
        try {
            const responseData = await getModels();
            console.log("Data received from getConfig:", responseData);
            renderModelList(responseData);
        } catch (error) {
            console.error("加载模型列表失败 (in loadAndDisplayModels):", error);
            if (modelListContainer) modelListContainer.innerHTML = '<p style="color: red; text-align: center;">无法加载模型列表。</p>';
            if (noModelsMessage) noModelsMessage.classList.add('hidden');
        }
    }

    // --- 事件委托：处理删除和下载按钮点击 ---
    if (modelListContainer) {
        modelListContainer.addEventListener('click', async (event) => {
            const target = event.target;
            const listItem = target.closest('.model-list-item');
            if (!listItem) return;

            const modelName = listItem.dataset.modelName;
            if (!modelName) {
                console.warn("无法从列表项获取 modelName:", listItem);
                return;
            }

            if (target.classList.contains('delete-model-button')) {
                console.log(`请求删除模型: ${modelName}`);
                const userConfirmed = await showConfirmation(
                    `确定要删除模型 "<strong>${modelName}</strong>" 吗？此操作不可恢复！`
                );
                if (userConfirmed) {
                    try {
                        const response = await sendInferenceCommand('DeleteModel', {"ModelName": modelName});
                        console.log(`删除模型 "${modelName}" 成功:`, response);
                        showNotification(2, `模型 "<strong>${modelName}</strong>" 已成功删除。`); // status 2 = 绿色成功
                        loadAndDisplayModels();
                    } catch (error) {
                        console.error(`删除模型 "${modelName}" 失败:`, error);
                        showNotification(0, `删除模型 "${modelName}" 失败: ${error.message || '未知错误'}`);
                    }
                }
            } else if (target.classList.contains('download-model-button')) {
                console.log(`请求下载模型: ${modelName}`);
                // --- 下载逻辑 ---
                try {
                    const downloadUrl = `${API_BASE_URL}/api/download_model?model=${encodeURIComponent(modelName)}`;
                    console.log(`构造下载链接: ${downloadUrl}`);

                    const link = document.createElement('a');
                    link.href = downloadUrl;
                    link.download = modelName;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    console.log(`已触发模型 "${modelName}" 的下载。`);
                    // 注意：这种方法无法直接知道下载是否真的成功（例如网络错误或服务器错误），

                } catch (error) {
                    // 这个 catch 主要捕获创建链接或点击时的 JS 错误，而不是下载本身的错误
                    console.error(`触发下载模型 "${modelName}" 时出错:`, error);
                    showNotification(0, `启动下载模型 "${modelName}" 时遇到问题: ${error.message || '未知错误'}`);
                }
            }
        });
    }

    // --- 上传按钮点击事件 ---
    if (uploadButton && fileInput) {
        uploadButton.addEventListener('click', () => {
            console.log("上传模型按钮被点击，触发文件选择...");
            fileInput.value = '';
            fileInput.click();
        });

        fileInput.addEventListener('change', async (event) => {
            const files = event.target.files;
            if (files.length > 0) {
                const file = files[0]; 
                console.log(`选择了文件: ${file.name}, 大小: ${file.size}, 类型: ${file.type}`);

                uploadButton.disabled = true;
                uploadButton.textContent = '上传中...';

                try {
                    const response = await uploadInferenceFile(
                        'UploadModel', // 命令
                        file,          // 文件对象
                        {}             // 无需附加数据，传空对象
                    );
                    console.log(`上传模型 "${file.name}" 成功:`, response);
                    showNotification(2, `模型 "${file.name}" 上传成功！`);
                    loadAndDisplayModels();
                } catch (error) {
                    console.error(`上传模型 "${file.name}" 失败:`, error);
                    showNotification(0, `上传模型 "${file.name}" 失败: ${error.message || '未知错误'}`);
                } finally {
                    uploadButton.disabled = false;
                    uploadButton.textContent = '上传模型';
                }
            } else {
                console.log("没有选择文件。");
            }
        });
    }
    window.loadAndDisplayModels = loadAndDisplayModels;

});