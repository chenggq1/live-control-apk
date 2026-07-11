"""
网络工具模块 - 解决Android上SSL证书验证问题
"""
import os
import sys
import ssl
import traceback


def setup_ssl():
    """
    配置SSL证书路径，解决Android上requests/websocket-client找不到CA证书包的问题。
    如果找不到证书包，则禁用SSL验证（仅适用于公开数据抓取场景）。
    """
    # 尝试设置certifi证书路径
    try:
        import certifi
        ca_bundle = certifi.where()
        if ca_bundle and os.path.exists(ca_bundle):
            os.environ['SSL_CERT_FILE'] = ca_bundle
            os.environ['REQUESTS_CA_BUNDLE'] = ca_bundle
            os.environ['CURL_CA_BUNDLE'] = ca_bundle
            print(f"[SSL] CA证书包: {ca_bundle}")
            return True
    except Exception as e:
        print(f"[SSL] certifi不可用: {e}")

    # 尝试Android系统证书
    android_ca_paths = [
        '/system/etc/security/cacerts',
        '/etc/ssl/certs/ca-certificates.crt',
        '/data/misc/user/0/cacerts-added',
    ]
    for path in android_ca_paths:
        if os.path.exists(path):
            if os.path.isdir(path):
                # 合并目录下所有证书
                os.environ['SSL_CERT_DIR'] = path
                print(f"[SSL] 使用系统证书目录: {path}")
                return True
            else:
                os.environ['SSL_CERT_FILE'] = path
                print(f"[SSL] 使用系统证书文件: {path}")
                return True

    print("[SSL] 警告: 未找到CA证书包，将禁用SSL验证")
    return False


# 全局SSL验证标志
SSL_VERIFY = True


def init_network():
    """初始化网络配置，在应用启动时调用"""
    global SSL_VERIFY
    result = setup_ssl()
    SSL_VERIFY = result
    if not result:
        # 创建不验证SSL的上下文
        ssl._create_default_https_context = ssl._create_unverified_context
        print("[SSL] 已禁用SSL验证（降级模式）")
    return result


def get_request_kwargs():
    """获取requests请求的额外参数"""
    if not SSL_VERIFY:
        return {'verify': False}
    return {}


def get_ws_sslopt():
    """获取WebSocket的SSL选项"""
    if not SSL_VERIFY:
        return {'cert_reqs': ssl.CERT_NONE, 'check_hostname': False}
    return {}


def safe_request_get(url, headers=None, timeout=10, **kwargs):
    """安全的GET请求，SSL失败时自动降级"""
    import requests as req
    try:
        resp = req.get(url, headers=headers, timeout=timeout, verify=SSL_VERIFY, **kwargs)
        return resp
    except req.exceptions.SSLError:
        # SSL失败，降级为不验证
        print("[NET] SSL验证失败，降级为不验证模式")
        resp = req.get(url, headers=headers, timeout=timeout, verify=False, **kwargs)
        return resp
    except Exception as e:
        print(f"[NET] GET请求失败: {e}")
        raise


def safe_request_post(url, json=None, headers=None, cookies=None, timeout=10, **kwargs):
    """安全的POST请求，SSL失败时自动降级"""
    import requests as req
    try:
        resp = req.post(url, json=json, headers=headers, cookies=cookies,
                       timeout=timeout, verify=SSL_VERIFY, **kwargs)
        return resp
    except req.exceptions.SSLError:
        print("[NET] SSL验证失败，降级为不验证模式")
        resp = req.post(url, json=json, headers=headers, cookies=cookies,
                       timeout=timeout, verify=False, **kwargs)
        return resp
    except Exception as e:
        print(f"[NET] POST请求失败: {e}")
        raise
