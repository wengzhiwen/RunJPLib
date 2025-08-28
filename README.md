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

### 最新更新 (2025-01-27)
- **GridFS PDF存储**：解决MongoDB 16MB文档大小限制
- **安全文件名策略**：使用UUID防止文件名注入攻击
- **智能文件去重**：避免重复存储相同文件

### 技术栈
- **后端**: Flask + MongoDB + GridFS
- **前端**: HTML + CSS + JavaScript + PDF.js
- **认证**: JWT + 访问码保护
- **部署**: 支持Docker和传统部署

### 数据存储
- **大学信息**: MongoDB + GridFS (PDF文件)
- **博客文章**: MongoDB
- **文件系统**: 作为MongoDB的回退数据源

## 开发文档

详细的开发文档请查看 `docs/` 目录：
- [MongoDB设计文档](docs/mongoDB_design.md)
- [GridFS迁移指南](docs/GridFS_migration_guide.md)
- [管理面板文档](docs/admin_panel.md)
- [线程池架构设计](docs/thread_pool_architecture.md)
- [变更日志](docs/CHANGELOG.md)

## 快速开始

```bash
# 克隆项目
git clone https://github.com/wengzhiwen/RunJPLib.git
cd RunJPLib

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置以下重要配置：
# - MongoDB连接和访问码
# - 线程池大小（可选，有默认值）
# - 详见docs/thread_pool_architecture.md

# 运行迁移脚本（如果需要）
python tools/migrate_to_gridfs.py

# 启动应用
python app.py
```

## 贡献

欢迎提交Issue和Pull Request！请确保：
1. 遵循现有的代码风格
2. 更新相关文档
3. 测试功能完整性

## 许可证

本项目采用MIT许可证，详见 [LICENSE](LICENSE) 文件。