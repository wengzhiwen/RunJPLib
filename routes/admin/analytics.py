import logging
from datetime import datetime, timedelta

from flask import redirect, render_template, request, url_for

from routes.admin.auth import admin_required
from utils import get_db, task_manager

from . import admin_bp


@admin_bp.route("/university-tagger", methods=["GET", "POST"])
@admin_required
def university_tagger_page():
    """大学标签工具页面，用于手动触发和查看结果"""
    db = get_db()
    if db is None:
        return render_template("university_tagger.html", error="数据库连接失败")

    if request.method == "POST":
        # 查找是否已经有正在运行或待处理的标签任务
        existing_task = db.processing_tasks.find_one({"task_type": "TAG_UNIVERSITIES", "status": {"$in": ["pending", "processing"]}})
        if existing_task:
            logging.warning("University tagging task is already running or pending.")
        else:
            task_name = f"University Tagging - Triggered manually at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            task_manager.create_task(task_type="TAG_UNIVERSITIES", task_name=task_name)
            logging.info("New university tagging task created.")
        return redirect(url_for("admin.university_tagger_page"))

    # GET请求：查找最新的一次标签任务
    latest_task = db.processing_tasks.find_one({"task_type": "TAG_UNIVERSITIES"}, sort=[("created_at", -1)])

    if latest_task:
        # 格式化时间戳以便显示
        if latest_task.get("created_at"):
            latest_task["created_at_str"] = latest_task["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if latest_task.get("updated_at"):
            latest_task["updated_at_str"] = latest_task["updated_at"].strftime("%Y-%m-%d %H:%M:%S")

        # 将日志中的时间戳也格式化
        if "logs" in latest_task:
            for log in latest_task["logs"]:
                if "timestamp" in log:
                    log["timestamp_str"] = log["timestamp"].strftime("%H:%M:%S.%f")[:-3]

    return render_template("university_tagger.html", task=latest_task)


@admin_bp.route("/analytics/unique_ips")
@admin_required
def unique_ips_page():
    """展示最近24小时的独立IP列表及相关信息（无SSE）。"""
    db = get_db()
    if db is None:
        return render_template("unique_ips.html", error="数据库连接失败", items=[])

    # 确保mmdb文件可用
    from utils import ip_geo_manager

    logging.info("🔧 检查mmdb文件可用性...")
    mmdb_available = ip_geo_manager.ensure_mmdb_available()
    logging.info(f"📁 mmdb文件状态: {'可用' if mmdb_available else '不可用'}")

    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    logging.info(f"⏰ 查询时间范围: {twenty_four_hours_ago} 至今")

    try:
        pipeline = [
            {
                "$match": {
                    "timestamp": {
                        "$gte": twenty_four_hours_ago
                    }
                }
            },
            {
                "$group": {
                    "_id": "$ip",
                    "first_seen": {
                        "$min": "$timestamp"
                    },
                    "last_seen": {
                        "$max": "$timestamp"
                    },
                    "visit_count": {
                        "$sum": 1
                    },
                    "page_types": {
                        "$addToSet": "$page_type"
                    },
                }
            },
            {
                "$sort": {
                    "last_seen": -1
                }
            },
        ]

        logging.info("🔍 执行MongoDB聚合查询...")
        results = list(db.access_logs.aggregate(pipeline))
        logging.info(f"📊 查询到 {len(results)} 个独立IP")

        items = []
        ips_to_lookup = []

        for r in results:
            ip = r.get("_id")

            # 检查该IP是否已有地理信息
            geo_info = None
            if mmdb_available:
                # 从访问记录中查找
                sample_log = db.access_logs.find_one({"ip": ip, "geo_info": {"$exists": True}})
                if sample_log and sample_log.get("geo_info"):
                    geo_info = sample_log["geo_info"]
                    logging.debug(f"✅ 从访问记录中找到地理信息: {ip} -> {geo_info.get('city', 'N/A')}")
                else:
                    ips_to_lookup.append(ip)
                    logging.debug(f"❓ IP需要解析地理信息: {ip}")

            item = {
                "ip": ip,
                "first_seen": r.get("first_seen"),
                "last_seen": r.get("last_seen"),
                "visit_count": r.get("visit_count", 0),
                "page_types": r.get("page_types", []),
                "geo_info": geo_info,
            }
            items.append(item)

        logging.info(f"🎯 准备处理 {len(ips_to_lookup)} 个IP的地理信息")

        # 批量查询地理信息并更新数据库
        if mmdb_available and ips_to_lookup:
            _batch_update_geo_info(db, ips_to_lookup, items)
        else:
            logging.info("⏭️ 跳过地理信息处理 (mmdb不可用或无IP需要处理)")

        logging.info(f"✅ 页面渲染完成，共 {len(items)} 个IP")
        return render_template("unique_ips.html", items=items, mmdb_available=mmdb_available)
    except Exception as e:
        logging.error(f"查询独立IP统计失败: {e}", exc_info=True)
        return render_template("unique_ips.html", error="查询失败", items=[])


def _batch_update_geo_info(db, ips_to_lookup, items):
    """批量更新IP地理信息到数据库（嵌入方案）"""
    from utils import ip_geo_manager

    try:
        logging.info(f"🔍 开始批量更新地理信息，总IP数量: {len(ips_to_lookup)}")

        # 限制批量处理数量
        batch_size = 200
        processed_count = 0
        skipped_count = 0

        logging.info(f"⚙️ 批量处理限制: {batch_size} 个IP")

        for ip in ips_to_lookup:
            if processed_count >= batch_size:
                logging.info(f"⏹️ 达到批量处理限制 {batch_size}，跳过剩余 {len(ips_to_lookup) - processed_count} 个IP")
                break

            # 处理多IP地址的情况
            original_ip = ip
            if "," in ip or " " in ip:
                # 取第一个IP进行解析
                first_ip = ip.split(",")[0].strip()
                logging.debug(f"🔄 多IP地址处理: '{ip}' -> 使用第一个IP '{first_ip}' 进行地理信息解析")
                ip = first_ip
            elif not ip:
                logging.warning("跳过空IP地址")
                skipped_count += 1
                continue

            logging.debug(f"🔍 查询IP: {ip}")
            geo_data = ip_geo_manager.lookup_ip(ip)

            if geo_data:
                logging.debug(f"📍 解析成功: {ip} -> {geo_data.get('city', 'N/A')}, {geo_data.get('country_name', 'N/A')}")

                geo_info = {
                    "country_code": geo_data.get("country_code"),
                    "country_name": geo_data.get("country_name"),
                    "city": geo_data.get("city"),
                    "latitude": geo_data.get("latitude"),
                    "longitude": geo_data.get("longitude"),
                    "mmdb_version": "1.0",
                    "geo_updated_at": datetime.utcnow(),
                }

                try:
                    # 更新所有该IP的访问记录
                    update_result = db.access_logs.update_many({"ip": original_ip}, {"$set": {"geo_info": geo_info}})
                    logging.debug(f"💾 更新访问记录: '{original_ip}' -> {update_result.modified_count} 条记录")

                    # 保存到缓存
                    geo_doc = {"ip": ip, **geo_info}
                    db.ip_geo_cache.replace_one({"ip": ip}, geo_doc, upsert=True)
                    logging.debug(f"💾 保存到缓存: {ip}")

                    # 更新items中的地理信息
                    for item in items:
                        if item["ip"] == original_ip:
                            item["geo_info"] = geo_info
                            break

                    processed_count += 1

                except Exception as e:
                    logging.warning(f"❌ 更新IP {ip} 地理信息失败: {e}")
                    skipped_count += 1
            else:
                logging.debug(f"❓ 无法解析IP: {ip} (可能是私有IP或无记录)")
                skipped_count += 1

        # 总结日志
        logging.info("📊 批量更新完成:")
        logging.info(f"  - 新解析并嵌入: {processed_count} 个IP")
        logging.info(f"  - 跳过/失败: {skipped_count} 个IP")
        logging.info(f"  - 剩余未处理: {len(ips_to_lookup) - processed_count} 个IP")

        if processed_count > 0:
            logging.info(f"🎉 成功更新了 {processed_count} 个IP的地理信息到访问记录中")

    except Exception as e:
        logging.error(f"❌ 批量更新地理信息失败: {e}", exc_info=True)
