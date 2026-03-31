// public/clipboard_fallback.js
// 针对 HTTP 环境下 Clipboard API 被浏览器禁用的降级处理方案

// 1. 补齐 ClipboardItem 定义，防止运行时 Chainlit 抛出 ReferenceError
if (typeof window.ClipboardItem === 'undefined') {
    window.ClipboardItem = class ClipboardItem {
        constructor(data) {
            this.data = data;
        }
    };
}

// 2. 确保 navigator.clipboard 对象存在
if (!navigator.clipboard) {
    navigator.clipboard = {};
}

// 3. 重写/劫持 write 方法，使用传统的 document.execCommand('copy') 实现复制
// 即使在非 HTTPS 环境下，这段代码也能强制执行文本复制
if (!navigator.clipboard.write || window.location.protocol !== 'https:') {
    navigator.clipboard.write = async function (clipboardItems) {
        try {
            for (const item of clipboardItems) {
                // Chainlit 前端默认会将文本封装在 'text/plain' 格式的 Blob 对象中
                if (item.data && item.data['text/plain']) {
                    const blob = item.data['text/plain'];
                    // 将 Blob 异步解析为真实的纯文本字符串
                    const text = await blob.text();
                    
                    // 创建一个隐藏的 textarea 元素用于承载文本
                    const textArea = document.createElement("textarea");
                    textArea.value = text;
                    
                    // 将 textarea 移出屏幕可视区域，避免页面发生抖动或滚动干扰用户体验
                    textArea.style.position = "fixed";
                    textArea.style.left = "-999999px";
                    textArea.style.top = "-999999px";
                    
                    // 挂载、聚焦并全选文本
                    document.body.appendChild(textArea);
                    textArea.focus();
                    textArea.select();
                    
                    // 执行传统复制命令
                    const successful = document.execCommand('copy');
                    
                    // 复制完成后清理临时节点
                    document.body.removeChild(textArea);
                    
                    if (!successful) {
                        console.error('【降级复制失败】浏览器拒绝了 execCommand 调用');
                    }
                }
            }
        } catch (err) {
            console.error('【降级复制报错】处理 ClipboardItem 异常:', err);
        }
    };
}