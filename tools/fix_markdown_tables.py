#!/usr/bin/env python3
import sys
import os
import shutil
from pathlib import Path


def fix_list_format(content):
    """修复列表格式，确保【- 】开头的行前面要么是空行，要么是另一个列表项"""
    lines = content.split('\n')
    fixed_lines = []

    for i, line in enumerate(lines):
        current_line = line.strip()
        # 处理被日语引号包裹的表格行
        if current_line.startswith('- "| ') and current_line.endswith(' |" '):
            # 移除引号和列表符号，只保留表格内容
            table_content = current_line[4:-2].strip()  # 移除开头的 '- "' 和结尾的 '"'
            if table_content.startswith('| '):
                table_content = table_content[2:]  # 移除多余的开头空格和|
            if table_content.endswith(' |'):
                table_content = table_content[:-2]  # 移除多余的结尾空格和|
            cells = [cell.strip() for cell in table_content.split('|')]
            fixed_line = '| ' + ' | '.join(cells) + ' |'
            fixed_lines.append(fixed_line)
        elif current_line.startswith('- '):
            # 如果是第一行或者上一行是空行或者上一行也是列表项，则直接添加
            if (i == 0 or not fixed_lines or not fixed_lines[-1].strip() or fixed_lines[-1].strip().startswith('- ')):
                fixed_lines.append(line)
            else:
                # 否则，在当前行之前添加一个空行
                fixed_lines.append('')
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def fix_markdown_table(content):
    """修复Markdown表格格式"""
    lines = content.split('\n')
    fixed_lines = []
    in_table = False
    header_found = False

    for i, line in enumerate(lines):
        # 移除多余的空格和制表符
        line = line.strip()

        # 检测表格开始（以 | 开头的行）
        if line.startswith('|') and '|' in line[1:]:
            if not in_table:
                # 确保表格前有空行
                if fixed_lines and fixed_lines[-1]:
                    fixed_lines.append('')
                in_table = True

            # 清理表格行
            cells = [cell.strip() for cell in line.split('|')]
            # 移除空的首尾单元格
            cells = [cell for cell in cells if cell]
            # 重建表格行
            fixed_line = '| ' + ' | '.join(cells) + ' |'
            fixed_lines.append(fixed_line)

            # 检测表头行并添加分隔行
            if in_table and not header_found and i < len(lines) - 1:
                next_line = lines[i + 1].strip()
                if not next_line.startswith('|---'):
                    header_found = True
                    # 生成分隔行
                    separator = '|' + '|'.join(['---' for _ in cells]) + '|'
                    fixed_lines.append(separator)
        else:
            if in_table:
                # 确保表格后有空行
                if fixed_lines and fixed_lines[-1]:
                    fixed_lines.append('')
                in_table = False
                header_found = False
            fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def needs_fixing(content):
    """检查内容是否需要修复"""
    fixed_content = fix_markdown_table(content)
    fixed_content = fix_list_format(fixed_content)
    return content != fixed_content


def process_file(input_file):
    """处理单个Markdown文件"""
    try:
        # 读取文件
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否需要修复
        if not needs_fixing(content):
            print(f"文件无需修复: {input_file}")
            return True

        # 创建备份
        backup_file = str(input_file) + '.bak'
        shutil.copy2(input_file, backup_file)
        print(f"已创建备份: {backup_file}")

        # 修复表格格式
        fixed_content = fix_markdown_table(content)
        # 修复列表格式
        fixed_content = fix_list_format(fixed_content)

        # 写回文件
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(fixed_content)

        print(f"成功修复文件: {input_file}")
        return True
    except Exception as e:
        print(f"处理文件 {input_file} 时出错: {str(e)}")
        return False


def process_directory(directory):
    """处理目录中的所有Markdown文件"""
    success_count = 0
    for md_file in Path(directory).rglob('*.md'):
        if process_file(md_file):
            success_count += 1
    return success_count


def main():
    if len(sys.argv) < 2:
        print("使用方法: python fix_markdown_tables.py <markdown_file_or_directory> [markdown_file_or_directory2 ...]")
        sys.exit(1)

    success_count = 0
    for path in sys.argv[1:]:
        if os.path.isdir(path):
            print(f"\n处理目录: {path}")
            success_count += process_directory(path)
        elif os.path.isfile(path):
            if not path.endswith('.md'):
                print(f"跳过非Markdown文件: {path}")
                continue
            if process_file(path):
                success_count += 1
        else:
            print(f"路径不存在: {path}")

    print(f"\n处理完成! 成功修复 {success_count} 个文件。")


if __name__ == "__main__":
    main()
