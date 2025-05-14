import os
from waitress import serve
from app import create_app
from app.config import Config
import traceback

# --- 检查 waitress 是否支持 SSL ---
# Waitress 需要 pyOpenSSL 来直接处理 SSL
try:
    # 尝试导入 pyOpenSSL 来判断是否安装
    import OpenSSL
    waitress_can_handle_ssl = True
except ImportError:
    waitress_can_handle_ssl = False
    print("警告: 未找到 pyOpenSSL。Waitress 将无法直接处理 HTTPS。")
    print("如果需要 HTTPS，请运行 'pip install pyopenssl' 或 'pip install waitress[ssl]'。")
    print("或者，您可以使用 Nginx 等反向代理来处理 SSL。")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, 'config.yaml')

    # --- 配置加载 ---
    try:
        # 假设 Config 类在初始化时会加载配置，但可能不强制检查 SSL 文件存在性
        cfg = Config(config_path)
        print(f"从 {config_path} 加载配置...")
    except FileNotFoundError:
        print(f"错误: 配置文件 {config_path} 未找到！")
        exit(1)
    except Exception as e:
        # 捕获其他可能的配置加载错误
        print(f"加载配置时出错: {e}")
        traceback.print_exc()
        exit(1)

    # --- 创建 Flask 应用 ---
    try:
        app, app_config = create_app(cfg) # 使用加载的配置对象创建 app
        print("Flask 应用实例已创建。")
    except Exception as e:
        print(f"创建 Flask 应用时出错: {e}")
        traceback.print_exc()
        exit(1)

    # --- 获取监听地址和端口 ---
    host_config = app_config.SERVER_HOST # 从配置对象获取
    port = app_config.SERVER_PORT       # 从配置对象获取
    listen_host = "*" if host_config == "0.0.0.0" else host_config
    listen_str = f"{listen_host}:{port}"

    # --- 检查 HTTPS 配置 ---
    use_https = False
    cert_file_rel = app_config.CERT_FILE # 从配置对象获取证书相对路径
    key_file_rel = app_config.KEY_FILE   # 从配置对象获取密钥相对路径
    cert_file_abs = None
    key_file_abs = None

    if cert_file_rel and key_file_rel:
        cert_file_abs = os.path.join(base_dir, cert_file_rel)
        key_file_abs = os.path.join(base_dir, key_file_rel)
        print(f"检查 HTTPS 证书文件: {cert_file_abs}")
        print(f"检查 HTTPS 密钥文件: {key_file_abs}")
        if os.path.exists(cert_file_abs) and os.path.exists(key_file_abs):
            if waitress_can_handle_ssl:
                use_https = True
                print("找到有效的证书和密钥文件，且 pyOpenSSL 可用。将尝试启动 HTTPS 服务器。")
            else:
                print("找到有效的证书和密钥文件，但 pyOpenSSL 不可用。无法直接启动 HTTPS，将回退到 HTTP。")
        else:
            print("警告: 配置了证书或密钥文件，但文件不存在。将启动 HTTP 服务器。")
            if not os.path.exists(cert_file_abs): print(f"  - 文件未找到: {cert_file_abs}")
            if not os.path.exists(key_file_abs): print(f"  - 文件未找到: {key_file_abs}")
    else:
        print("未配置证书和密钥文件。将启动 HTTP 服务器。")

    # --- 准备 Waitress 参数 ---
    serve_args = {
        "app": app,
        "listen": listen_str,
        "threads": app.config.get('WAITRESS_THREADS', 4) # 可以从配置读取线程数，提供默认值
    }

    protocol = "http"
    if use_https:
        protocol = "https"
        serve_args['ssl_certificate'] = cert_file_abs
        serve_args['ssl_private_key'] = key_file_abs
        # Waitress 默认 url_scheme 是 http，当提供 ssl_* 参数时，
        # 它通常能正确处理，但明确设置可能更清晰（虽然文档没明确要求）
        # serve_args['url_scheme'] = 'https' # 一般不需要显式设置

    # --- 打印启动信息 ---
    print("-" * 30)
    print(f"启动服务器，监听 {protocol}://{host_config}:{port} (Waitress 使用: {listen_str})")
    print(f"工作线程数: {serve_args['threads']}")
    print(f"Session 类型: {app_config.SESSION_TYPE}") # 从配置对象获取
    if app_config.SESSION_TYPE == 'filesystem':
        session_dir_rel = app_config.SESSION_FILE_DIR # 从配置对象获取
        session_dir_abs = os.path.join(base_dir, session_dir_rel)
        if not os.path.exists(session_dir_abs):
             try:
                 os.makedirs(session_dir_abs)
                 print(f"创建 Session 目录: {session_dir_abs}")
             except OSError as e:
                 print(f"警告：无法创建 Session 目录 {session_dir_abs}: {e}")
        print(f"Session 目录: {session_dir_abs}")
    print("-" * 30)

    # --- 使用 Waitress 启动服务器 ---
    try:
        serve(**serve_args) # 使用解包的参数字典启动 serve
    except ImportError as e:
         # 捕获可能的 OpenSSL 导入错误（虽然前面检查过，以防万一）
         print(f"启动 Waitress 时发生导入错误（可能是缺少 pyOpenSSL）: {e}")
         traceback.print_exc()
         exit(1)
    except OSError as e:
         # 捕获端口占用等 OS 错误
         if "Address already in use" in str(e):
             print(f"错误: 端口 {port} 已被占用。请检查是否有其他程序在使用该端口。")
         else:
             print(f"启动 Waitress 时发生 OS 错误: {e}")
             traceback.print_exc()
         exit(1)
    except Exception as e:
        print(f"启动 Waitress 服务器失败: {e}")
        traceback.print_exc()
        exit(1)