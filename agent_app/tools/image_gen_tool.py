import os
import time
import base64
import re
import requests
from pathlib import Path
from agentscope.tool import Toolkit, ToolResponse


def _extract_generated_image(resp_json: dict) -> tuple[str | None, str | None]:
    """Extract base64 image data and mime type from known fastai/Gemini response shapes."""
    try:
        res_parts = (
            resp_json.get("candidates", [])[0]
            .get("content", {})
            .get("parts", [])
        )
    except Exception:
        return None, None

    for part in res_parts:
        inline_data = part.get("inline_data") or part.get("inlineData")
        if inline_data and inline_data.get("data"):
            mime_type = inline_data.get("mime_type") or inline_data.get("mimeType")
            return inline_data["data"], mime_type

        text = part.get("text")
        if not text:
            continue

        match = re.search(
            r"data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\r\n]+)",
            text,
        )
        if match:
            mime_type = match.group(1)
            encoded_data = re.sub(r"\s+", "", match.group(2))
            return encoded_data, mime_type

    return None, None


def _suffix_from_mime_type(mime_type: str | None) -> str:
    """Choose a file suffix that matches the returned image mime type."""
    mime = (mime_type or "").lower()
    if mime == "image/png":
        return ".png"
    if mime in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if mime == "image/webp":
        return ".webp"
    return ".jpg"


def generate_image_tool(prompt: str, image_path: str = "") -> ToolResponse:
    """
    根据用户的文字描述和上传的图片，调用 Gemini 模型生成或修改图片。
    
    Args:
        prompt (str): 用户期望如何修改或生成图片的详细文字描述。
        image_path (str): 用户上传的原始图片的本地路径。如果是纯文本生图任务，该参数留空即可。
        
    Returns:
        ToolResponse: 符合 AgentScope 工具协议的执行结果。
    """
    def text_response(text: str) -> ToolResponse:
        return ToolResponse(content=[{"type": "text", "text": text}])

    # 从环境变量中获取密钥
    api_key = os.getenv("FASTAI_API_KEY", "")
    if not api_key:
        return text_response("错误：未能找到 FASTAI_API_KEY 环境变量，请检查配置。")

    # 4K 学术插图生成通常较慢，默认给足读取超时；可用环境变量覆盖
    request_timeout_seconds = int(os.getenv("FASTAI_IMAGE_TIMEOUT_SECONDS", "600"))

    inline_image_data = None
    inline_image_mime_type = None

    # 如果用户上传了图片，进行 base64 编码并装载
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                img_data = f.read()
            inline_image_data = base64.b64encode(img_data).decode("utf-8")
            
            # 根据后缀简单判断 mime type
            ext = os.path.splitext(image_path)[1].lower()
            inline_image_mime_type = "image/png" if ext == ".png" else "image/jpeg"
        except Exception as e:
            return text_response(f"读取本地图片失败：{str(e)}")

    # 按 fastai.group 的 Gemini 图片接口格式构造请求
    url = "https://api.fastai.group/v1beta/models/gemini-3-pro-image-preview:generateContent"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    parts = [{"text": prompt}]
    if inline_image_data and inline_image_mime_type:
        parts.append({
            "inline_data": {
                "mime_type": inline_image_mime_type,
                "data": inline_image_data,
            }
        })
    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": "3:2",
                "imageSize": "4K"
            }
        }
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=(30, request_timeout_seconds),
        )
        response.raise_for_status()
        resp_json = response.json()

        generated_base64, generated_mime_type = _extract_generated_image(resp_json)
        if not generated_base64:
            return text_response(
                f"API调用成功，但未能从返回值中解析出图片数据。返回片段：{str(resp_json)[:200]}"
            )

        output_dir = Path(__file__).resolve().parents[2] / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        file_suffix = _suffix_from_mime_type(generated_mime_type)
        output_file = output_dir / f"generated_{int(time.time())}{file_suffix}"
        with open(output_file, "wb") as f:
            f.write(base64.b64decode(generated_base64))

        # 严格要求大模型输出 [GEN_IMAGE: 路径] 格式，方便我们在 app.py 中正则捕获并交给 Chainlit 渲染
        return text_response(
            f"图片处理成功！已存入本地：{output_file}。请在你最终给用户的回复正文中，严格附上此段字符串（包含括号）：\n[GEN_IMAGE: {output_file}]"
        )

    except requests.exceptions.Timeout:
        return text_response(
            f"图片生成超时：已等待约 {request_timeout_seconds} 秒。4K 生图通常较慢，可稍后重试，或继续增大 FASTAI_IMAGE_TIMEOUT_SECONDS。"
        )
    except Exception as e:
        return text_response(f"图片生成接口请求失败，异常信息：{str(e)}")

def register_image_tools(toolkit: Toolkit):
    """
    注册生图工具的统一入口
    """
    toolkit.register_tool_function(generate_image_tool)
