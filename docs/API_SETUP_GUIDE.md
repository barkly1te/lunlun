# API 配置指南

本文档说明如何配置 API Key 以使用 agentscope 的各项技能。

---

## 📌 当前环境信息

- **Python 解释器**: `D:\Code\agentscope\.venv\Scripts\python.exe`
- **Python 版本**: 3.12.12 (64 位 CPython)
- **系统**: Windows 11
- **环境文件**: `D:\Code\agentscope\.env`

---

## 🔑 必需配置的 API Key

### 1. OpenRouter API Key ⭐ 强烈推荐

**用途**: 
- 访问 Perplexity sonar-pro-search
- 学术论文搜索（`research-lookup` skill）
- 文献检索（`literature-review` skill）

**获取步骤**:
1. 访问 https://openrouter.ai/
2. 注册/登录账号
3. 进入 "Keys" 页面
4. 点击 "Create Key"
5. 复制 Key

**费用**:
- 按使用量计费
- Perplexity sonar-pro-search: ~$0.01-0.05/次查询
- 新用户可能有免费额度

**配置方法**:
编辑 `.env` 文件，将以下内容替换为你的真实 Key：
```
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

### 2. Parallel AI API Key（可选）

**用途**:
- Parallel Chat API
- 通用研究查询
- 多源信息整合

**获取步骤**:
1. 访问 https://parallel.ai/
2. 注册账号
3. 进入 Dashboard 创建 API Key

**配置方法**:
```
PARALLEL_API_KEY=your_parallel_api_key_here
```

---

### 3. OpenAI API Key（可选）

**用途**:
- OpenAI 原生 API
- GPT-4 等模型调用

**获取步骤**:
1. 访问 https://platform.openai.com/
2. 登录账号
3. 进入 "API Keys" 页面
4. 创建新的 Key

**配置方法**:
```
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

### 4. DashScope API Key ✅ 已配置

**用途**:
- 阿里云通义千问模型
- 中文任务优化

**状态**: 示例配置
```
DASHSCOPE_API_KEY=your_dashscope_api_key_here
```

---

## 📦 已安装的 Python 包

### 基础包
- ✅ requests (2.32.5)
- ✅ openai (2.28.0)
- ✅ python-dotenv

### 文献检索包
- ✅ gget (0.30.3) - PubMed, arXiv, bioRxiv 搜索
- ✅ bioservices - 生物医学数据库

### 数据处理包
- ✅ pandas (3.0.1)
- ✅ matplotlib (3.10.8)

### PDF 处理包
- ✅ pillow (已安装)
- ✅ pdf2image (已安装)
- ✅ pypdf (已安装)
- ✅ Poppler (已安装: MiKTeX 版本)

---

## 🚀 快速测试配置

### 测试 OpenRouter (Perplexity)

```bash
# 激活虚拟环境
D:\Code\agentscope\.venv\Scripts\activate

# 运行测试脚本
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.environ.get('OPENROUTER_API_KEY')
if api_key and 'your_' not in api_key:
    print('✅ OpenRouter API Key 已正确配置')
else:
    print('❌ 请配置 OPENROUTER_API_KEY')
"
```

### 测试 research-lookup skill

```bash
python skills/research-lookup/scripts/research_lookup.py \
  "Prefill-Decoding disaggregation LLM" \
  --force-backend perplexity \
  -o sources/test_search.md
```

### 测试 literature-review skill

```bash
# 使用 gget 搜索 arXiv
gget search arxiv "LLM serving" -l 5
```

---

## 📝 使用示例

### 示例 1: 学术论文搜索

```bash
# 搜索 PD 分离技术相关论文
python skills/research-lookup/scripts/research_lookup.py \
  "Prefill-Decoding disaggregation DistServe Mooncake LLM serving" \
  --force-backend perplexity \
  -o sources/papers_pd_disaggregation.md
```

### 示例 2: 系统性文献综述

```bash
# 使用 literature-review skill
# 需要先阅读 skills/literature-review/SKILL.md
```

### 示例 3: PDF 分析

```bash
# 分析下载的 PDF 论文
python skills/pdf_analysis/scripts/analyze_pdf.py \
  papers/distserve.pdf \
  -o outputs/distserve_summary.md
```

---

## 🔧 故障排查

### 问题 1: API Key 未生效

**症状**: 提示 "OPENROUTER_API_KEY not set"

**解决方法**:
1. 确认 `.env` 文件在正确位置 (`D:\Code\agentscope\.env`)
2. 确认 Key 格式正确，没有多余空格
3. 重启 Python 环境或终端
4. 手动加载环境变量:
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```

### 问题 2: 包导入失败

**症状**: `ModuleNotFoundError: No module named 'xxx'`

**解决方法**:
1. 确认已激活虚拟环境:
   ```bash
   D:\Code\agentscope\.venv\Scripts\activate
   ```
2. 重新安装包:
   ```bash
   pip install <package_name>
   ```

### 问题 3: PDF 渲染失败

**症状**: pdf2image 报错 "poppler not found"

**解决方法**:
1. 确认 Poppler 已安装:
   ```bash
   pdftoppm -h
   ```
2. 如果未安装，参考上文安装指南
3. 确保 Poppler 的 bin 目录在 PATH 中

---

## 💡 最佳实践

1. **不要将 `.env` 文件提交到 Git**
   ```bash
   # 确保 .env 在 .gitignore 中
   echo ".env" >> .gitignore
   ```

2. **定期更新 API Key**
   - 每 3-6 个月更换一次
   - 如果怀疑泄露，立即更换

3. **监控 API 使用量**
   - OpenRouter: https://openrouter.ai/activity
   - 设置使用限额提醒

4. **使用本地缓存**
   - 搜索结果保存到 `sources/` 目录
   - 避免重复查询节省费用

---

## 📚 相关文档

- `skills/research-lookup/SKILL.md` - Research Lookup 技能说明
- `skills/literature-review/SKILL.md` - Literature Review 技能说明
- `skills/pdf_analysis/SKILL.md` - PDF Analysis 技能说明
- `sources/` - 所有搜索结果和文献数据存放目录

---

**最后更新**: 2026-03-15
**维护者**: 廖浩充
