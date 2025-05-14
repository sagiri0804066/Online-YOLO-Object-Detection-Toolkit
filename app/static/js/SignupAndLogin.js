document.addEventListener('DOMContentLoaded', () => {
    const loginSubmitButton = document.getElementById('login-submit-button');
    const signupSubmitButton = document.getElementById('signup-submit-button');
    const loginUsernameInput = document.getElementById('login-username');
    const loginPasswordInput = document.getElementById('login-password');
    const signupUsernameInput = document.getElementById('signup-username');
    const signupPasswordInput = document.getElementById('signup-password');
    const signupConfirmPasswordInput = document.getElementById('signup-confirm-password');

    // --- 登录提交 ---
    if (loginSubmitButton && loginUsernameInput && loginPasswordInput) {
        loginSubmitButton.addEventListener('click', async () => {
            const username = loginUsernameInput.value.trim();
            const password = loginPasswordInput.value;

            if (!username || !password) {
                showNotification(1, '请输入用户名和密码！');
                return;
            }

            loginSubmitButton.disabled = true;
            loginSubmitButton.textContent = '登录中...';

            try {
                const result = await login(username, password);

                // showNotification(2, result.message || '登录成功！');
                //console.log("登录成功，用户信息:", result.user);

                //if (typeof closeContentView === 'function') {
                    //closeContentView();
                //} else {
                    //console.warn("未找到 closeContentView 函数");
                //}
                //updateUIAfterLogin(result.user);

                location.reload();

            } catch (error) {
                showNotification(0, `登录失败: ${error.message}`);
                console.error("登录错误:", error);
            } finally {
                loginSubmitButton.disabled = false;
                loginSubmitButton.textContent = '登录账号';
            }
        });
    } else {
         console.error("未能找到登录表单的必要元素！");
    }

    // --- 注册提交 ---
    if (signupSubmitButton && signupUsernameInput && signupPasswordInput && signupConfirmPasswordInput) {
        signupSubmitButton.addEventListener('click', async () => {
            const username = signupUsernameInput.value.trim();
            const password = signupPasswordInput.value;
            const confirmPassword = signupConfirmPasswordInput.value;

            if (!username || !password || !confirmPassword) {
                showNotification(1, '请填写所有注册字段！');
                return;
            }

            if (password !== confirmPassword) {
                showNotification(1, '两次输入的密码不一致！');
                return;
            }

            if (password.length < 8) {
                 showNotification(1, '密码长度至少需要8位！');
                 return;
            }

            signupSubmitButton.disabled = true;
            signupSubmitButton.textContent = '注册中...';

            try {
                const result = await register(username, password);

                showNotification(2, result.message || '注册成功！用户ID:', result.user_id);
                console.log("注册成功，用户ID:", result.user_id);

                if (typeof closeContentView === 'function') {
                    closeContentView();
                }
                openAuthView('login-content');
                signupUsernameInput.value = '';
                signupPasswordInput.value = '';
                signupConfirmPasswordInput.value = '';

            } catch (error) {
                showNotification(0, `注册失败: ${error.message}`);
                console.error("注册错误:", error);
            } finally {
                signupSubmitButton.disabled = false;
                signupSubmitButton.textContent = '注册账号';
            }
        });
    } else {
        console.error("未能找到注册表单的必要元素！");
    }

    // --- 页面加载时检查登录状态 ---
    checkInitialLoginState();

}); // DOMContentLoaded 结束

// --- UI 更新和状态检查逻辑 ---

/**
 * 页面加载时检查用户登录状态并更新 UI
 */
async function checkInitialLoginState() {
    console.log("检查初始登录状态...");
    try {
        const status = await checkLoginStatus();
        if (status.logged_in) {
            console.log("用户已登录:", status.user);
            updateUIAfterLogin(status.user);
        } else {
            console.log("用户未登录");
            updateUIAfterLogout();
        }
    } catch (error) {
        console.error("检查登录状态时出错:", error);
        showNotification(0, `无法检查登录状态: ${error.message}`);
        // 发生错误时，假定用户未登录
        updateUIAfterLogout();
    }
}

/**
 * 更新 UI 以反映用户已登录的状态
 * @param {object} user
 */
function updateUIAfterLogin(user) {
    const authLinks = document.querySelector('.auth-links');
    if (authLinks) {
        authLinks.innerHTML = `
            <span class="user-greeting">欢迎, ${user.username}!</span>
            <a href="#" id="logout-link">登出</a>
        `;
        const logoutLink = document.getElementById('logout-link');
        if (logoutLink) {
            logoutLink.addEventListener('click', handleLogoutClick);
        }
    }
}

/**
 * 更新 UI 以反映用户已登出的状态
 */
function updateUIAfterLogout() {
    const authLinks = document.querySelector('.auth-links');
    if (authLinks) {
        authLinks.innerHTML = `
            <a href="#" id="login-link">登录</a>
            <a href="#" id="signup-link">注册</a>
        `;
        // 重新绑定登录/注册链接事件 (因为 innerHTML 替换会移除旧监听器)
        const loginLink = document.getElementById('login-link');
        const signupLink = document.getElementById('signup-link');
        if (loginLink) {
            loginLink.addEventListener('click', (e) => {
                e.preventDefault();
                openAuthView('login-content');
            });
        }
        if (signupLink) {
            signupLink.addEventListener('click', (e) => {
                e.preventDefault();
                openAuthView('signup-content');
            });
        }
    }
}

/**
 * 处理登出点击事件
 */
async function handleLogoutClick(e) {
    e.preventDefault();
    console.log("尝试登出...");

    const confirmed = await showConfirmation("确定要登出吗？");
    if (!confirmed) return;

    try {
        const result = await logout(); // 调用 request.js 的函数
        showNotification(2, result.message || '已成功登出。');
        updateUIAfterLogout(); // 更新 UI 到未登录状态
    } catch (error) {
        showNotification(0, `登出时发生错误: ${error.message}`);
        console.error("登出错误:", error);
    }
}

const openAuthView = (sectionId) => {
     if (typeof openContentView !== 'function') {
         console.error("openContentView 函数未定义！");
         return;
     }
    console.log(`打开 Auth 面板: ${sectionId}`);
    const sectionName = sectionId.replace('-content', '');
    openContentView(sectionName);
};