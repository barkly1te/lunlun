// public/clipboard_fallback.js
// 为 HTTP 或受限浏览器补齐 Chainlit 复制按钮依赖的 Clipboard API。

if (typeof window.ClipboardItem === 'undefined') {
    window.ClipboardItem = class ClipboardItem {
        constructor(data) {
            this.data = data;
        }
    };
}

function ensureClipboardObject() {
    if (navigator.clipboard) {
        return navigator.clipboard;
    }

    const clipboardShim = {};
    Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: clipboardShim,
    });
    return clipboardShim;
}

function copyTextWithExecCommand(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.setAttribute('readonly', '');
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';

    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    textArea.setSelectionRange(0, textArea.value.length);

    const success = document.execCommand('copy');
    document.body.removeChild(textArea);

    if (!success) {
        throw new Error('document.execCommand("copy") returned false');
    }
}

async function extractTextFromClipboardItem(item) {
    if (!item) {
        return '';
    }

    const plainText = item.data && item.data['text/plain'];
    if (plainText && typeof plainText.text === 'function') {
        return plainText.text();
    }

    if (typeof item.getType === 'function') {
        try {
            const blob = await item.getType('text/plain');
            if (blob && typeof blob.text === 'function') {
                return blob.text();
            }
        } catch (error) {
            console.warn('读取 ClipboardItem 文本失败，继续尝试其他项。', error);
        }
    }

    return '';
}

const clipboard = ensureClipboardObject();
const insecureContext = window.location.protocol !== 'https:' && window.location.hostname !== 'localhost';

if (!clipboard.writeText || insecureContext) {
    clipboard.writeText = async function (text) {
        copyTextWithExecCommand(String(text ?? ''));
    };
}

if (!clipboard.write || insecureContext) {
    clipboard.write = async function (clipboardItems) {
        for (const item of clipboardItems || []) {
            const text = await extractTextFromClipboardItem(item);
            if (text) {
                await clipboard.writeText(text);
                return;
            }
        }

        throw new Error('未能从 ClipboardItem 中提取可复制的文本内容');
    };
}
