// --- DOM Elements ---
const buttons = document.querySelectorAll('.tool-button');
const contentView = document.getElementById('content-view');
const contentArea = document.getElementById('content-area');
const contentPlaceholder = document.getElementById('content-placeholder');
const backButton = document.getElementById('back-button');
const tasksButton = document.getElementById('tasks-button');
const mainContainer = document.querySelector('.button-container');
const header = document.querySelector('header');
const contentSections = document.querySelectorAll('.content-section');
const contentTitle = document.getElementById('content-title');
const settingsOverlay = document.getElementById('settings-overlay');
const inferenceSettingsContent = document.getElementById('inference-settings-content');
const closeSettingsButton = document.getElementById('close-settings-button');
const settingsButton = document.getElementById('settings-button');

// --- New DOM Elements for Settings ---
const settingConfidenceSlider = document.getElementById('setting-confidence');
const settingConfidenceValue = document.getElementById('setting-confidence-value');
const settingIouSlider = document.getElementById('setting-iou');
const settingIouValue = document.getElementById('setting-iou-value');
const settingImgszInput = document.getElementById('setting-imgsz');
const settingDeviceRadios = document.querySelectorAll('input[name="device"]');
const settingHalfCheckbox = document.getElementById('setting-half');
const settingAugmentCheckbox = document.getElementById('setting-augment');
const settingMaxDetInput = document.getElementById('setting-max-det');
const importConfigButton = document.getElementById('import-config-button');
const exportConfigButton = document.getElementById('export-config-button');
const configFileIn = document.getElementById('config-file-input');


// --- State ---
let currentSection = null;
let currentSubView = 'main'; // 'main', 'tasks', 'modelManagement'
let parentSectionForSubView = null;
let activeSectionElement = null;
let isSettingsPanelVisible = false;
let configUploadDebounceTimer = null;

let inferenceParams = {
    conf: 0.25,
    iou: 0.45,
    imgsz: 640,
    device: 'cpu',
    half: false,
    augment: false,
    max_det: 300
};

function updateSliderValueDisplay(sliderElement, displayElement) {
    if (sliderElement && displayElement) {
        displayElement.textContent = parseFloat(sliderElement.value).toFixed(2);
    }
}

/**
 * 上传当前的 inferenceParams 配置到后端。
 * 使用 sendInferenceCommand 发送 'UploadConfig' 命令。
 * @param {object} configData - 要上传的配置对象 (通常是 inferenceParams)。
 * @returns {Promise<void>}
 */
async function uploadCurrentConfig(configData) {
    console.log('[自动上传] 准备上传配置:', configData);
    try {
        const response = await sendInferenceCommand('UpdateConfig', { config: configData });
        console.log('[自动上传] 配置上传成功:', response);
    } catch (error) {
        showNotification(0, '[自动上传] 配置上传失败:' + error);
    }
}

/**
 * 防抖处理函数：延迟上传配置，用于滑块等频繁触发的控件。
 * @param {object} configData - 当前的配置对象。
 * @param {number} delay - 延迟时间（毫秒）
 */
function debouncedUploadConfig(configData, delay = 500) {
    clearTimeout(configUploadDebounceTimer);
    configUploadDebounceTimer = setTimeout(() => {
        uploadCurrentConfig(configData);
    }, delay);
}

function populateSettingsPanel() {
    if (!inferenceSettingsContent) return;

    // Confidence
    if (settingConfidenceSlider && settingConfidenceValue) {
        settingConfidenceSlider.value = inferenceParams.conf;
        updateSliderValueDisplay(settingConfidenceSlider, settingConfidenceValue);
    }
    // IoU
    if (settingIouSlider && settingIouValue) {
        settingIouSlider.value = inferenceParams.iou;
        updateSliderValueDisplay(settingIouSlider, settingIouValue);
    }
    // Image Size
    if (settingImgszInput) {
        settingImgszInput.value = inferenceParams.imgsz;
    }
    // Device
    if (settingDeviceRadios) {
        settingDeviceRadios.forEach(radio => {
        radio.checked = (radio.value === inferenceParams.device);
    });
    }
    // Half Precision
    if (settingHalfCheckbox) {
        settingHalfCheckbox.checked = inferenceParams.half;
    }
    // Augment
    if (settingAugmentCheckbox) {
        settingAugmentCheckbox.checked = inferenceParams.augment;
    }
    // Max Detections
    if (settingMaxDetInput) {
        settingMaxDetInput.value = inferenceParams.max_det;
    }
    console.log("Settings panel populated with:", inferenceParams);
    uploadCurrentConfig(inferenceParams);

}


function showSettingsPanel() {
    if (!settingsOverlay || !inferenceSettingsContent) return;
    console.log("Showing settings panel and overlay.");

    populateSettingsPanel();

    settingsOverlay.classList.remove('hidden');
    inferenceSettingsContent.classList.remove('hidden');

    requestAnimationFrame(() => {
        setTimeout(() => {
            settingsOverlay.classList.add('visible');
            inferenceSettingsContent.classList.add('visible');
            isSettingsPanelVisible = true;
        }, 10);
    });
}

function hideSettingsPanel() {
    if (!settingsOverlay || !inferenceSettingsContent || !isSettingsPanelVisible) return;
    console.log("Hiding settings panel and overlay.");

    settingsOverlay.classList.remove('visible');
    inferenceSettingsContent.classList.remove('visible');

    updateInferenceMetricsDisplay();

    setTimeout(() => {
        settingsOverlay.classList.add('hidden');
        inferenceSettingsContent.classList.add('hidden');
        isSettingsPanelVisible = false;
    }, 300);
}

function updateInferenceMetricsDisplay() {
    const metricConfidence = document.getElementById('metric-confidence');
    const metricIou = document.getElementById('metric-iou');

    if (metricConfidence) {
        metricConfidence.textContent = inferenceParams.conf.toFixed(2);
    }
    if (metricIou) {
        metricIou.textContent = inferenceParams.iou.toFixed(2);
    }
}

if (settingsButton) {
    settingsButton.addEventListener('click', (event) => {
        event.stopPropagation();
        console.log('参数设置按钮 (main.js listener) 被点击');
        showSettingsPanel();
    });
} else {
    console.warn('Settings button (#settings-button) not found in the DOM.');
}

if (closeSettingsButton) {
    closeSettingsButton.addEventListener('click', (event) => {
        event.stopPropagation();
        hideSettingsPanel();
    });
} else {
    console.warn('Close settings button (#close-settings-button) not found.');
}

if (settingsOverlay) {
    settingsOverlay.addEventListener('click', (event) => {
        if (event.target === settingsOverlay) {
            hideSettingsPanel();
        }
    });
} else {
    console.warn('Settings overlay (#settings-overlay) not found.');
}
if (settingConfidenceSlider && settingConfidenceValue) {
    settingConfidenceSlider.addEventListener('input', () => {
        updateSliderValueDisplay(settingConfidenceSlider, settingConfidenceValue);
        inferenceParams.conf = parseFloat(settingConfidenceSlider.value);
        debouncedUploadConfig(inferenceParams);
    });
}
if (settingIouSlider && settingIouValue) {
    settingIouSlider.addEventListener('input', () => {
        updateSliderValueDisplay(settingIouSlider, settingIouValue);
        inferenceParams.iou = parseFloat(settingIouSlider.value);
        debouncedUploadConfig(inferenceParams);
    });
}
if (settingImgszInput) {
    settingImgszInput.addEventListener('change', () => {
        let val = parseInt(settingImgszInput.value, 10);
        if (isNaN(val) || val < 32) val = 32;
        if (val > 2048) val = 2048;
        val = Math.round(val / 32) * 32;
        settingImgszInput.value = val;
        inferenceParams.imgsz = val;
        debouncedUploadConfig(inferenceParams);
    });
}
if (settingDeviceRadios) {
    settingDeviceRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            if (radio.checked) {
                inferenceParams.device = radio.value;
                uploadCurrentConfig(inferenceParams);
            }
        });
    });
}
if (settingHalfCheckbox) {
    settingHalfCheckbox.addEventListener('change', () => {
        inferenceParams.half = settingHalfCheckbox.checked;
        uploadCurrentConfig(inferenceParams);
    });
}
if (settingAugmentCheckbox) {
    settingAugmentCheckbox.addEventListener('change', () => {
        inferenceParams.augment = settingAugmentCheckbox.checked;
        uploadCurrentConfig(inferenceParams);
    });
}
if (settingMaxDetInput) {
    settingMaxDetInput.addEventListener('change', () => {
        let val = parseInt(settingMaxDetInput.value, 10);
        if (isNaN(val) || val < 1) val = 1;
        if (val > 1000) val = 1000;
        settingMaxDetInput.value = val;
        inferenceParams.max_det = val;
        debouncedUploadConfig(inferenceParams);
    });
}

if (exportConfigButton) {
    exportConfigButton.addEventListener('click', () => {
        try {
            const configJson = JSON.stringify(inferenceParams, null, 2);
            const blob = new Blob([configJson], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'inference_config.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            console.log('Configuration exported successfully.');
        } catch (error) {
            console.error('Error exporting configuration:', error);
            showNotification(0, '导出配置失败！');
        }
    });
}

if (importConfigButton && configFileIn) {
    importConfigButton.addEventListener('click', () => {
        configFileIn.click();
    });

    configFileIn.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (!file) {
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const importedConfig = JSON.parse(e.target.result);
                console.log('Imported config data:', importedConfig);
                for (const key in inferenceParams) {
                    if (importedConfig.hasOwnProperty(key)) {
                         inferenceParams[key] = importedConfig[key];
                    }
                }

                console.log('Updated inferenceParams after import:', inferenceParams);
                populateSettingsPanel();

                updateInferenceMetricsDisplay();
            } catch (error) {
                console.error('Error importing or parsing configuration:', error);
                showNotification(0, '导入配置失败！请确保文件是有效的 JSON 格式。');
            } finally {
                 configFileIn.value = '';
            }
        };
        reader.onerror = (e) => {
             console.error('Error reading file:', e);
             showNotification(0, '读取文件失败！');
             configFileIn.value = '';
        };
        reader.readAsText(file);
    });
}

function showContentSection(sectionId) {
    let foundSection = null;
    contentSections.forEach(section => {
        if (section.id === sectionId) {
            section.classList.remove('hidden');
            foundSection = section;
        } else {
            section.classList.add('hidden');
        }
    });

    const modelManagementSection = document.getElementById('model-management-content');
    if (modelManagementSection && modelManagementSection.id === sectionId) {
         modelManagementSection.classList.remove('hidden');
         foundSection = modelManagementSection;
    } else if (modelManagementSection) {
         modelManagementSection.classList.add('hidden');
    }


    if (foundSection && foundSection.dataset.title) {
        contentTitle.textContent = foundSection.dataset.title;
        activeSectionElement = foundSection;
    } else {
        contentTitle.textContent = '';
        activeSectionElement = null;
    }

    if ((currentSection === 'finetune' || currentSection === 'validate') && currentSubView === 'main') {
        tasksButton.classList.remove('hidden');
    } else {
        tasksButton.classList.add('hidden');
    }

    if (sectionId === 'inference-content') {
        updateInferenceMetricsDisplay();
    }
}

function openContentView(section) {
    currentSection = section;
    currentSubView = 'main';
    console.log(`Opening section: ${currentSection} (main view)`);

    if (isSettingsPanelVisible) {
        hideSettingsPanel();
    }

    mainContainer.classList.add('hidden');
    header.classList.add('hidden');
    document.querySelector('.auth-links')?.classList.add('hidden');

    if (section === 'login' || section === 'signup') {
        contentArea.classList.add('auth-mode');
        console.log('ContentArea entering auth-mode.');
    } else {
        contentArea.classList.remove('auth-mode');
        console.log('ContentArea exiting auth-mode.');
    }

    showContentSection(`${currentSection}-content`);

    contentView.classList.remove('hidden');

    requestAnimationFrame(() => {
         setTimeout(() => {
            contentView.classList.add('visible');
            contentArea.classList.add('visible');
            document.body.style.overflow = 'hidden';
         }, 10);
    });
}

function closeContentView() {
    console.log("Closing content view, returning to main menu.");

    if (isSettingsPanelVisible) {
        hideSettingsPanel();
    }

    contentView.classList.remove('visible');
    contentArea.classList.remove('visible');
    contentArea.classList.remove('auth-mode');
    document.body.style.overflow = '';

    setTimeout(() => {
        contentView.classList.add('hidden');
        contentSections.forEach(section => section.classList.add('hidden'));
        contentTitle.textContent = '';
        activeSectionElement = null;

        mainContainer.classList.remove('hidden');
        header.classList.remove('hidden');
        document.querySelector('.auth-links')?.classList.remove('hidden');

        currentSection = null;
        currentSubView = 'main';
        parentSectionForSubView = null;

    }, 350);
}


buttons.forEach(button => {
    button.addEventListener('click', () => {
        const section = button.dataset.section;
        if (!section) return;

        console.log(`Button "${section}" clicked!`);
        button.classList.add('enlarging');

        setTimeout(() => {
            button.classList.remove('enlarging');
             openContentView(section);
        }, 150);
    });
});

backButton.addEventListener('click', () => {
    if (isSettingsPanelVisible) {
        hideSettingsPanel();
        return;
    }

    if (!currentSection && !parentSectionForSubView) return;

    if (currentSection === 'login' || currentSection === 'signup') {
        console.log(`Back button: From ${currentSection} view to main menu.`);
        closeContentView();
        return;
    }

    if (currentSubView === 'tasks') {
        console.log(`Back button: From tasks view of ${currentSection} to main view.`);
        currentSubView = 'main';
        showContentSection(`${currentSection}-content`);
    } else if (currentSubView === 'modelManagement') {
        console.log(`Back button: From model management view to ${parentSectionForSubView} main view.`);
        const parentViewId = `${parentSectionForSubView}-content`;
        currentSubView = 'main';
        currentSection = parentSectionForSubView;
        parentSectionForSubView = null;
        showContentSection(parentViewId);
    } else if (currentSubView === 'main') {
        console.log(`Back button: From main view of ${currentSection} to main menu.`);
        closeContentView();
    }else if (currentSubView === 'main') {
        console.log(`Back button: From main view of ${currentSection} to main menu.`);
        closeContentView();
    }
});

tasksButton.addEventListener('click', () => {
    if (!currentSection || currentSubView !== 'main' || (currentSection !== 'finetune' && currentSection !== 'validate')) {
        return;
    }

    console.log(`Tasks button: Switching to tasks view for: ${currentSection}`);
    const targetSectionId = `${currentSection}-tasks-content`;
    parentSectionForSubView = currentSection; 
    currentSubView = 'tasks';
    showContentSection(targetSectionId);

    if (currentSection === 'finetune') {
        if (typeof window.loadAndDisplayFinetuneTasks === 'function') {
            console.log("Calling loadAndDisplayFinetuneTasks...");
            window.loadAndDisplayFinetuneTasks();
        } else {
            console.warn('loadAndDisplayFinetuneTasks function not found.');
        }
    } else if (currentSection === 'validate') {
        if (typeof window.loadAndDisplayValidateTasks === 'function') {
            console.log("Calling loadAndDisplayValidateTasks...");
            window.loadAndDisplayValidateTasks();
        } else {
            console.warn('loadAndDisplayValidateTasks function not found.');
        }
    }
});
