from pathlib import Path
from agentscope.tool import Toolkit

from agent_app.tools.code_tools import register_code_tools
from agent_app.tools.get_current_time import register_current_time_tools
from agent_app.tools.get_weather_tools import register_get_weather_tools
from agent_app.tools.file_tools import register_file_tools
from agent_app.tools.image_gen_tool import register_image_tools


def build_toolkit() -> Toolkit:
    toolkit = Toolkit()
    register_code_tools(toolkit)
    register_current_time_tools(toolkit)
    register_get_weather_tools(toolkit)
    register_file_tools(toolkit)
    register_image_tools(toolkit)

    base_dir = Path(__file__).resolve().parents[2]
    # 技能1
    skill_dir = base_dir / "agent_app" / "skills" / "top-tier-architecture-diagram-expert"
    # 检查目录是否存在，存在则调用原生 API 注册
    if skill_dir.exists():
        # register_agent_skill 仅记录技能路径和解析 YAML，不会把内容直接塞满上下文
        toolkit.register_agent_skill(str(skill_dir))
    else:
        print(f"[Warning] 技能目录未找到，跳过注册: {skill_dir}")
        
    # 技能2
    draw_skill_dir = base_dir / "agent_app" / "skills" / "academic-diagram-generator"
    if draw_skill_dir.exists():
        # 将我们刚刚新建的执行技能也注入给模型
        toolkit.register_agent_skill(str(draw_skill_dir))
    else:
        print(f"[Warning] 绘图执行技能目录未找到，跳过注册: {draw_skill_dir}")

    return toolkit
