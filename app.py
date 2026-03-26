import os
import re
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
    
    # ================= 新增：处理用户上传的图片 =================
    # 提取用户通过 Chainlit 附件上传的图片本地路径
    image_paths = []
    if message.elements:
        for el in message.elements:
            # 判断附件是否为图片
            if "image" in el.mime:
                image_paths.append(el.path)
    
    content = message.content
    # 如果用户传了图片，我们通过后台注入的形式告诉 Agent 这个图片的本地路径
    if image_paths:
        content += f"\n\n[系统提示：用户上传了图片，系统已缓存至本地路径：{', '.join(image_paths)}。如果用户的需求涉及改图或生图，请提取此路径作为 image_path 参数调用 generate_image_tool 工具]"
    
    user_msg = Msg(name="user", content=content, role="user")
    # ============================================================
    
    thinking_text = ""
    final_text = ""

    # ================= 1. 动态思考过程 UI =================
    async with cl.Step(name="🤔 论论正在深度思考中...") as step:
        
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
            formatted_think = f"> _{thinking_text}_"
            
            chunk_size = 6
            for i in range(0, len(formatted_think), chunk_size):
                await step.stream_token(formatted_think[i:i + chunk_size])
                await asyncio.sleep(0.01) 
        else:
            step.name = "🤔 思考完毕"
            step.content = "_无内部思考过程。_"

    # ================= 2. 流式输出正文与图片渲染 =================
    if not final_text:
        final_text = "（由于某些原因，没有生成正文内容）"

    # ================= 新增：解析工具留下的图片标记 =================
    image_elements = []
    # 使用正则匹配形如 [GEN_IMAGE: outputs/generated_123456.jpg] 的特殊标记
    img_pattern = r"\[GEN_IMAGE:\s*(.*?)\]"
    img_matches = re.findall(img_pattern, final_text)
    
    # 遍历所有被找出的路径，包装成 Chainlit 支持下载和预览的元素对象
    for img_path in img_matches:
        if os.path.exists(img_path):
            image_elements.append(
                # cl.Image 支持前端直接预览以及右键保存原图
                cl.Image(path=img_path, name="生成的图片", display="inline")
            )
    
    # 从呈现给用户的正文中剔除掉这个工具标记，保证阅读体验干净
    display_text = re.sub(img_pattern, "", final_text).strip()
    # 如果把标记剔除后成了空文本，给一个兜底说明
    if not display_text and image_elements:
         display_text = "图片已生成，请查看下方结果："
    # ============================================================

    # 将图片元素附着在此次交互消息体上
    msg = cl.Message(content="", elements=image_elements)
    await msg.send()
    
    # 正文的打字机速度
    chunk_size = 3 
    for i in range(0, len(display_text), chunk_size):
        msg.content += display_text[i:i + chunk_size]
        await msg.update()
        await asyncio.sleep(0.02) 

    msg.content = display_text
    await msg.update()