#!/usr/bin/env python3
"""
API 配置测试脚本

用法:
    python test_api_setup.py
"""

import os
import sys
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

def check_env_var(name, required=False):
    """检查环境变量是否设置"""
    value = os.environ.get(name)
    if value:
        if len(value) > 20:
            masked = value[:10] + "..." + value[-5:]
        else:
            masked = "***"
        print(f"✅ {name}: {masked}")
        return True
    else:
        if required:
            print(f"❌ {name}: 未设置 (必需)")
            return False
        else:
            print(f"⚠️  {name}: 未设置 (可选)")
            return False

def test_imports():
    """测试必要的包是否已安装"""
    print("\n" + "="*80)
    print("检查 Python 包")
    print("="*80)
    
    packages = {
        "requests": "HTTP 请求",
        "openai": "OpenAI API 客户端",
        "gget": "学术搜索 (PubMed, arXiv)",
        "bioservices": "生物医学数据库",
        "pandas": "数据处理",
        "matplotlib": "绘图",
        "PIL": "图像处理",
        "pdf2image": "PDF 转图片",
        "pypdf": "PDF 解析",
        "dotenv": "环境变量管理"
    }
    
    all_installed = True
    for pkg, desc in packages.items():
        try:
            if pkg == "PIL":
                __import__("PIL")
            elif pkg == "dotenv":
                __import__("dotenv")
            else:
                __import__(pkg)
            
            # 获取版本号
            module = sys.modules[pkg] if pkg != "PIL" else sys.modules["PIL"]
            version = getattr(module, "__version__", "未知版本")
            print(f"✅ {pkg} ({version}): {desc}")
        except ImportError:
            print(f"❌ {pkg}: {desc} - 未安装")
            all_installed = False
    
    return all_installed

def test_openrouter():
    """测试 OpenRouter API 连接"""
    print("\n" + "="*80)
    print("测试 OpenRouter API (Perplexity)")
    print("="*80)
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or "your_" in api_key:
        print("⚠️  OPENROUTER_API_KEY 未配置或为占位符")
        print("   请在 .env 文件中配置真实的 API Key")
        print("   获取地址：https://openrouter.ai/keys")
        return False
    
    try:
        import requests
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 测试连接（不实际调用模型，只验证 Key）
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ OpenRouter API 连接成功")
            models = response.json().get("data", [])
            perplexity_models = [m for m in models if "perplexity" in m.get("id", "").lower()]
            if perplexity_models:
                print(f"   可用的 Perplexity 模型:")
                for m in perplexity_models[:3]:
                    print(f"     - {m['id']}")
            return True
        else:
            print(f"❌ OpenRouter API 连接失败: {response.status_code}")
            print(f"   响应: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_gget():
    """测试 gget 学术搜索"""
    print("\n" + "="*80)
    print("测试 gget (arXiv 搜索)")
    print("="*80)
    
    try:
        import gget
        
        # 测试搜索（限制结果数）
        print("   正在搜索 'LLM serving'...")
        results = gget.search_arxiv("LLM serving", limit=3)
        
        if results and len(results) > 0:
            print(f"✅ gget 工作正常，找到 {len(results)} 条结果")
            print("   示例结果:")
            for i, r in enumerate(results[:2], 1):
                title = r.get("title", "无标题")[:60]
                print(f"     {i}. {title}...")
            return True
        else:
            print("⚠️  gget 返回空结果（可能是网络问题）")
            return True  # 不算失败
            
    except Exception as e:
        print(f"❌ gget 测试失败: {e}")
        return False

def test_pdf_tools():
    """测试 PDF 工具"""
    print("\n" + "="*80)
    print("测试 PDF 工具")
    print("="*80)
    
    # 检查 Poppler
    import shutil
    poppler_path = shutil.which("pdftoppm")
    if poppler_path:
        print(f"✅ Poppler 已安装: {poppler_path}")
    else:
        print("⚠️  Poppler 未安装 (pdf2image 需要)")
        print("   安装指南：见 docs/API_SETUP_GUIDE.md")
    
    # 测试 pdf2image 导入
    try:
        import pdf2image
        print("✅ pdf2image 已安装")
    except ImportError:
        print("❌ pdf2image 未安装")
    
    # 测试 pypdf 导入
    try:
        import pypdf
        print("✅ pypdf 已安装")
    except ImportError:
        print("❌ pypdf 未安装")

def main():
    """主测试函数"""
    print("="*80)
    print("API 配置测试")
    print("="*80)
    print(f"Python: {sys.executable}")
    print(f"版本：{sys.version.split()[0]}")
    print(f"时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查环境变量
    print("\n" + "="*80)
    print("检查环境变量")
    print("="*80)
    
    env_status = {
        "OPENROUTER_API_KEY": check_env_var("OPENROUTER_API_KEY", required=False),
        "PARALLEL_API_KEY": check_env_var("PARALLEL_API_KEY", required=False),
        "OPENAI_API_KEY": check_env_var("OPENAI_API_KEY", required=False),
        "DASHSCOPE_API_KEY": check_env_var("DASHSCOPE_API_KEY", required=False),
    }
    
    # 测试包导入
    imports_ok = test_imports()
    
    # 测试 API 连接
    if env_status.get("OPENROUTER_API_KEY"):
        api_ok = test_openrouter()
    else:
        print("\n⚠️  跳过 OpenRouter API 测试（未配置）")
        api_ok = None
    
    # 测试 gget
    gget_ok = test_gget()
    
    # 测试 PDF 工具
    test_pdf_tools()
    
    # 总结
    print("\n" + "="*80)
    print("测试总结")
    print("="*80)
    
    if all(env_status.values()) and imports_ok:
        print("✅ 所有必需配置已完成！")
        print("\n可以开始使用:")
        print("  - research-lookup skill (学术论文搜索)")
        print("  - literature-review skill (系统性文献综述)")
        print("  - pdf_analysis skill (PDF 分析)")
    else:
        print("⚠️  部分配置缺失:")
        if not env_status.get("OPENROUTER_API_KEY"):
            print("  - 配置 OPENROUTER_API_KEY 以使用学术搜索")
        if not imports_ok:
            print("  - 安装缺失的 Python 包")
        
        print("\n即使部分配置缺失，仍可使用:")
        print("  - 基于知识库的文献整理")
        print("  - PDF 读取和分析（如果 Poppler 已安装）")
        print("  - 数据处理和可视化")
    
    print("\n详细配置指南：docs/API_SETUP_GUIDE.md")
    print("="*80)

if __name__ == "__main__":
    main()
