// public/clipboard_compat.js
// Chainlit code-copy compatibility for HTTP and restricted clipboard environments.

(function installClipboardCompat() {
    function copyTextWithExecCommand(text) {
        const textArea = document.createElement('textarea');
        textArea.value = String(text ?? '');
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

    function findCodeTextNearButton(button) {
        let node = button;

        while (node && node !== document.body) {
            const codeNodes = node.querySelectorAll('pre code, code.whitespace-pre-wrap');
            if (codeNodes.length === 1) {
                return codeNodes[0].textContent || '';
            }
            node = node.parentElement;
        }

        return '';
    }

    function installCodeCopyClickFallback() {
        document.addEventListener(
            'click',
            function handleCodeCopyClick(event) {
                const target = event.target;
                if (!(target instanceof Element)) {
                    return;
                }

                const button = target.closest('button');
                if (!button) {
                    return;
                }

                const codeText = findCodeTextNearButton(button);
                if (!codeText) {
                    return;
                }

                if (typeof navigator.clipboard?.writeText === 'function') {
                    return;
                }

                try {
                    copyTextWithExecCommand(codeText);
                    event.preventDefault();
                    event.stopPropagation();
                    if (typeof event.stopImmediatePropagation === 'function') {
                        event.stopImmediatePropagation();
                    }
                } catch (error) {
                    console.warn('[lunlun] Manual code-copy fallback failed.', error);
                }
            },
            true,
        );
    }

    async function extractTextFromClipboardItem(item) {
        if (!item) {
            return '';
        }

        const data = item.data || {};
        const plainText = data['text/plain'];
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
                console.warn('[lunlun] Failed to read ClipboardItem text/plain.', error);
            }
        }

        return '';
    }

    const shim = {
        async writeText(text) {
            copyTextWithExecCommand(text);
        },
        async write(items) {
            for (const item of items || []) {
                const text = await extractTextFromClipboardItem(item);
                if (text) {
                    await shim.writeText(text);
                    return;
                }
            }

            throw new Error('No text/plain clipboard payload available');
        },
    };

    function defineMethod(target, name, fn) {
        if (!target) {
            return false;
        }

        try {
            Object.defineProperty(target, name, {
                configurable: true,
                writable: true,
                value: fn,
            });
        } catch (error) {
            try {
                target[name] = fn;
            } catch (_ignored) {
                return false;
            }
        }

        return typeof target[name] === 'function';
    }

    function patchClipboardObject(target) {
        if (!target) {
            return false;
        }

        const writeTextReady = defineMethod(target, 'writeText', shim.writeText);
        const writeReady = defineMethod(target, 'write', shim.write);
        return writeTextReady && writeReady;
    }

    if (typeof window.ClipboardItem === 'undefined') {
        window.ClipboardItem = class ClipboardItem {
            constructor(data) {
                this.data = data;
            }
        };
    }

    let currentClipboard;
    try {
        currentClipboard = navigator.clipboard;
    } catch (error) {
        currentClipboard = undefined;
    }

    patchClipboardObject(currentClipboard);

    if (typeof window.Clipboard !== 'undefined' && window.Clipboard.prototype) {
        patchClipboardObject(window.Clipboard.prototype);
    }

    const navigatorProto = window.Navigator && window.Navigator.prototype;
    const protoDescriptor = navigatorProto
        ? Object.getOwnPropertyDescriptor(navigatorProto, 'clipboard')
        : undefined;

    if (navigatorProto) {
        try {
            Object.defineProperty(navigatorProto, 'clipboard', {
                configurable: true,
                get() {
                    let clipboard = currentClipboard;

                    if (!clipboard && protoDescriptor && typeof protoDescriptor.get === 'function') {
                        try {
                            clipboard = protoDescriptor.get.call(this);
                        } catch (_ignored) {
                            clipboard = undefined;
                        }
                    }

                    if (patchClipboardObject(clipboard)) {
                        return clipboard;
                    }

                    return shim;
                },
            });
        } catch (error) {
            console.warn('[lunlun] Failed to override Navigator.prototype.clipboard.', error);
        }
    }

    if (!patchClipboardObject(currentClipboard)) {
        try {
            Object.defineProperty(navigator, 'clipboard', {
                configurable: true,
                value: shim,
            });
        } catch (error) {
            try {
                navigator.clipboard = shim;
            } catch (_ignored) {
                console.warn('[lunlun] Failed to attach clipboard shim to navigator.', error);
            }
        }
    }

    installCodeCopyClickFallback();
    window.__lunlunClipboardCompatInstalled = true;
})();
