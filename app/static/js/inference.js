// js/inference.js
document.addEventListener('DOMContentLoaded', () => {
    /**
     * 从 /api/DownloadOutcome 获取结果并触发下载
     * @returns {Promise<void>}
     * @throws {Error} 如果请求失败或处理数据出错
     */
    async function downloadResults() {
        const url = `${API_BASE_URL}/api/DownloadOutcome`;
        console.log(`[Request] Fetching results for download from ${url}`);
        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                let errorBody = 'No error details';
                try { errorBody = await response.text(); } catch (e) { /* ignore */ }
                console.error(`[Request] Error response from ${url}: ${response.status} ${response.statusText}`, errorBody);
                throw new Error(`下载结果服务器错误: ${response.status} ${response.statusText}. ${errorBody}`);
            }

            const jsonData = await response.json();
            console.log(`[Request] Success response from ${url}:`, jsonData);

            const jsonString = JSON.stringify(jsonData, null, 2);
            const blob = new Blob([jsonString], { type: 'application/json' });

            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = downloadUrl;

            // 智能生成下载文件名
            let filename = 'detection_results.json';
            if (jsonData && jsonData.results_per_image && jsonData.results_per_image.length > 0 && jsonData.results_per_image[0].original_filename) {
                const originalName = jsonData.results_per_image[0].original_filename;
                filename = originalName.substring(0, originalName.lastIndexOf('.')) + '_results.json';
            } else if (jsonData && jsonData.inference_config_used && jsonData.inference_config_used.model_name) {
                filename = `${jsonData.inference_config_used.model_name}_results.json`;
            }
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(downloadUrl);
            document.body.removeChild(a);

            console.log('[Request] Results download triggered.');

        } catch (error) {
            console.error(`[Request] Network or fetch error for ${url}:`, error);
            showNotification(0, `下载结果失败: ${error.message}`);
            throw error;
        }
    }

    // --- DOM Element Selection ---
    const inferenceContent = document.getElementById('inference-content');
    if (!inferenceContent) return;

    const modelFolderButton = inferenceContent.querySelector('.model-folder-button');
    const modelSelect = inferenceContent.querySelector('#model-select');
    const loadModelButton = inferenceContent.querySelector('.load-model-button');

    // Overall metrics display elements
    const metricOverallStatus = document.getElementById('metric-status');
    const metricOverallTime = document.getElementById('metric-time'); // batch_processing_time_ms
    const metricOverallObjects = document.getElementById('metric-objects'); // total_objects_detected
    const metricOverallImagesProcessed = document.getElementById('metric-resolution'); // "成功处理X/Y张"
    const metricOverallAvgConfidence = document.getElementById('metric-confidence'); // batch_average_confidence
    const metricOverallAvgObjectsPerImage = document.getElementById('metric-iou'); // "平均每图目标数"

    const startDetectionButton = document.getElementById('start-detection-button');
    const saveResultsButton = document.getElementById('save-results-button');

    const uploadBox = document.getElementById('inference-upload-box');
    const uploadText = document.getElementById('inference-upload-text');
    const clearUploadButton = document.getElementById('inference-clear-button');

    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.multiple = true;
    fileInput.style.display = 'none';
    inferenceContent.appendChild(fileInput);

    const imagePreviewContainer = document.createElement('div');
    imagePreviewContainer.className = 'image-preview-container';
    imagePreviewContainer.style.display = 'none';

    // --- State Variables ---
    let loadButtonState = 'load'; // 'load', 'waiting', 'eject'
    let isFileUploaded = false; // File successfully uploaded to backend
    let currentUploadedFiles = []; // Local File objects for pre-upload preview
    let currentAtlasIndex = 0; // Current index for atlas (preview or results)
    let isAtlas = false; // Is current content an atlas
    let currentInferenceResults = null; // Stores `results_per_image` from backend

    /** Opens an image (File object or base64 string) in a new tab. */
    function openImageInNewTab(data, isBase64 = false, filename = 'image.png') {
        if (!data) return;
        try {
            let blobUrl;
            if (isBase64) {
                const newWindow = window.open();
                 if (newWindow) {
                    newWindow.document.write(`<title>${filename}</title><img src="${data}" alt="Enlarged: ${filename}" style="max-width:100%; max-height:100vh; image-rendering: pixelated; image-rendering: crisp-edges;"/>`);
                    newWindow.document.close();
                } else {
                    console.warn("打开新窗口可能被阻止。");
                    showNotification(0, "无法打开新窗口查看大图，请检查浏览器是否阻止了弹出窗口。");
                }
                return; // Base64 handled
            } else { // File object
                blobUrl = URL.createObjectURL(data);
            }

            const newWindow = window.open(blobUrl, '_blank');
            if (newWindow) {
                newWindow.onload = () => {
                    if (!isBase64) URL.revokeObjectURL(blobUrl); // Revoke for File objects
                };
            } else {
                 console.warn("打开新窗口可能被阻止。Blob URL 未立即释放。");
                 showNotification(0, "无法打开新窗口查看大图，请检查浏览器是否阻止了弹出窗口。");
                 if (!isBase64) URL.revokeObjectURL(blobUrl);
            }
        } catch (error) {
            console.error("创建或打开 Blob URL/Base64 图像时出错:", error);
            showNotification(0, "无法打开大图。");
        }
    }

    /** Updates the overall batch processing metrics display. */
    function updateOverallMetrics(overallMetrics = {}, statusText = '未知', message = '') {
        metricOverallImagesProcessed.textContent = (overallMetrics.total_images_processed_successfully !== undefined && overallMetrics.total_images_requested !== undefined)
            ? `${overallMetrics.total_images_processed_successfully} / ${overallMetrics.total_images_requested} 张成功`
            : '-';
        metricOverallAvgConfidence.textContent = overallMetrics.batch_average_confidence !== undefined
            ? parseFloat(overallMetrics.batch_average_confidence).toFixed(4)
            : '-';
        metricOverallAvgObjectsPerImage.textContent = overallMetrics.average_objects_per_successful_image !== undefined
            ? parseFloat(overallMetrics.average_objects_per_successful_image).toFixed(2)
            : '-';
        metricOverallStatus.textContent = statusText;
        if (message && statusText === '错误') {
            metricOverallStatus.title = message;
        } else {
            metricOverallStatus.title = '';
        }

        metricOverallTime.textContent = overallMetrics.batch_processing_time_ms !== undefined
            ? `${parseFloat(overallMetrics.batch_processing_time_ms).toFixed(2)} ms`
            : '-';
        metricOverallObjects.textContent = overallMetrics.total_objects_detected !== undefined
            ? overallMetrics.total_objects_detected
            : '-';

        switch(statusText) {
            case '检测完成': metricOverallStatus.style.color = '#28a745'; break;
            case '正在检测...': metricOverallStatus.style.color = '#ffc107'; break;
            case '错误': metricOverallStatus.style.color = '#dc3545'; break;
            default: metricOverallStatus.style.color = '#007bff';
        }
    }

    /** Resets the overall metrics display to initial state. */
    function resetOverallMetrics() {
         updateOverallMetrics({}, '未开始');
         metricOverallStatus.style.color = '#6c757d';
    }

    /** Populates the model selection dropdown from backend data. */
    async function populateModelDropdown() {
        console.log("尝试从后端获取模型列表以填充下拉框...");
        try {
            const modelsData =  await getModels();
            modelSelect.innerHTML = '<option value="" disabled selected>请选择模型...</option>';

            if (modelsData.length > 0) {
                modelsData.forEach(modelObject => {
                    if (modelObject && modelObject.modelname) {
                        const option = document.createElement('option');
                        option.value = modelObject.modelname;
                        option.textContent = modelObject.modelname;
                        modelSelect.appendChild(option);
                    } else {
                        console.warn("在模型数据中发现无效或缺少 'modelname' 的对象:", modelObject);
                    }
                });
                const modelNames = modelsData.map(m => m.modelname).filter(name => name);
                console.log("模型下拉列表已填充:", modelNames);
            } else {
                console.log("后端未返回可用模型列表。");
                 modelSelect.innerHTML = '<option value="" disabled selected>无可用模型</option>';
            }
        } catch (error) {
            console.error("填充模型下拉列表失败:", error);
            showNotification(0,"填充模型下拉列表失败:"+error);
            modelSelect.innerHTML = '<option value="" disabled selected>获取模型失败</option>';
        }
    }

    /** Updates the UI of the load/eject model button. */
    function updateLoadButtonUI(state) {
        loadModelButton.classList.remove('state-load', 'state-waiting', 'state-eject');
        loadModelButton.disabled = false;
        loadModelButton.style.cursor = 'pointer';

        switch (state) {
            case 'load':
                loadModelButton.textContent = '载入';
                loadModelButton.classList.add('state-load');
                break;
            case 'waiting':
                loadModelButton.textContent = '请稍后...';
                loadModelButton.classList.add('state-waiting');
                loadModelButton.disabled = true;
                loadModelButton.style.cursor = 'wait';
                break;
            case 'eject':
                loadModelButton.textContent = '弹出';
                loadModelButton.classList.add('state-eject');
                break;
            default:
                loadModelButton.textContent = '载入';
                loadModelButton.classList.add('state-load');
                loadButtonState = 'load';
        }
    }

    /** Displays pre-upload preview of selected image(s) (local File objects). */
    function displayPreview(files) {
        imagePreviewContainer.innerHTML = ''; // Clear for new content
        imagePreviewContainer.style.display = 'flex';
        uploadBox.classList.add('uploaded');
        uploadText.textContent = '';

        currentUploadedFiles = files; // File objects
        currentAtlasIndex = 0;
        isAtlas = files.length > 1;

        if (!imagePreviewContainer.parentNode) {
            uploadBox.appendChild(imagePreviewContainer);
        }

        if (isAtlas) {
            displayAtlasImagePreview(currentAtlasIndex);
        } else {
            const file = files[0];
            if (!file) return;

            const img = document.createElement('img');
            img.alt = '图片预览';
            img.style.display = 'block';
            img.style.maxWidth = '100%';
            img.style.maxHeight = '100%';
            img.style.objectFit = 'contain';
            img.style.cursor = 'zoom-in';

            img.onclick = () => openImageInNewTab(file, false, file.name);

            const reader = new FileReader();
            reader.onload = (e) => {
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
            imagePreviewContainer.appendChild(img);
        }
         clearUploadButton.classList.add('visible');
    }

    /** Displays a single image from an atlas for pre-upload preview (local File objects). */
    function displayAtlasImagePreview(index) {
        if (!isAtlas || index < 0 || index >= currentUploadedFiles.length) {
            console.error("无效的图集预览索引:", index);
            return;
        }
        currentAtlasIndex = index;
        const file = currentUploadedFiles[index]; // File object

        imagePreviewContainer.innerHTML = '';

        const img = document.createElement('img');
        img.alt = `图集预览 ${index + 1}/${currentUploadedFiles.length}`;
        img.style.display = 'block';
        img.style.maxWidth = '100%';
        img.style.maxHeight = 'calc(100% - 35px)'; // Space for controls
        img.style.objectFit = 'contain';
        img.style.cursor = 'zoom-in';
        img.style.marginBottom = '30px';

        img.onclick = () => openImageInNewTab(file, false, file.name);

        const reader = new FileReader();
        reader.onload = (e) => {
            img.src = e.target.result;
        };
        reader.readAsDataURL(file);
        imagePreviewContainer.appendChild(img);

        // Atlas navigation controls
        const controls = document.createElement('div');
        controls.className = 'atlas-controls';
        controls.style.position = 'absolute';
        controls.style.bottom = '5px';
        controls.style.left = '0';
        controls.style.width = '100%';
        controls.style.textAlign = 'center';
        controls.style.color = '#333';
        controls.style.backgroundColor = 'rgba(255, 255, 255, 0.7)';
        controls.style.padding = '5px 0';
        controls.style.boxSizing = 'border-box';
        controls.style.zIndex = '10';

        const prevButton = document.createElement('button');
        prevButton.textContent = '◀';
        prevButton.disabled = index === 0;
        prevButton.onclick = (e) => { e.stopPropagation(); displayAtlasImagePreview(index - 1); };
        prevButton.style.margin = '0 10px';
        prevButton.style.border = 'none';
        prevButton.style.background = 'transparent';
        prevButton.style.fontSize = '1.2em';
        prevButton.style.cursor = 'pointer';

        const nextButton = document.createElement('button');
        nextButton.textContent = '▶';
        nextButton.disabled = index === currentUploadedFiles.length - 1;
        nextButton.onclick = (e) => { e.stopPropagation(); displayAtlasImagePreview(index + 1); };
        nextButton.style.margin = '0 10px';
        nextButton.style.border = 'none';
        nextButton.style.background = 'transparent';
        nextButton.style.fontSize = '1.2em';
        nextButton.style.cursor = 'pointer';

        const counter = document.createElement('span');
        counter.textContent = `${index + 1} / ${currentUploadedFiles.length}`;
        counter.style.verticalAlign = 'middle';

        controls.appendChild(prevButton);
        controls.appendChild(counter);
        controls.appendChild(nextButton);
        imagePreviewContainer.appendChild(controls);
    }

    /** Displays a single inference result (annotated image and info) from backend data. */
    function displaySingleInferenceResult(resultItem, totalItems = 1, currentIndex = 0) {
        imagePreviewContainer.innerHTML = '';
        imagePreviewContainer.style.display = 'flex';
        uploadBox.classList.add('uploaded');
        uploadText.textContent = '';

        if (!imagePreviewContainer.parentNode) {
            uploadBox.appendChild(imagePreviewContainer);
        }

        const resultWrapper = document.createElement('div');
        resultWrapper.style.width = '100%';
        resultWrapper.style.height = '100%';
        resultWrapper.style.display = 'flex';
        resultWrapper.style.flexDirection = 'column';
        resultWrapper.style.alignItems = 'center';
        resultWrapper.style.justifyContent = 'center';
        resultWrapper.style.position = 'relative'; // For atlas controls

        const img = document.createElement('img');
        img.alt = resultItem.original_filename || `检测结果 ${currentIndex + 1}/${totalItems}`;
        img.style.display = 'block';
        img.style.maxWidth = '100%';
        img.style.maxHeight = totalItems > 1 ? 'calc(100% - 70px)' : 'calc(100% - 35px)';
        img.style.objectFit = 'contain';
        img.style.cursor = 'zoom-in';
        img.style.marginBottom = '5px';

        if (resultItem.annotated_image_base64) {
            img.src = resultItem.annotated_image_base64;
            img.onclick = () => openImageInNewTab(resultItem.annotated_image_base64, true, resultItem.original_filename);
        } else if (resultItem.error) {
            img.alt = `错误: ${resultItem.original_filename}`;
            const errorTextElement = document.createElement('p');
            errorTextElement.textContent = `处理图片 ${resultItem.original_filename} 失败: ${resultItem.error}`;
            errorTextElement.style.color = 'red';
            imagePreviewContainer.appendChild(errorTextElement); // Display error instead of image
        }
        resultWrapper.appendChild(img);

        // Display single image info (filename, metrics, etc.)
        const infoDiv = document.createElement('div');
        infoDiv.className = 'inference-image-info';
        infoDiv.style.fontSize = '0.8em';
        infoDiv.style.textAlign = 'left';
        infoDiv.style.padding = '5px';
        infoDiv.style.overflowY = 'hidden';
        infoDiv.style.whiteSpace = 'nowrap';
        infoDiv.style.textOverflow = 'ellipsis';
        infoDiv.style.overflowX = 'hidden';
        infoDiv.style.maxHeight = totalItems > 1 ? '30px' : '30px';
        infoDiv.style.width = 'calc(100% - 10px)';
        infoDiv.style.boxSizing = 'border-box';
        infoDiv.style.borderTop = '1px solid #ccc';
        infoDiv.style.marginTop = '5px';

        let infoParts = [];
        if (resultItem.original_filename) {
            infoParts.push(`<strong>${resultItem.original_filename}</strong>`);
        } else {
            infoParts.push('<strong>未知图片</strong>');
        }

        if (resultItem.metrics) {
            let metricsString = "";
            if (resultItem.metrics.detection_time_ms !== undefined) {
                metricsString += `耗时: ${resultItem.metrics.detection_time_ms}ms`;
            }
            if (resultItem.metrics.object_count !== undefined) {
                metricsString += `${metricsString ? ', ' : ''}目标: ${resultItem.metrics.object_count}`;
            }
            if (resultItem.metrics.average_confidence !== undefined && resultItem.metrics.object_count > 0) {
                metricsString += `${metricsString ? ', ' : ''}均置信: ${parseFloat(resultItem.metrics.average_confidence).toFixed(2)}`;
            }
            if (metricsString) {
                infoParts.push(metricsString);
            }
        }

        if (resultItem.error) {
            infoParts.push(`<span style="color:red;">错误: ${resultItem.error.length > 20 ? resultItem.error.substring(0, 17) + '...' : resultItem.error}</span>`);
        }

        infoDiv.innerHTML = infoParts.join(' | ');
        infoDiv.title = infoParts.join(' | ').replace(/<strong>|<\/strong>|<span style="color:red;">|<\/span>/g, ''); // Tooltip with full info

        resultWrapper.appendChild(infoDiv);
        imagePreviewContainer.appendChild(resultWrapper);

        // Atlas navigation controls for results
        if (totalItems > 1) {
            const controls = document.createElement('div');
            controls.className = 'atlas-controls result-atlas-controls';
            controls.style.position = 'absolute';
            controls.style.bottom = '40px'; // Position above the infoDiv
            controls.style.left = '0';
            controls.style.width = '100%';
            controls.style.textAlign = 'center';
            controls.style.color = '#333';
            controls.style.backgroundColor = 'rgba(255, 255, 255, 0.8)';
            controls.style.padding = '5px 0';
            controls.style.boxSizing = 'border-box';
            controls.style.zIndex = '10';

            const prevButton = document.createElement('button');
            prevButton.textContent = '◀';
            prevButton.disabled = currentIndex === 0;
            prevButton.onclick = (e) => {
                e.stopPropagation();
                currentAtlasIndex = currentIndex - 1;
                displaySingleInferenceResult(currentInferenceResults[currentAtlasIndex], totalItems, currentAtlasIndex);
            };
            prevButton.style.margin = '0 10px';
            prevButton.style.border = 'none';
            prevButton.style.background = 'transparent';
            prevButton.style.fontSize = '1.2em';
            prevButton.style.cursor = 'pointer';

            const nextButton = document.createElement('button');
            nextButton.textContent = '▶';
            nextButton.disabled = currentIndex === totalItems - 1;
            nextButton.onclick = (e) => {
                e.stopPropagation();
                currentAtlasIndex = currentIndex + 1;
                displaySingleInferenceResult(currentInferenceResults[currentAtlasIndex], totalItems, currentAtlasIndex);
            };
            nextButton.style.margin = '0 10px';
            nextButton.style.border = 'none';
            nextButton.style.background = 'transparent';
            nextButton.style.fontSize = '1.2em';
            nextButton.style.cursor = 'pointer';

            const counter = document.createElement('span');
            counter.textContent = `${currentIndex + 1} / ${totalItems}`;
            counter.style.verticalAlign = 'middle';

            controls.appendChild(prevButton);
            controls.appendChild(counter);
            controls.appendChild(nextButton);
            resultWrapper.appendChild(controls);
        }
        clearUploadButton.classList.add('visible');
    }

    /** Displays a batch of inference results. */
    function displayInferenceResultsBatch(resultsPerImage) {
        currentInferenceResults = resultsPerImage; // Store for atlas navigation
        isAtlas = resultsPerImage.length > 1;
        currentAtlasIndex = 0;

        if (!resultsPerImage || resultsPerImage.length === 0) {
            imagePreviewContainer.innerHTML = '<p>没有检测结果可显示。</p>';
            imagePreviewContainer.style.display = 'flex';
            if (!imagePreviewContainer.parentNode) {
                uploadBox.appendChild(imagePreviewContainer);
            }
            return;
        }
        displaySingleInferenceResult(resultsPerImage[currentAtlasIndex], resultsPerImage.length, currentAtlasIndex);
    }

    /** Clears image preview, uploaded files, inference results, and resets related states. */
    function clearPreviewAndState() {
        imagePreviewContainer.innerHTML = '';
        imagePreviewContainer.style.display = 'none';
        uploadBox.classList.remove('uploaded');
        uploadText.textContent = '上传图像或图集';
        clearUploadButton.classList.remove('visible');
        fileInput.value = null;

        isFileUploaded = false;
        currentUploadedFiles = [];
        currentInferenceResults = null;
        isAtlas = false;

        resetOverallMetrics();

        startDetectionButton.disabled = false;
        startDetectionButton.textContent = '开始检测';
        saveResultsButton.disabled = true;
    }

    if (modelSelect) {
        modelSelect.addEventListener('change', () => {
            const selectedModel = modelSelect.value;
            if (selectedModel) {
                console.log(`选择了模型: ${selectedModel}`);
                if (loadButtonState === 'eject') {
                     loadButtonState = 'load';
                     updateLoadButtonUI(loadButtonState);
                     console.log('模型更改，重置加载按钮为 "载入" 状态');
                }
            }
        });
    }

    if (loadModelButton) {
        loadModelButton.addEventListener('click', async () => {
            console.log(`加载/弹出按钮被点击，当前状态: ${loadButtonState}`);

            if (loadButtonState === 'load') {
                const selectedModel = modelSelect.value;
                if (!selectedModel) {
                    showNotification(1, '请先选择一个模型！');
                    return;
                }
                console.log(`请求加载模型: ${selectedModel}`);
                loadButtonState = 'waiting';
                updateLoadButtonUI(loadButtonState);

                try {
                    const response = await sendInferenceCommand('LoadModel', { ModelName: selectedModel });
                    console.log('模型加载成功:', response);
                    if (response.loadedModel === selectedModel) {
                        loadButtonState = 'eject';
                         showNotification(2, `模型 '${selectedModel}' 加载成功。`);
                    } else {
                         console.warn("后端返回的模型与请求不符或加载失败", response);
                         showNotification(0, `模型加载可能失败: ${response.message || '未知原因'}`);
                         loadButtonState = 'load';
                    }
                    updateLoadButtonUI(loadButtonState);
                } catch (error) {
                    console.error('加载模型失败:', error);
                    showNotification(0, `加载模型失败: ${error.message}`);
                    loadButtonState = 'load';
                    updateLoadButtonUI(loadButtonState);
                }

            } else if (loadButtonState === 'eject') {
                console.log('请求弹出模型');
                loadButtonState = 'waiting';
                updateLoadButtonUI(loadButtonState);

                try {
                    const response = await sendInferenceCommand('EjectModel');
                    console.log('模型弹出成功:', response);
                    showNotification(2, '模型已弹出。');
                    loadButtonState = 'load';
                    updateLoadButtonUI(loadButtonState);
                    resetOverallMetrics();
                    startDetectionButton.disabled = false;
                    startDetectionButton.textContent = '开始检测';
                } catch (error) {
                    console.error('弹出模型失败:', error);
                    showNotification(0, `弹出模型失败: ${error.message}`);
                    loadButtonState = 'eject';
                    updateLoadButtonUI(loadButtonState);
                }
            }
        });
    }

    if (uploadBox) {
        uploadBox.addEventListener('click', (event) => { // Added event parameter
            const isDisplayingSomething = imagePreviewContainer.style.display !== 'none' && imagePreviewContainer.innerHTML.trim() !== '';
            if (!isDisplayingSomething || !isFileUploaded) {
                 if (event.target === uploadBox || event.target === uploadText) { // Click on empty area or text
                    console.log('点击上传框，触发文件选择...');
                    fileInput.click();
                }
            } else {
                console.log('文件已上传或结果已显示，请先清除或直接开始检测。点击图片本身可能有其他操作。');
            }
        });
    }


    fileInput.addEventListener('change', async (event) => {
        const files = event.target.files;
        if (!files || files.length === 0) {
            console.log('未选择文件');
            return;
        }

        if (currentInferenceResults) {
            console.log("检测到已有推理结果，在上传新文件前清除...");
            clearPreviewAndState();
        }

        const fileList = Array.from(files);
        console.log(`选择了 ${fileList.length} 个文件`);

        imagePreviewContainer.style.display = 'flex';
        imagePreviewContainer.style.justifyContent = 'center';
        imagePreviewContainer.style.alignItems = 'center';
        imagePreviewContainer.style.backgroundColor = '#e9ecef';
        imagePreviewContainer.style.overflow = 'hidden';
        imagePreviewContainer.style.padding = '5px';
        imagePreviewContainer.style.boxSizing = 'border-box';
        imagePreviewContainer.style.width = '100%';
        imagePreviewContainer.style.height = '100%';

        if (!imagePreviewContainer.parentNode) {
             uploadBox.appendChild(imagePreviewContainer);
        } else {
             imagePreviewContainer.innerHTML = '';
        }

        displayPreview(fileList); // Show local file preview

        const isUploadingAtlas = fileList.length > 1;
        const uploadCommand = isUploadingAtlas ? 'UploadAtlas' : 'UploadPicture';
        const filesToUpload = isUploadingAtlas ? fileList : fileList[0];

        try {
            const response = await uploadInferenceFile(
                uploadCommand,
                filesToUpload,
                { type: isUploadingAtlas ? 'atlas' : 'picture' }
            );
            console.log(`文件${isUploadingAtlas ? '图集' : ''}上传成功:`, response);
            showNotification(2, `文件${isUploadingAtlas ? '图集' : ''}上传成功。`);
            isFileUploaded = true;
            saveResultsButton.disabled = true;

        } catch (error) {
            console.error(`文件${isUploadingAtlas ? '图集' : ''}上传失败:`, error);
            showNotification(0, `文件${isUploadingAtlas ? '图集' : ''}上传失败: ${error.message}`);
            clearPreviewAndState();
        }
    });


    if (clearUploadButton) {
        clearUploadButton.addEventListener('click', async (event) => {
            event.stopPropagation(); // Prevent bubbling to uploadBox
            if (imagePreviewContainer.style.display !== 'none' && imagePreviewContainer.innerHTML.trim() !== '') {
                console.log('请求清除上传内容或检测结果');
                const wasShowingResults = !!currentInferenceResults;
                clearPreviewAndState();
                try {
                    if (isFileUploaded || wasShowingResults) {
                         await sendInferenceCommand('Clear');
                         console.log('后端清除操作成功');
                         isFileUploaded = false;
                    }
                } catch (error) {
                    console.warn('通知后端清除失败 (这可能不是问题，如果前端已无内容):', error.message);
                }
            }
        });
    }

    if (startDetectionButton) {
        startDetectionButton.addEventListener('click', async () => {
            if (!isFileUploaded) {
                showNotification(1, '请先上传图片或图集！');
                return;
            }
            if (loadButtonState !== 'eject') {
                showNotification(1, '请先选择并加载一个模型！');
                return;
            }

            console.log('请求开始检测...');
            startDetectionButton.disabled = true;
            startDetectionButton.textContent = '检测中...';
            saveResultsButton.disabled = true;

            updateOverallMetrics({}, '正在检测...', '计算中...');

            // Prepare inference configuration (example, actual values might come from UI)
            const inferenceConfig = {
                 // confidence: 0.25, // Example
                 // iou: 0.45,        // Example
            };
            console.log("使用推理参数:", inferenceConfig);

            try {
                const response = await sendInferenceCommand('Start', inferenceConfig);
                console.log('检测请求成功:', response);

                if (response.status === 'success' && response.overall_metrics && response.results_per_image) {
                    updateOverallMetrics(response.overall_metrics, '检测完成', response.message);
                    displayInferenceResultsBatch(response.results_per_image);
                    if (response.inference_config_used) {
                        console.log("实际使用的推理配置:", response.inference_config_used);
                    }
                    saveResultsButton.disabled = false;
                } else {
                    console.error("检测失败或返回格式错误:", response);
                    const errorMessage = response.message || (response.error ? response.error : '未知错误');
                    updateOverallMetrics({}, '错误', errorMessage);
                    showNotification(0, `检测失败: ${errorMessage}`);
                    if (response.results_per_image && response.results_per_image.length > 0) {
                        displayInferenceResultsBatch(response.results_per_image);
                    } else {
                         imagePreviewContainer.innerHTML = `<p style="color:red;">检测处理失败: ${errorMessage}</p>`;
                         imagePreviewContainer.style.display = 'flex';
                         if (!imagePreviewContainer.parentNode) {
                            uploadBox.appendChild(imagePreviewContainer);
                         }
                    }
                }

            } catch (error) {
                console.error('检测请求失败:', error);
                updateOverallMetrics({}, '错误', error.message);
                showNotification(0, `检测失败: ${error.message}`);
                 imagePreviewContainer.innerHTML = `<p style="color:red;">检测请求异常: ${error.message}</p>`;
                 imagePreviewContainer.style.display = 'flex';
                 if (!imagePreviewContainer.parentNode) {
                    uploadBox.appendChild(imagePreviewContainer);
                 }
            } finally {
                 startDetectionButton.disabled = false;
                 startDetectionButton.textContent = '开始检测';
            }
        });
    }

    if (saveResultsButton) {
        saveResultsButton.addEventListener('click', async () => {
            if (saveResultsButton.disabled) return;

            console.log('请求下载结果...');
            saveResultsButton.disabled = true;
            saveResultsButton.textContent = '下载中...';

            try {
                await downloadResults();
            } catch (error) {
                console.error('下载结果时捕获到顶层错误。');
            } finally {
                saveResultsButton.disabled = false;
                saveResultsButton.textContent = '保存结果';
            }
        });
    }

     if (modelFolderButton) {
        modelFolderButton.addEventListener('click', () => {
            console.log('模型管理按钮 (inference.js) 被点击');
            if (typeof showContentSection === 'function') {
                currentSubView = 'modelManagement';
                parentSectionForSubView = 'inference';
                currentSection = null; // Ensure main section highlighting is cleared
                showContentSection('model-management-content');
                if (typeof loadAndDisplayModels === 'function') {
                    loadAndDisplayModels(); // Function from modelManagement.js
                } else {
                    console.warn('loadAndDisplayModels function not found.');
                    const msgElement = document.getElementById('no-models-message'); // In model-management-content
                     if(msgElement) msgElement.classList.remove('hidden');
                }
            } else {
                 console.error('showContentSection function is not defined globally.');
                 showNotification(0, '无法切换到模型管理视图。');
            }
        });
    }

    // --- Initialization ---
    console.log("初始化推理模块...");
    populateModelDropdown();
    resetOverallMetrics();
    saveResultsButton.disabled = true;

});