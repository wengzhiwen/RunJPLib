import logging
from datetime import datetime

from bson.objectid import ObjectId
from flask import jsonify, redirect, render_template, request, url_for

from routes.admin.auth import admin_required
from utils import LlamaIndexIntegration, get_db, thread_pool_manager

from . import admin_bp


def _update_university_in_db(object_id, update_data, university_id):
    """异步更新大学信息到数据库"""
    try:
        db = get_db()
        if db is None:
            logging.error("Admin异步更新大学信息失败：无法连接数据库")
            return
        db.universities.update_one({"_id": object_id}, update_data)
        logging.info(f"University with ID {university_id} was updated (async).")
    except Exception as e:
        logging.error(f"异步更新大学信息失败: {e}")


@admin_bp.route("/manage/universities")
@admin_required
def manage_universities_page():
    return render_template("manage_universities.html")


@admin_bp.route("/api/universities", methods=["GET"])
@admin_required
def get_universities():
    db = get_db()
    if db is None:
        logging.error("[Admin API] Get universities failed: DB connection error.")
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        logging.debug("[Admin API] Fetching universities from database...")
        projection = {"content": 0, "source_path": 0}

        # 解析基于标签的筛选参数，支持1-2个标签，AND关系
        tags_param = request.args.get("tags", "").strip()
        query = {}
        if tags_param:
            # 允许逗号分隔或多次tags参数传入
            tags = [t.strip() for t in tags_param.split(",") if t.strip()]
            if not tags:
                tags = request.args.getlist("tags")
            # 限制最多两个标签
            if len(tags) > 2:
                tags = tags[:2]
            if len(tags) == 1:
                query["tags"] = tags[0]
            elif len(tags) == 2:
                # AND 关系：同时包含两个标签
                query["tags"] = {"$all": tags}

        # 为了保持"同一大学仅展示最新"的去重逻辑，这里使用聚合管道：
        # 1) 先按 _id 倒序（_id时间序），2) 按大学名分组取第一个（即最新），3) 再按 _id 倒序返回
        project_stage = {"$project": {field: 0 for field in projection}}

        if query:
            # 基于"每所大学的标签合集"进行筛选，然后输出该大学的最新一份文档
            # 1) 按 _id 倒序确保 firstDoc 是最新
            # 2) group 收集每所大学所有 tags 数组
            # 3) 用 $reduce + $setUnion 合并并去重所有 tags
            # 4) 根据 combinedTags 做 AND/单标签匹配
            # 5) 输出 firstDoc 并维持最终排序与投影
            match_on_tags = {}
            if isinstance(query.get("tags"), dict) and "$all" in query["tags"]:
                match_on_tags = {"$expr": {"$setIsSubset": [query["tags"]["$all"], "$combinedTags"]}}
            elif isinstance(query.get("tags"), str):
                match_on_tags = {"combinedTags": query["tags"]}

            pipeline = [
                {
                    "$sort": {
                        "_id": -1
                    }
                },
                {
                    "$group": {
                        "_id": "$university_name",
                        "firstDoc": {
                            "$first": "$$ROOT"
                        },
                        "tagsArrays": {
                            "$addToSet": {
                                "$ifNull": ["$tags", []]
                            }
                        }
                    }
                },
                {
                    "$project": {
                        "firstDoc": 1,
                        "combinedTags": {
                            "$setUnion": {
                                "$reduce": {
                                    "input": "$tagsArrays",
                                    "initialValue": [],
                                    "in": {
                                        "$setUnion": ["$$value", "$$this"]
                                    }
                                }
                            }
                        }
                    }
                },
                {
                    "$match": match_on_tags
                } if match_on_tags else {
                    "$match": {}
                },
                {
                    "$replaceRoot": {
                        "newRoot": "$firstDoc"
                    }
                },
                {
                    "$sort": {
                        "_id": -1
                    }
                },
                project_stage,
            ]
        else:
            # 无标签筛选时，保持原有逻辑：每所大学仅展示最新一份，整体按创建时间逆序
            pipeline = [
                {
                    "$sort": {
                        "_id": -1
                    }
                },
                {
                    "$group": {
                        "_id": "$university_name",
                        "doc": {
                            "$first": "$$ROOT"
                        }
                    }
                },
                {
                    "$replaceRoot": {
                        "newRoot": "$doc"
                    }
                },
                {
                    "$sort": {
                        "_id": -1
                    }
                },
                project_stage,
            ]

        universities = list(db.universities.aggregate(pipeline))

        for u in universities:
            u["_id"] = str(u["_id"])
            if u.get("deadline") and isinstance(u["deadline"], datetime):
                u["deadline"] = u["deadline"].isoformat()

        logging.info(f"[Admin API] Successfully fetched {len(universities)} university documents.")
        return jsonify(universities)
    except Exception as e:
        logging.error(
            f"[Admin API] An exception occurred while fetching universities: {e}",
            exc_info=True,
        )
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/api/university-tags", methods=["GET"])
@admin_required
def get_university_tags():
    """返回系统中存在的所有tag及其对应的大学数量，按数量降序排列。"""
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        # 统计口径：每所大学的"全量文档标签合集"去重后计数，避免因最新文档未带标签导致的低估
        pipeline = [
            {
                "$project": {
                    "university_name": 1,
                    "tags": {
                        "$ifNull": ["$tags", []]
                    }
                }
            },
            {
                "$group": {
                    "_id": "$university_name",
                    "tagsArrays": {
                        "$addToSet": "$tags"
                    }
                }
            },
            {
                "$project": {
                    "combinedTags": {
                        "$setUnion": {
                            "$reduce": {
                                "input": "$tagsArrays",
                                "initialValue": [],
                                "in": {
                                    "$setUnion": ["$$value", "$$this"]
                                }
                            }
                        }
                    }
                }
            },
            {
                "$unwind": {
                    "path": "$combinedTags",
                    "preserveNullAndEmptyArrays": False
                }
            },
            {
                "$group": {
                    "_id": "$combinedTags",
                    "count": {
                        "$sum": 1
                    }
                }
            },
            {
                "$sort": {
                    "count": -1,
                    "_id": 1
                }
            },
        ]

        tag_counts = list(db.universities.aggregate(pipeline))
        result = [{"tag": tc["_id"], "count": tc["count"]} for tc in tag_counts]
        return jsonify(result)
    except Exception as e:
        logging.error(f"[Admin API] 获取标签统计失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500


@admin_bp.route("/edit_university/<university_id>", methods=["GET", "POST"])
@admin_required
def edit_university(university_id):
    """
    编辑大学信息的页面和处理逻辑
    GET: 显示编辑表单
    POST: 更新大学信息
    """
    db = get_db()
    if db is None:
        return render_template("edit_university.html", error="数据库连接失败")

    try:
        object_id = ObjectId(university_id)
    except Exception:
        return render_template("404.html"), 404

    if request.method == "POST":
        university_name = request.form.get("university_name", "").strip()
        university_name_zh = request.form.get("university_name_zh", "").strip()
        is_premium = request.form.get("is_premium") == "true"
        deadline_str = request.form.get("deadline", "")
        basic_analysis_report = request.form.get("basic_analysis_report", "").strip()

        if not university_name:
            university = db.universities.find_one({"_id": object_id})
            return render_template("edit_university.html", university=university, error="大学名称不能为空")

        update_data = {
            "$set": {
                "university_name": university_name,
                "university_name_zh": university_name_zh,
                "is_premium": is_premium,
                "content.report_md": basic_analysis_report,
                "last_modified": datetime.utcnow(),
            }
        }

        if deadline_str:
            try:
                # 将 YYYY-MM-DD 格式的字符串转换为 datetime 对象
                update_data["$set"]["deadline"] = datetime.strptime(deadline_str, "%Y-%m-%d")
            except ValueError:
                # 如果日期格式不正确，返回错误信息
                university = db.universities.find_one({"_id": object_id})
                return render_template(
                    "edit_university.html",
                    university=university,
                    error="日期格式不正确，请使用 YYYY-MM-DD 格式。",
                )

        # 尝试异步更新数据库
        success = thread_pool_manager.submit_admin_task(_update_university_in_db, object_id, update_data, university_id)

        if not success:
            # 线程池满，同步执行
            logging.warning("Admin线程池繁忙，同步更新大学信息")
            try:
                db.universities.update_one({"_id": object_id}, update_data)
                logging.info(f"University with ID {university_id} was updated (sync).")
            except Exception as e:
                logging.error(f"同步更新大学信息失败: {e}")
                return render_template(
                    "edit_university.html",
                    university=db.universities.find_one({"_id": object_id}),
                    error="更新失败，请重试",
                )
        else:
            logging.info(f"University with ID {university_id} update task submitted to thread pool.")

        return redirect(url_for("admin.manage_universities_page"))

    # GET 请求
    university = db.universities.find_one({"_id": object_id})
    if not university:
        return render_template("404.html"), 404

    return render_template("edit_university.html", university=university)


@admin_bp.route("/api/universities/<item_id>", methods=["DELETE"])
@admin_required
def delete_university(item_id):
    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    # First, delete the vector index
    try:
        llama_index_integration = LlamaIndexIntegration()
        if not llama_index_integration.delete_university_index(item_id):
            # Log a warning but don't block the deletion of the MongoDB record
            logging.warning(f"Could not delete vector index for university {item_id}. It may need to be cleaned up manually.")
    except Exception as e:
        logging.error(f"An error occurred while deleting vector index for university {item_id}: {e}", exc_info=True)

    # Then, delete the MongoDB record
    db.universities.delete_one({"_id": ObjectId(item_id)})
    return jsonify({"message": "删除成功"})


@admin_bp.route("/api/universities/search", methods=["GET"])
@admin_required
def search_universities():
    """
    根据名称搜索大学。
    接受'q'作为查询参数。
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    db = get_db()
    if db is None:
        return jsonify({"error": "数据库连接失败"}), 500

    try:
        # 根据名称模糊搜索（不区分大小写）
        universities = list(db.universities.find(
            {
                "university_name": {
                    "$regex": query,
                    "$options": "i"
                }
            },
            {
                "_id": 1,
                "university_name": 1
            },
        ).limit(20))  # 限制20条结果以提高性能

        for u in universities:
            u["_id"] = str(u["_id"])

        return jsonify(universities)
    except Exception as e:
        logging.error(f"[Admin API] University search failed: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500
