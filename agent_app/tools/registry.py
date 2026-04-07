from agentscope.tool import Toolkit

from agent_app.skills.catalog import get_registered_skills
from agent_app.tools.code_tools import register_code_tools
from agent_app.tools.file_tools import register_file_tools
from agent_app.tools.get_current_time import register_current_time_tools
from agent_app.tools.get_weather_tools import register_get_weather_tools
from agent_app.tools.image_gen_tool import register_image_tools
from agent_app.tools.search_paper_rag import register_search_paper_rag_tools


def register_local_agent_skills(toolkit: Toolkit) -> None:
    skills = get_registered_skills()
    if not skills:
        print('[Warning] 未发现可注册的技能目录。')
        return

    for skill in skills:
        toolkit.register_agent_skill(skill.skill_dir)


def build_toolkit() -> Toolkit:
    toolkit = Toolkit()
    register_code_tools(toolkit)
    register_current_time_tools(toolkit)
    register_get_weather_tools(toolkit)
    register_file_tools(toolkit)
    register_image_tools(toolkit)
    register_search_paper_rag_tools(toolkit)
    register_local_agent_skills(toolkit)
    return toolkit
