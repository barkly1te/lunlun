from agentscope.agent import AgentBase
from agentscope.message import Msg
import asyncio

from agent_runtime import create_agent


async def creating_react_agent() -> None:
    """创建一个 ReAct 智能体并运行一个简单任务。"""
    jarvis = create_agent()

    msg = Msg(
        name="user",
        content="""你好！Jarvis，我现在有一段论文文本如下：
        随着以GPT-4、DeepSeek-V3、Llama 3为代表的大型语言模型（LLM）参数量突破千亿甚至万亿规模，生成式人工智能（AIGC）正在经历从“模型竞赛”向“基础设施竞赛”的深刻转型。[1]在这一转型过程中，推理成本、响应延迟与数据隐私成为了制约LLM大规模商业化落地的“不可能三角”。[2]传统的单体式推理架构——即由同一组GPU负责处理从Prompt输入到Token生成的全过程——正面临严峻的物理与经济瓶颈。
根本性的矛盾在于Transformer架构在推理过程中存在着两种截然不同的计算特征：首字生成阶段（预填充, Prefill）是典型的计算密集型任务，主要受限于GPU的浮点运算能力（FLOPS）；而随后的逐词生成阶段（解码, Decode）则是典型的显存带宽密集型任务，主要受限于显存带宽。在单体架构下，昂贵的计算资源（如NVIDIA H100）在解码阶段往往处于极低的利用率状态，造成了巨大的算力浪费。[3]，请你帮我用顶刊的风格稍微修改一下。""",
        role="user",
    )

    await jarvis(msg)


asyncio.run(creating_react_agent())
