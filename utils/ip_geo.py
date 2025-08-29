from datetime import datetime
from datetime import timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Dict, Optional

from geoip2.database import Reader
from geoip2.errors import AddressNotFoundError
import requests


class IPGeoManager:
    """IP地理位置管理器"""

    def __init__(self):
        self.mmdb_dir = Path("temp/mmdb")
        self.mmdb_file = self.mmdb_dir / "GeoLite2-City.mmdb"
        self.update_record_file = self.mmdb_dir / "update_record.json"
        self.reader: Optional[Reader] = None
        self._ensure_mmdb_dir()

    def _ensure_mmdb_dir(self):
        """确保mmdb目录存在"""
        self.mmdb_dir.mkdir(parents=True, exist_ok=True)

    def _load_update_record(self) -> Dict:
        """加载更新记录"""
        if not self.update_record_file.exists():
            return {"next_update": None, "last_update": None, "file_hash": None}

        try:
            with open(self.update_record_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"加载更新记录失败: {e}")
            return {"next_update": None, "last_update": None, "file_hash": None}

    def _save_update_record(self, record: Dict):
        """保存更新记录"""
        try:
            with open(self.update_record_file, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存更新记录失败: {e}")

    def _download_mmdb(self) -> bool:
        """下载mmdb文件"""
        url = "https://git.io/GeoLite2-City.mmdb"
        try:
            logging.info("开始下载GeoIP数据库...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # 先下载到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mmdb') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name

            # 计算文件哈希
            with open(temp_file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            # 移动文件到目标位置
            shutil.move(temp_file_path, self.mmdb_file)

            # 更新记录
            now = datetime.utcnow()
            next_update = now + timedelta(days=10)
            record = {"next_update": next_update.isoformat(), "last_update": now.isoformat(), "file_hash": file_hash}
            self._save_update_record(record)

            logging.info(f"GeoIP数据库下载成功，下次更新: {next_update}")
            return True

        except Exception as e:
            logging.error(f"下载GeoIP数据库失败: {e}")
            return False

    def _is_private_ip(self, ip: str) -> bool:
        """判断是否为私有IP地址"""
        try:
            import ipaddress
            ip_obj = ipaddress.ip_address(ip)
            return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
        except Exception:
            return False

    def ensure_mmdb_available(self) -> bool:
        """确保mmdb文件可用，必要时下载"""
        # 检查是否需要更新
        record = self._load_update_record()
        need_update = False

        if not self.mmdb_file.exists():
            need_update = True
            logging.info("GeoIP数据库文件不存在，需要下载")
        else:
            # 检查更新记录
            if record.get("next_update"):
                try:
                    next_update = datetime.fromisoformat(record["next_update"])
                    if datetime.utcnow() >= next_update:
                        need_update = True
                        logging.info("GeoIP数据库文件已过期，需要更新")
                except Exception as e:
                    logging.warning(f"解析更新记录时间失败: {e}")
                    need_update = True

        if need_update:
            # 删除旧文件
            if self.mmdb_file.exists():
                try:
                    os.remove(self.mmdb_file)
                    logging.info("已删除旧的GeoIP数据库文件")
                except Exception as e:
                    logging.warning(f"删除旧文件失败: {e}")

            # 下载新文件
            if not self._download_mmdb():
                logging.error("无法下载GeoIP数据库，将使用现有文件（如果存在）")
                return self.mmdb_file.exists()

        return True

    def get_reader(self) -> Optional[Reader]:
        """获取mmdb reader实例"""
        if self.reader is None and self.mmdb_file.exists():
            try:
                self.reader = Reader(str(self.mmdb_file))
                logging.info("GeoIP数据库Reader初始化成功")
            except Exception as e:
                logging.error(f"初始化GeoIP数据库Reader失败: {e}")
                return None

        return self.reader

    def lookup_ip(self, ip: str) -> Optional[Dict]:
        """查询IP地理位置信息"""
        if self._is_private_ip(ip):
            return None

        reader = self.get_reader()
        if not reader:
            return None

        try:
            response = reader.city(ip)
            return {
                "country_code": response.country.iso_code,
                "country_name": response.country.name,
                "city": response.city.name,
                "latitude": response.location.latitude,
                "longitude": response.location.longitude,
            }
        except AddressNotFoundError:
            return None
        except Exception as e:
            logging.warning(f"查询IP {ip} 地理位置失败: {e}")
            return None

    def close(self):
        """关闭reader"""
        if self.reader:
            self.reader.close()
            self.reader = None


# 全局实例
ip_geo_manager = IPGeoManager()
