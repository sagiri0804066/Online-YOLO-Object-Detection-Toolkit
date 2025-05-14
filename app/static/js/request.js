// js/request.js

const API_BASE_URL = ''; // 留空表示使用相对路径

// ==================================================
// 认证相关函数
// ==================================================

/**
 * 注册新用户。
 * @param {string} username - 用户名。
 * @param {string} password - 密码。
 * @returns {Promise<object>} 后端返回的 JSON 对象 (例如: { message: "用户创建成功", user_id: ... })。
 * @throws {Error} 如果网络请求失败或服务器返回错误状态码 (如 400, 409, 500)。
 */
async function register(username, password) {
    const url = `${API_BASE_URL}/api/auth/signup`;
    const payload = { username, password };

    console.log(`[Auth] 尝试注册用户 '${username}' 至 ${url}`);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        // 尝试解析响应体，无论成功与否，因为错误信息可能在 JSON 中
        let responseData;
        try {
            responseData = await response.json();
        } catch (e) {
            // 解析 JSON 失败 (例如响应体为空或非 JSON)
            if (!response.ok) {
                // 若请求本身失败，抛出基于状态码的错误
                console.error(`[Auth] 注册失败于 ${url}: ${response.status} ${response.statusText}. 响应体非有效 JSON。`);
                throw new Error(`注册失败: ${response.status} ${response.statusText}. 服务器响应格式错误。`);
            } else {
                // 请求成功但响应体无法解析 (不常见，但作为保护)
                console.warn(`[Auth] 来自 ${url} 的注册响应成功 (${response.status}) 但响应体非有效 JSON。`);
                return { status: response.status, message: "操作可能成功，但服务器响应格式错误" };
            }
        }

        if (!response.ok) {
            // 使用从 JSON 解析出的错误信息
            const errorMessage = responseData?.error || `HTTP ${response.status} ${response.statusText}`;
            console.error(`[Auth] 用户 '${username}' 注册失败于 ${url}:`, errorMessage);
            const error = new Error(`注册失败: ${errorMessage}`);
            error.response = responseData; // 附加完整的响应数据
            error.status = response.status;
            throw error;
        }

        console.log(`[Auth] 用户 '${username}' 注册成功:`, responseData);
        return responseData;

    } catch (error) {
        // 捕获 fetch 网络错误或上方显式抛出的错误
        if (!error.status) { // 若错误非自定义的带 status 的 Error 对象
            console.error(`[Auth] ${url} 注册期间网络或处理错误:`, error);
        }
        throw error; // 重新抛出，由调用者处理
    }
}

/**
 * 用户登录。
 * @param {string} username - 用户名。
 * @param {string} password - 密码。
 * @returns {Promise<object>} 后端返回的 JSON 对象 (例如: { message: "登录成功", user: { id: ..., username: ... } })。
 * @throws {Error} 如果网络请求失败或服务器返回错误状态码 (如 400, 401)。
 */
async function login(username, password) {
    const url = `${API_BASE_URL}/api/auth/login`;
    const payload = { username, password };

    console.log(`[Auth] 尝试登录用户 '${username}' 至 ${url}`);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(payload)
            // 注意：浏览器会自动处理和发送与该域相关的 cookie (包括会话 cookie)
        });

        let responseData;
        try {
            responseData = await response.json();
        } catch (e) {
            if (!response.ok) {
                console.error(`[Auth] 登录失败于 ${url}: ${response.status} ${response.statusText}. 响应体非有效 JSON。`);
                throw new Error(`登录失败: ${response.status} ${response.statusText}. 服务器响应格式错误。`);
            } else {
                console.warn(`[Auth] 来自 ${url} 的登录响应成功 (${response.status}) 但响应体非有效 JSON。`);
                return { status: response.status, message: "操作可能成功，但服务器响应格式错误" };
            }
        }

        if (!response.ok) {
            const errorMessage = responseData?.error || `HTTP ${response.status} ${response.statusText}`;
            console.error(`[Auth] 用户 '${username}' 登录失败于 ${url}:`, errorMessage);
            const error = new Error(`登录失败: ${errorMessage}`);
            error.response = responseData;
            error.status = response.status;
            throw error;
        }

        console.log(`[Auth] 用户 '${username}' 登录成功:`, responseData);
        // 登录成功后，浏览器会自动处理 Set-Cookie 头
        return responseData;

    } catch (error) {
        if (!error.status) {
            console.error(`[Auth] ${url} 登录期间网络或处理错误:`, error);
        }
        throw error;
    }
}

/**
 * 用户登出。
 * @returns {Promise<object>} 后端返回的 JSON 对象 (例如: { message: "登出成功" })。
 * @throws {Error} 如果网络请求失败或服务器返回错误状态码。
 */
async function logout() {
    const url = `${API_BASE_URL}/api/auth/logout`;

    console.log(`[Auth] 尝试从 ${url} 登出`);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                // 'Content-Type': 'application/json', // 通常登出不需要，除非后端要求
                'Accept': 'application/json'
            },
            // body: JSON.stringify({}) // 通常登出不需要 body
            // 注意：浏览器会自动发送会话 cookie
        });

        let responseData;
        try {
            responseData = await response.json();
        } catch (e) {
            if (!response.ok) {
                console.error(`[Auth] 登出失败于 ${url}: ${response.status} ${response.statusText}. 响应体非有效 JSON。`);
                throw new Error(`登出失败: ${response.status} ${response.statusText}. 服务器响应格式错误。`);
            } else {
                // 登出成功 (200 OK) 但响应体非 JSON (例如纯文本)
                const textResponse = await response.text().catch(() => "未知响应");
                console.log(`[Auth] 从 ${url} 登出成功. 响应为文本: ${textResponse}`);
                return { message: textResponse, status: response.status };
            }
        }

        if (!response.ok) {
            const errorMessage = responseData?.error || `HTTP ${response.status} ${response.statusText}`;
            console.error(`[Auth] 登出失败于 ${url}:`, errorMessage);
            const error = new Error(`登出失败: ${errorMessage}`);
            error.response = responseData;
            error.status = response.status;
            throw error;
        }

        console.log(`[Auth] 登出成功:`, responseData);
        // 登出成功后，浏览器会自动处理 Set-Cookie 头 (通常是删除或过期会话 cookie)
        return responseData;

    } catch (error) {
        if (!error.status) {
            console.error(`[Auth] ${url} 登出期间网络或处理错误:`, error);
        }
        throw error;
    }
}

/**
 * 检查当前用户的登录状态。
 * @returns {Promise<object>} 后端返回的 JSON 对象 (例如: { logged_in: true, user: { ... } } 或 { logged_in: false })。
 * @throws {Error} 如果网络请求失败或服务器返回错误状态码。
 */
async function checkLoginStatus() {
    const url = `${API_BASE_URL}/api/auth/status`;
    console.log(`[Auth] 检查登录状态于 ${url}`);

    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
            // GET 请求，浏览器自动发送 cookie
        });

        let responseData;
        try {
            responseData = await response.json();
        } catch (e) {
            if (!response.ok) {
                console.error(`[Auth] 检查状态失败于 ${url}: ${response.status} ${response.statusText}. 响应体非有效 JSON。`);
                throw new Error(`检查状态失败: ${response.status} ${response.statusText}. 服务器响应格式错误。`);
            } else {
                console.warn(`[Auth] 来自 ${url} 的状态检查响应成功 (${response.status}) 但响应体非有效 JSON。`);
                return { status: response.status, message: "操作可能成功，但服务器响应格式错误" };
            }
        }

        if (!response.ok) {
            // /status 理论上不应轻易失败，除非服务器内部错误
            const errorMessage = responseData?.error || `HTTP ${response.status} ${response.statusText}`;
            console.error(`[Auth] 检查登录状态失败于 ${url}:`, errorMessage);
            const error = new Error(`检查登录状态失败: ${errorMessage}`);
            error.response = responseData;
            error.status = response.status;
            throw error;
        }

        console.log(`[Auth] 登录状态检查成功:`, responseData);
        return responseData;

    } catch (error) {
        if (!error.status) {
            console.error(`[Auth] ${url} 状态检查期间网络或处理错误:`, error);
        }
        throw error;
    }
}

// ==================================================
// 推理相关函数 (Inference)
// ==================================================

/**
 * 发送命令和参数到 /api/Inference 端点 (POST)。
 * 用于不需要上传文件的操作，如加载/弹出模型、清除上传、开始检测等。
 * @param {string} command - 要执行的命令 (例如: 'LoadModel', 'Start', 'OpenThePath')。
 * @param {object} [data={}] - 伴随命令发送的可选数据 (例如: { model: 'yolov8n.pt' } 用于 LoadModel)。
 * @returns {Promise<object>} 后端返回的 JSON 对象。
 * @throws {Error} 如果网络请求失败或服务器返回非成功状态码。
 */
async function sendInferenceCommand(command, data = {}) {
    const url = `${API_BASE_URL}/api/Inference`;
    const payload = {
        "command": command,
        "data": data
    };

    console.log(`[Request] 发送命令至 ${url}:`, payload);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            let errorBody = '无错误详情';
            try {
                errorBody = await response.text();
            } catch (e) { /* 忽略读取错误详情时的错误 */ }
            console.error(`[Request] 来自 ${url} 的错误响应: ${response.status} ${response.statusText}`, errorBody);
            throw new Error(`服务器错误: ${response.status} ${response.statusText}. ${errorBody}`);
        }

        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
            const responseData = await response.json();
            console.log(`[Request] 来自 ${url} 的成功响应:`, responseData);
            return responseData;
        } else {
            if (response.status === 204) { // No Content
                console.log(`[Request] 来自 ${url} 的成功响应: 204 No Content`);
                return { status: 204, message: '操作成功，无内容返回' };
            }
            // 若非 JSON 也非 204，尝试读取文本
            const responseText = await response.text();
            console.warn(`[Request] 从 ${url} 收到非 JSON 响应: Status ${response.status}`, responseText);
            throw new Error(`服务器返回了非预期的格式: ${contentType || '未知'} (Status: ${response.status})`);
        }

    } catch (error) {
        console.error(`[Request] ${url} 网络或处理错误:`, error);
        throw error;
    }
}

/**
 * 上传单个文件或文件数组到 /api/Inference 端点 (POST)。
 * 用于上传图片、图集或配置文件。
 * @param {string} command - 指示上传类型的命令 (例如: 'UploadPicture', 'UploadAtlas', 'UploadConfig')。
 * @param {File|File[]} filesOrFile - 要上传的单个文件对象或文件对象数组。
 * @param {object} [additionalData={}] - 可选的附加数据，会一并发送。
 * @returns {Promise<object>} 后端返回的 JSON 对象。
 * @throws {Error} 如果网络请求失败、服务器返回非成功状态码, 或未提供有效文件。
 */
async function uploadInferenceFile(command, filesOrFile, additionalData = {}) {
    const url = `${API_BASE_URL}/api/Inference`;
    const formData = new FormData();

    formData.append('command', command);

    const files = Array.isArray(filesOrFile) ? filesOrFile : [filesOrFile];

    if (files.length === 0 || !files[0]) {
        console.error('[Request] 没有提供要上传的文件。');
        throw new Error('没有提供要上传的文件。');
    }

    let validFileCount = 0;
    // 关键假设: 后端期望多个文件都使用相同的字段名 'file'
    files.forEach((file, index) => {
        if (file instanceof File) {
            formData.append('file', file, file.name); // 使用相同的 key 'file'
            validFileCount++;
        } else {
            console.warn(`[Request] 提供的项目非有效文件对象，已跳过索引 ${index}:`, file);
        }
    });

    if (validFileCount === 0) {
        console.error('[Request] 没有有效的文件被添加到 FormData。');
        throw new Error('没有有效的文件可上传。');
    }

    for (const key in additionalData) {
        if (Object.prototype.hasOwnProperty.call(additionalData, key)) {
            formData.append(key, additionalData[key]);
        }
    }

    const fileNames = files.filter(f => f instanceof File).map(f => f.name).join(', ');
    console.log(`[Request] 上传 ${validFileCount} 个文件至 ${url}，命令: ${command}, 文件名: ${fileNames}`);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                // 对于 FormData，浏览器会自动设置 Content-Type
                'Accept': 'application/json' // 期望服务器返回 JSON
            },
            body: formData
        });

        if (!response.ok) {
            let errorBody = '无错误详情';
            try {
                errorBody = await response.text();
            } catch (e) { /* 忽略读取错误详情时的错误 */ }
            console.error(`[Request] 上传时 ${url} 返回错误: ${response.status} ${response.statusText}`, errorBody);
            const uploadType = validFileCount > 1 ? '图集' : '文件';
            throw new Error(`${uploadType}上传服务器错误: ${response.status} ${response.statusText}. ${errorBody}`);
        }

        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
            const responseData = await response.json();
            console.log(`[Request] 上传后 ${url} 返回成功响应:`, responseData);
            return responseData;
        } else {
            if (response.status === 204) { // No Content
                console.log(`[Request] 上传后 ${url} 返回成功响应: 204 No Content`);
                return { status: 204, message: '文件上传成功，无内容返回' };
            }
            const responseText = await response.text();
            console.warn(`[Request] 上传后从 ${url} 收到非 JSON 响应: Status ${response.status}`, responseText);
            throw new Error(`文件上传后服务器返回了非预期的格式: ${contentType || '未知'} (Status: ${response.status})`);
        }

    } catch (error) {
        console.error(`[Request] 上传时 ${url} 网络或处理错误:`, error);
        throw error;
    }
}

/**
 * 从 /api/GetModels 端点获取模型列表或相关配置信息 (GET)。
 * @returns {Promise<object>} 后端返回的 JSON 配置/状态对象。
 * @throws {Error} 如果网络请求失败或服务器返回非成功状态码。
 */
async function getModels() {
    const url = `${API_BASE_URL}/api/GetModels`;
    console.log(`[Request] 从 ${url} 获取配置`);

    try {
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });

        if (!response.ok) {
            let errorBody = '无错误详情';
            try {
                errorBody = await response.text();
            } catch (e) { /* 忽略读取错误详情时的错误 */ }
            console.error(`[Request] 来自 ${url} 的错误响应: ${response.status} ${response.statusText}`, errorBody);
            throw new Error(`获取配置服务器错误: ${response.status} ${response.statusText}. ${errorBody}`);
        }

        const contentType = response.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
            const responseData = await response.json();
            console.log(`[Request] 来自 ${url} 的成功响应:`, responseData);
            return responseData;
        } else {
            const responseText = await response.text();
            console.warn(`[Request] 从 ${url} 收到非 JSON 响应: Status ${response.status}`, responseText);
            throw new Error(`获取配置时服务器返回了非预期的格式: ${contentType || '未知'} (Status: ${response.status})`);
        }

    } catch (error) {
        console.error(`[Request] ${url} 网络或处理错误:`, error);
        throw error;
    }
}

// ==================================================
// 微调任务相关函数 (Finetune)
// ==================================================

/**
 * 创建一个新的微调任务。
 * @param {FormData} formData 包含任务配置和文件的 FormData 对象。
 *                            后端期望字段: task_name, base_model_pt (或 preset_model_name), dataset_zip, dataset_yaml, training_params (JSON字符串)。
 * @returns {Promise<object>} 包含 task_id 和 message 的对象。
 * @throws {Error} 如果请求失败或服务器返回错误。
 */
async function createFinetuneTask(formData) {
    const response = await fetch('/api/finetune/tasks', {
        method: 'POST',
        body: formData
        // 对于 FormData，浏览器会自动设置 Content-Type
        // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
    });

    const responseData = await response.json();
    if (!response.ok) {
        const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
        console.error('创建微调任务错误:', errorMessage, responseData);
        throw new Error(errorMessage);
    }
    return responseData; // 应包含 { message: "...", task_id: "..." }
}

/**
 * 获取当前用户的所有微调任务列表。
 * @returns {Promise<Array<object>>} 任务对象数组。
 * @throws {Error} 如果请求失败或服务器返回错误。
 */
async function getFinetuneTasks() {
    const response = await fetch('/api/finetune/tasks', {
        method: 'GET'
        // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
    });

    if (!response.ok) {
        let errorMessage = `HTTP 错误! 状态: ${response.status}`;
        try {
            const errorData = await response.json();
            errorMessage = errorData.error || errorMessage;
        } catch (e) { /* 无法解析 JSON 错误体，使用默认 HTTP 错误 */ }
        console.error('获取微调任务列表错误:', errorMessage);
        throw new Error(errorMessage);
    }
    return await response.json(); // 应为任务数组
}

/**
 * 获取指定任务 ID 的详细信息。
 * @param {string} taskId 任务的唯一标识符。
 * @returns {Promise<object>} 任务详情对象。
 * @throws {Error} 如果请求失败、服务器返回错误或 taskId 为空。
 */
async function getFinetuneTaskDetails(taskId) {
    if (!taskId) {
        throw new Error("获取任务详情需要任务 ID。");
    }
    const response = await fetch(`/api/finetune/tasks/${taskId}`, {
        method: 'GET'
        // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
    });

    const responseData = await response.json();
    if (!response.ok) {
        const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
        console.error(`获取任务 ${taskId} 详情错误:`, errorMessage, responseData);
        throw new Error(errorMessage);
    }
    return responseData;
}

/**
 * 获取指定任务 ID 的训练日志。
 * @param {string} taskId 任务的唯一标识符。
 * @param {number|null} [tailLines=null] 可选，获取日志末尾的指定行数。若为 null，则获取完整日志。
 * @returns {Promise<object>} 包含 task_id 和 logs (字符串) 的对象。
 * @throws {Error} 如果请求失败、服务器返回错误或 taskId 为空。
 */
async function getFinetuneTaskLogs(taskId, tailLines = null) {
    if (!taskId) {
        throw new Error("获取任务日志需要任务 ID。");
    }
    let url = `/api/finetune/tasks/${taskId}/logs`;
    if (tailLines !== null && Number.isInteger(tailLines) && tailLines > 0) {
        url += `?tail=${tailLines}`;
    }

    const response = await fetch(url, {
        method: 'GET'
        // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
    });

    const responseData = await response.json();
    if (!response.ok) {
        // 后端日志接口即使404也可能返回JSON {"error": "...", "logs": ""}，优先使用 responseData.error
        const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
        console.error(`获取任务 ${taskId} 日志错误:`, errorMessage, responseData);
        throw new Error(errorMessage);
    }
    // 即使响应200 OK，也检查后端是否在 responseData 中明确指出了错误
    if (responseData.error && response.status !== 404) { // 404时 error 是预期的
        console.warn(`任务 ${taskId} 日志获取成功 (200 OK)，但 API 返回错误信息:`, responseData.error);
    }
    return responseData; // 应包含 { task_id: "...", logs: "..." }
}

/**
 * 请求下载指定任务 ID 的输出文件（例如模型）。
 * 此函数返回原始的 Response 对象，调用者需处理它以触发浏览器下载。
 * @param {string} taskId 任务的唯一标识符。
 * @returns {Promise<Response>} Fetch API 的 Response 对象。
 * @throws {Error} 如果请求初始化失败、服务器返回明确的 JSON 错误 (例如 404 时) 或 taskId 为空。
 */
async function downloadFinetuneTaskOutput(taskId) {
    if (!taskId) {
        throw new Error("下载任务输出需要任务 ID。");
    }
    const response = await fetch(`/api/finetune/tasks/${taskId}/output`, {
        method: 'GET'
        // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
    });

    if (!response.ok) {
        // 尝试解析JSON错误，因为后端在404时可能返回JSON
        try {
            const errorData = await response.json();
            const errorMessage = errorData.error || `HTTP 错误! 状态: ${response.status}`;
            console.error(`准备下载任务 ${taskId} 输出错误:`, errorMessage, errorData);
            throw new Error(errorMessage);
        } catch (e) {
            // 若非JSON错误，则抛出通用HTTP错误
            const errorMessage = `HTTP 错误! 状态: ${response.status}`;
            console.error(`准备下载任务 ${taskId} 输出错误:`, errorMessage);
            throw new Error(errorMessage);
        }
    }
    // 对于成功的下载请求 (response.ok 为 true)，直接返回 response 对象
    return response;
}

/**
 * 请求取消指定任务 ID 的微调任务。
 * @param {string} taskId 任务的唯一标识符。
 * @returns {Promise<object>} 包含 message 和 task_id 的对象。
 * @throws {Error} 如果请求失败、服务器返回错误或 taskId 为空。
 */
async function cancelFinetuneTask(taskId) {
    if (!taskId) {
        throw new Error("取消任务需要任务 ID。");
    }
    const response = await fetch(`/api/finetune/tasks/${taskId}/cancel`, {
        method: 'POST' // 后端定义为 POST
        // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED', 'Content-Type': 'application/json' },
        // body: JSON.stringify({}) // 如果API需要空JSON对象作为body
    });

    const responseData = await response.json();
    if (!response.ok) {
        const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
        console.error(`取消任务 ${taskId} 错误:`, errorMessage, responseData);
        throw new Error(errorMessage);
    }
    return responseData; // 应包含 { message: "...", task_id: "..." }
}

/**
 * 删除指定任务 ID 的微调任务。
 * @param {string} taskId 任务的唯一标识符。
 * @returns {Promise<object>} 包含 message 和 task_id 的对象。
 * @throws {Error} 如果请求失败、服务器返回错误或 taskId 为空。
 */
async function deleteFinetuneTask(taskId) {
    if (!taskId) {
        throw new Error("删除任务需要任务 ID。");
    }
    const response = await fetch(`/api/finetune/tasks/${taskId}/delete`, {
        method: 'DELETE'
        // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
    });

    // DELETE 请求成功时可能不返回 body，或返回 JSON，需灵活处理
    if (!response.ok) {
        try {
            const errorData = await response.json();
            const errorMessage = errorData.error || `HTTP 错误! 状态: ${response.status}`;
            console.error(`删除任务 ${taskId} 错误:`, errorMessage, errorData);
            throw new Error(errorMessage);
        } catch (e) {
            // 若响应体非JSON或为空
            const errorMessage = `HTTP 错误! 状态: ${response.status}`;
            console.error(`删除任务 ${taskId} 错误:`, errorMessage);
            throw new Error(errorMessage);
        }
    }

    // 尝试解析JSON，若后端在成功时返回JSON
    try {
        const responseData = await response.json();
        return responseData; // 应包含 { message: "...", task_id: "..." }
    } catch (e) {
        // 若成功但无JSON body (例如 204 No Content)
        if (response.status === 200 || response.status === 204) {
            return { message: `任务 ${taskId} 已成功删除 (或请求已接受)。`, task_id: taskId };
        }
        // 若非预期的无内容成功
        console.warn(`任务 ${taskId} 删除响应成功，但响应体非有效JSON且状态为 ${response.status}。`);
        throw new Error(`任务 ${taskId} 删除成功但响应格式非预期。状态: ${response.status}`);
    }
}

// ==================================================
// 验证任务相关函数 (Validate)
// ==================================================

/**
 * 创建一个新的验证任务。
 * 前端仅支持文件上传方式。
 * @param {FormData} formData 包含任务配置和文件的 FormData 对象。
 *                            后端期望字段: task_name, model_source_type='upload', model_file_upload,
 *                                         dataset_source_type='upload', dataset_zip_upload, dataset_yaml_upload,
 *                                         validation_params (JSON字符串)。
 * @returns {Promise<object>} 包含 task_id 和 message 的对象。
 * @throws {Error} 如果请求失败或服务器返回错误。
 */
async function createValidateTask(formData) {
    const url = `${API_BASE_URL}/api/validate/tasks`; // API 蓝图前缀 /api/validate
    console.log(`[Validate] 尝试创建验证任务至 ${url}`);

    try {
        const response = await fetch(url, {
            method: 'POST',
            body: formData
            // 对于 FormData，浏览器会自动设置 Content-Type
            // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
        });

        const responseData = await response.json();
        if (!response.ok) {
            const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
            console.error('[Validate] 创建验证任务错误:', errorMessage, responseData);
            throw new Error(errorMessage);
        }
        console.log('[Validate] 验证任务创建成功:', responseData);
        return responseData; // 应包含 { message: "...", task_id: "..." }
    } catch (error) {
        console.error(`[Validate] ${url} 创建任务期间网络或处理错误:`, error);
        throw error;
    }
}

/**
 * 获取当前用户的所有验证任务列表。
 * @returns {Promise<Array<object>>} 任务对象数组。
 * @throws {Error} 如果请求失败或服务器返回错误。
 */
async function getValidateTasks() {
    const url = `${API_BASE_URL}/api/validate/tasks`;
    console.log(`[Validate] 尝试从 ${url} 获取验证任务列表`);

    try {
        const response = await fetch(url, {
            method: 'GET'
            // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
        });

        if (!response.ok) {
            let errorMessage = `HTTP 错误! 状态: ${response.status}`;
            try {
                const errorData = await response.json();
                errorMessage = errorData.error || errorMessage;
            } catch (e) { /* 无法解析 JSON 错误体，使用默认 HTTP 错误 */ }
            console.error('[Validate] 获取验证任务列表错误:', errorMessage);
            throw new Error(errorMessage);
        }
        const tasks = await response.json();
        console.log('[Validate] 验证任务列表获取成功:', tasks);
        return tasks; // 应为任务数组
    } catch (error) {
        console.error(`[Validate] ${url} 获取任务列表期间网络或处理错误:`, error);
        throw error;
    }
}

/**
 * 获取指定验证任务 ID 的详细信息。
 * @param {string} taskId 任务的唯一标识符。
 * @returns {Promise<object>} 任务详情对象。
 * @throws {Error} 如果请求失败、服务器返回错误或 taskId 为空。
 */
async function getValidateTaskDetails(taskId) {
    if (!taskId) {
        console.error("[Validate] 获取任务详情需要任务 ID。");
        throw new Error("获取验证任务详情需要任务 ID。");
    }
    const url = `${API_BASE_URL}/api/validate/tasks/${taskId}`;
    console.log(`[Validate] 尝试从 ${url} 获取任务 ${taskId} 的详情`);

    try {
        const response = await fetch(url, {
            method: 'GET'
            // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
        });

        const responseData = await response.json();
        if (!response.ok) {
            const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
            console.error(`[Validate] 获取任务 ${taskId} 详情错误:`, errorMessage, responseData);
            throw new Error(errorMessage);
        }
        console.log(`[Validate] 任务 ${taskId} 详情获取成功:`, responseData);
        return responseData;
    } catch (error) {
        console.error(`[Validate] ${url} 获取任务详情期间网络或处理错误:`, error);
        throw error;
    }
}

/**
 * 获取指定验证任务 ID 的日志。
 * @param {string} taskId 任务的唯一标识符。
 * @param {number|null} [tailLines=null] 可选，获取日志末尾的指定行数。若为 null，则获取完整日志。
 * @returns {Promise<object>} 包含 task_id 和 logs (字符串) 的对象。
 * @throws {Error} 如果请求失败、服务器返回错误或 taskId 为空。
 */
async function getValidateTaskLogs(taskId, tailLines = null) {
    if (!taskId) {
        console.error("[Validate] 获取任务日志需要任务 ID。");
        throw new Error("获取验证任务日志需要任务 ID。");
    }
    let url = `${API_BASE_URL}/api/validate/tasks/${taskId}/logs`;
    if (tailLines !== null && Number.isInteger(tailLines) && tailLines > 0) {
        url += `?tail=${tailLines}`;
    }
    console.log(`[Validate] 尝试从 ${url} 获取任务 ${taskId} 的日志`);

    try {
        const response = await fetch(url, {
            method: 'GET'
            // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
        });

        const responseData = await response.json();
        if (!response.ok) {
            const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
            console.error(`[Validate] 获取任务 ${taskId} 日志错误:`, errorMessage, responseData);
            throw new Error(errorMessage);
        }
        if (responseData.error && response.status !== 404) {
            console.warn(`[Validate] 任务 ${taskId} 日志获取成功 (200 OK)，但 API 返回错误信息:`, responseData.error);
        }
        console.log(`[Validate] 任务 ${taskId} 日志获取成功:`, responseData);
        return responseData; // 应包含 { task_id: "...", logs: "..." }
    } catch (error) {
        console.error(`[Validate] ${url} 获取任务日志期间网络或处理错误:`, error);
        throw error;
    }
}

/**
 * 请求下载指定验证任务 ID 的输出文件（结果归档）。
 * 此函数返回原始的 Response 对象，调用者需处理它以触发浏览器下载。
 * @param {string} taskId 任务的唯一标识符。
 * @returns {Promise<Response>} Fetch API 的 Response 对象。
 * @throws {Error} 如果请求初始化失败、服务器返回明确的 JSON 错误 (例如 404 时) 或 taskId 为空。
 */
async function downloadValidateTaskOutput(taskId) {
    if (!taskId) {
        console.error("[Validate] 下载任务输出需要任务 ID。");
        throw new Error("下载验证任务输出需要任务 ID。");
    }
    const url = `${API_BASE_URL}/api/validate/tasks/${taskId}/output`;
    console.log(`[Validate] 尝试从 ${url} 下载任务 ${taskId} 的输出`);

    try {
        const response = await fetch(url, {
            method: 'GET'
            // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
        });

        if (!response.ok) {
            try {
                const errorData = await response.json();
                const errorMessage = errorData.error || `HTTP 错误! 状态: ${response.status}`;
                console.error(`[Validate] 准备下载任务 ${taskId} 输出错误:`, errorMessage, errorData);
                throw new Error(errorMessage);
            } catch (e) {
                const errorMessage = `HTTP 错误! 状态: ${response.status}`;
                console.error(`[Validate] 准备下载任务 ${taskId} 输出错误 (非JSON响应):`, errorMessage);
                throw new Error(errorMessage);
            }
        }
        console.log(`[Validate] 任务 ${taskId} 输出下载请求成功, 准备流式传输。`);
        return response; // 对于成功的下载请求 (response.ok 为 true)，直接返回 response 对象
    } catch (error) {
        // 这个 catch 主要捕获 fetch 本身的网络错误，或者上面显式抛出的 Error
        console.error(`[Validate] ${url} 下载任务输出期间网络或处理错误:`, error);
        throw error;
    }
}

/**
 * 请求取消指定验证任务 ID 的任务。
 * @param {string} taskId 任务的唯一标识符。
 * @returns {Promise<object>} 包含 message 和 task_id 的对象。
 * @throws {Error} 如果请求失败、服务器返回错误或 taskId 为空。
 */
async function cancelValidateTask(taskId) {
    if (!taskId) {
        console.error("[Validate] 取消任务需要任务 ID。");
        throw new Error("取消验证任务需要任务 ID。");
    }
    const url = `${API_BASE_URL}/api/validate/tasks/${taskId}/cancel`;
    console.log(`[Validate] 尝试从 ${url} 取消任务 ${taskId}`);

    try {
        const response = await fetch(url, {
            method: 'POST'
            // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED', 'Content-Type': 'application/json' },
            // body: JSON.stringify({}) // 如果API需要空JSON对象作为body
        });

        const responseData = await response.json();
        if (!response.ok) {
            const errorMessage = responseData.error || `HTTP 错误! 状态: ${response.status}`;
            console.error(`[Validate] 取消任务 ${taskId} 错误:`, errorMessage, responseData);
            throw new Error(errorMessage);
        }
        console.log(`[Validate] 取消任务 ${taskId} 请求成功:`, responseData);
        return responseData; // 应包含 { message: "...", task_id: "..." }
    } catch (error) {
        console.error(`[Validate] ${url} 取消任务期间网络或处理错误:`, error);
        throw error;
    }
}

/**
 * 删除指定验证任务 ID 的任务。
 * @param {string} taskId 任务的唯一标识符。
 * @returns {Promise<object>} 包含 message 和 task_id 的对象。
 * @throws {Error} 如果请求失败、服务器返回错误或 taskId 为空。
 */
async function deleteValidateTask(taskId) {
    if (!taskId) {
        console.error("[Validate] 删除任务需要任务 ID。");
        throw new Error("删除验证任务需要任务 ID。");
    }
    const url = `${API_BASE_URL}/api/validate/tasks/${taskId}/delete`;
    console.log(`[Validate] 尝试从 ${url} 删除任务 ${taskId}`);

    try {
        const response = await fetch(url, {
            method: 'DELETE'
            // headers: { 'Authorization': 'Bearer YOUR_TOKEN_IF_NEEDED' }
        });

        if (!response.ok) {
            try {
                const errorData = await response.json();
                const errorMessage = errorData.error || `HTTP 错误! 状态: ${response.status}`;
                console.error(`[Validate] 删除任务 ${taskId} 错误:`, errorMessage, errorData);
                throw new Error(errorMessage);
            } catch (e) {
                const errorMessage = `HTTP 错误! 状态: ${response.status}`;
                console.error(`[Validate] 删除任务 ${taskId} 错误 (非JSON响应):`, errorMessage);
                throw new Error(errorMessage);
            }
        }

        try {
            const responseData = await response.json();
            console.log(`[Validate] 删除任务 ${taskId} 成功:`, responseData);
            return responseData;
        } catch (e) {
            if (response.status === 200 || response.status === 204) {
                 console.log(`[Validate] 任务 ${taskId} 已成功删除 (状态 ${response.status})。`);
                return { message: `任务 ${taskId} 已成功删除。`, task_id: taskId, status: response.status };
            }
            console.warn(`[Validate] 任务 ${taskId} 删除响应成功，但响应体非有效JSON且状态为 ${response.status}。`);
            throw new Error(`任务 ${taskId} 删除成功但响应格式非预期。状态: ${response.status}`);
        }
    } catch (error) {
        console.error(`[Validate] ${url} 删除任务期间网络或处理错误:`, error);
        throw error;
    }
}