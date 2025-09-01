# RunJPLib
日本本科考试信息图书馆 日本学部入試情報図書館

## DEMO
只想看效果[点这里](https://www.runjplib.com/)

### 热门大学

#### 顶尖国立大学
- [东京大学](https://www.runjplib.com/university/東京大学)
- [京都大学](https://www.runjplib.com/university/京都大学)
- [大阪大学](https://www.runjplib.com/university/大阪大学)
- [东北大学](https://www.runjplib.com/university/東北大学)
- [九州大学](https://www.runjplib.com/university/九州大学)
- [北海道大学](https://www.runjplib.com/university/北海道大学)
- [名古屋大学](https://www.runjplib.com/university/名古屋大学)
- [筑波大学](https://www.runjplib.com/university/筑波大学)
- [广岛大学](https://www.runjplib.com/university/広島大学)
- [一桥大学](https://www.runjplib.com/university/一橋大学)

#### 早庆上理
- [早稻田大学](https://www.runjplib.com/university/早稲田大学)
- [庆应义塾大学](https://www.runjplib.com/university/慶應義塾大学)
- [上智大学](https://www.runjplib.com/university/上智大学)
- [东京理科大学](https://www.runjplib.com/university/東京理科大学)

#### MARCH
- [明治大学](https://www.runjplib.com/university/明治大学)
- [青山学院大学](https://www.runjplib.com/university/青山学院大学)
- [立教大学](https://www.runjplib.com/university/立教大学)
- [中央大学](https://www.runjplib.com/university/中央大学)
- [法政大学](https://www.runjplib.com/university/法政大学)

#### 关西私立名校
- [同志社大学](https://www.runjplib.com/university/同志社大学)
- [立命馆大学](https://www.runjplib.com/university/立命館大学)
- [关西大学](https://www.runjplib.com/university/関西大学)
- [关西学院大学](https://www.runjplib.com/university/関西学院大学)
- [近畿大学](https://www.runjplib.com/university/近畿大学)

#### 艺术类院校
- [东京艺术大学](https://www.runjplib.com/university/東京藝術大学)
- [武藏野美术大学](https://www.runjplib.com/university/武蔵野美術大学)
- [多摩美术大学](https://www.runjplib.com/university/多摩美術大学)
- [京都精华大学](https://www.runjplib.com/university/京都精華大学)

#### 日东驹专
- [日本大学](https://www.runjplib.com/university/日本大学)
- [东洋大学](https://www.runjplib.com/university/東洋大学)
- [驹泽大学](https://www.runjplib.com/university/駒澤大学)
- [专修大学](https://www.runjplib.com/university/専修大学)

#### 大东亚帝国
- [大东文化大学](https://www.runjplib.com/university/大東文化大学)
- [东海大学](https://www.runjplib.com/university/東海大学)
- [亚细亚大学](https://www.runjplib.com/university/亜細亜大学)
- [帝京大学](https://www.runjplib.com/university/帝京大学)
- [国士馆大学](https://www.runjplib.com/university/国士舘大学)

#### 女子大学
- [津田塾大学](https://www.runjplib.com/university/津田塾大学)
- [东京女子大学](https://www.runjplib.com/university/東京女子大学)
- [日本女子大学](https://www.runjplib.com/university/日本女子大学)
- [圣心女子大学](https://www.runjplib.com/university/聖心女子大学)

#### 关东上流私大
- [学习院大学](https://www.runjplib.com/university/学習院大学)
- [成蹊大学](https://www.runjplib.com/university/成蹊大学)
- [成城大学](https://www.runjplib.com/university/成城大学)
- [武藏大学](https://www.runjplib.com/university/武蔵大学)

## 技术架构

### 技术栈
- **后端**: Flask + MongoDB + GridFS + LlamaIndex + ChromaDB
- **前端**: HTML + CSS + JavaScript + PDF.js
- **AI对话**: OpenAI GPT-4o-mini + 混合搜索策略
- **向量搜索**: LlamaIndex + OpenAI Embeddings
- **认证**: JWT + 访问码保护 + 浏览器会话ID
- **部署**: 支持Docker和传统部署

### 数据存储
- **大学信息**: MongoDB + GridFS (PDF文件)
- **博客文章**: MongoDB
- **向量索引**: ChromaDB (LlamaIndex)

### AI功能特性
- **智能混合搜索**：结合向量搜索和关键词搜索的优势
- **同义词扩展**：自动识别中日文同义词，提高查询准确性
- **内存优化**：实时监控内存使用，自动清理临时数据
- **隐私保护**：基于浏览器会话的完全隔离机制
- **会话管理**：智能会话恢复和历史消息加载


## 快速开始

### 环境要求
- Python 3.8+
- MongoDB 4.4+
- OpenAI API Key
- 至少4GB内存（推荐8GB+）

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/your-username/RunJPLib.git
cd RunJPLib

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入必要的配置

# 5. 启动MongoDB
./start-mongodb-dev.sh

# 6. 创建数据库索引
python -c "from utils.db_indexes import create_indexes; create_indexes()"

# 7. 启动应用
python app.py
```

### 环境变量配置

```bash
# OpenAI配置
OPENAI_API_KEY=your_openai_api_key
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EXT_QUERY_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-ada-002

# 数据库配置
MONGODB_URI=mongodb://localhost:27017/runjplib

# ChromaDB配置
CHROMA_DB_PATH=./chroma_db

# 混合搜索配置
HYBRID_SEARCH_ENABLED=true
MEMORY_CLEANUP_THRESHOLD=80
REGEX_CACHE_SIZE=50
SEARCH_TIMEOUT_VECTOR=5.0
SEARCH_TIMEOUT_KEYWORD=3.0

# 会话配置
CHAT_SESSION_TIMEOUT=3600
```
