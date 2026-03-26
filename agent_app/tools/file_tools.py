import os
from agentscope.tool import Toolkit, ToolResponse

def read_text_file(file_path: str) -> ToolResponse:
    """
    读取指定文本文件的内容。智能体可以使用此工具阅读 SKILL.md 等长文本文件。
    
    Args:
        file_path: 要读取的文本文件的绝对或相对路径。
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return ToolResponse(content=[{"type": "text", "text": f"Error: 文件 {file_path} 不存在。"}])
    
    try:
        # 以 UTF-8 编码读取文件内容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return ToolResponse(content=[{"type": "text", "text": content}])
    except Exception as e:
        return ToolResponse(content=[{"type": "text", "text": f"Error: 读取文件失败 - {str(e)}"}])

def register_file_tools(toolkit: Toolkit) -> None:
    """
    将文件读取工具注册到 Toolkit 中
    """
    toolkit.register_tool_function(read_text_file)