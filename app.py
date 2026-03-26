import asyncio
import chainlit as cl
from agentscope.message import Msg
from agent_app.agent_factory import build_agent 

@cl.on_chat_start
async def on_chat_start():
    agent = build_agent()
    print("带有智能体技能的系统提示词:")
    print(agent.sys_prompt)
    cl.user_session.set("agent", agent)
    await cl.Message(
        content="你好！我是 **论论**，你的智能助手。很高兴为你服务！"
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    agent = cl.user_session.get("agent")
    user_msg = Msg(name="user", content=message.content, role="user")
    
    thinking_text = ""
    final_text = ""

    # ================= 1. 动态思考过程 UI =================
    # async with 开启时，前端会出现气泡，并显示转圈的 Loading 动画
    async with cl.Step(name="🤔 论论正在深度思考中...") as step:
        
        # 此时前端在转圈等待，后端在真实调用模型
        response = await agent(user_msg)
        content_data = response.content
        
        # 解析数据
        if isinstance(content_data, list):
            for block in content_data:
                if block.get('type') == 'thinking':
                    thinking_text = block.get('thinking', '')
                elif block.get('type') == 'text':
                    final_text = block.get('text', '')
        elif isinstance(content_data, str):
            final_text = content_data
        else:
            final_text = str(content_data)

        # 拿到数据后，我们在气泡内实现“思考流”的打字机效果
        if thinking_text:
            step.name = "🤔 论论的思考过程"
            # 使用 Markdown 的斜体和引用语法，使其呈现灰色的次级文本视觉效果
            formatted_think = f"> _{thinking_text}_"
            
            # 使用 stream_token 将思考过程动态打字输出到气泡中
            # 速度可以稍微调快一点（0.01秒），模拟脑暴的过程
            chunk_size = 6
            for i in range(0, len(formatted_think), chunk_size):
                await step.stream_token(formatted_think[i:i + chunk_size])
                await asyncio.sleep(0.01) 
        else:
            step.name = "🤔 思考完毕"
            step.content = "_无内部思考过程。_"
            
    # 【核心机制】：当代码跳出上面的 async with 块时，
    # Chainlit 会自动把转圈动画变成“绿色的完成勾”，并且默认【自动折叠】这个气泡！

    # ================= 2. 流式输出正文 =================
    if not final_text:
        final_text = "（由于某些原因，没有生成正文内容）"

    msg = cl.Message(content="")
    await msg.send()
    
    # 正文的打字机速度可以稍微平缓一点，符合阅读节奏
    chunk_size = 3 
    for i in range(0, len(final_text), chunk_size):
        msg.content += final_text[i:i + chunk_size]
        await msg.update()
        await asyncio.sleep(0.02) 

    msg.content = final_text
    await msg.update()